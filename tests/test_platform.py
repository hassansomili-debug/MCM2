from __future__ import annotations

import base64
import json
import tempfile
import threading
import unittest
import urllib.error
import urllib.parse
import urllib.request
import zipfile
from io import BytesIO
from pathlib import Path

from http.server import ThreadingHTTPServer

from mcm import config
from mcm.api import API
from mcm.database import init_db
from mcm.scoring import _normalize


class PlatformJourneyTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tempdir = tempfile.TemporaryDirectory()
        config.DB_PATH = Path(cls.tempdir.name) / "test.sqlite3"
        init_db()
        cls.server = ThreadingHTTPServer(("127.0.0.1", 0), API)
        cls.port = cls.server.server_address[1]
        cls.thread = threading.Thread(target=cls.server.serve_forever, daemon=True)
        cls.thread.start()

    @classmethod
    def tearDownClass(cls):
        cls.server.shutdown()
        cls.server.server_close()
        cls.tempdir.cleanup()

    def request(self, method, path, body=None, token=None, expected=200, raw=False):
        payload = None if body is None else json.dumps(body).encode()
        headers = {"Content-Type": "application/json"}
        if token:
            headers["Authorization"] = f"Bearer {token}"
        parsed = urllib.parse.urlsplit(path)
        safe_path = urllib.parse.quote(urllib.parse.unquote(parsed.path), safe="/%")
        request_path = urllib.parse.urlunsplit(("", "", safe_path, parsed.query, parsed.fragment))
        request = urllib.request.Request(f"http://127.0.0.1:{self.port}{request_path}", data=payload, method=method, headers=headers)
        try:
            with urllib.request.urlopen(request, timeout=10) as response:
                content = response.read()
                status = response.status
                content_type = response.headers.get("Content-Type", "")
        except urllib.error.HTTPError as error:
            content = error.read()
            status = error.code
            content_type = error.headers.get("Content-Type", "")
        self.assertEqual(expected, status, content.decode("utf-8", "replace"))
        if raw:
            return content, content_type
        return json.loads(content or b"{}")

    def login(self, email="sara@example.com", password="ChangeMe-2026"):
        return self.request("POST", "/api/auth/login", {"email": email, "password": password})["token"]

    def test_complete_company_journey_and_exports(self):
        token = self.login()
        me = self.request("GET", "/api/me", token=token)
        self.assertEqual("COMPANY_ADMIN", me["user"]["role"])
        created = self.request("POST", "/api/assessments", {"assessment_type": "FULL"}, token, 201)
        assessment_id = created["id"]
        detail = self.request("GET", f"/api/assessments/{assessment_id}", token=token)
        self.assertEqual(51, len(detail["items"]))
        first_ten = [{"item_id": item["id"], "value": 4} for item in detail["items"][:10]]
        save = self.request("POST", f"/api/assessments/{assessment_id}/answers", {"answers": first_ten}, token)
        self.assertEqual(10, save["saved"])
        self.request("POST", "/api/auth/logout", {}, token)
        token = self.login()
        resumed = self.request("GET", f"/api/assessments/{assessment_id}", token=token)
        self.assertEqual(10, len(resumed["responses"]))
        remaining = [{"item_id": item["id"], "value": 4} for item in resumed["items"]]
        self.request("POST", f"/api/assessments/{assessment_id}/answers", {"answers": remaining}, token)
        review = self.request("GET", f"/api/assessments/{assessment_id}/review", token=token)
        self.assertTrue(review["complete"])
        results = self.request("POST", f"/api/assessments/{assessment_id}/submit", {}, token)
        self.assertEqual(75.0, results["scores"]["MCM"]["total"])
        self.assertEqual(75.0, results["scores"]["SMCE"]["total"])
        self.assertEqual(7, len(results["scores"]["MCM"]["dimensions"]))
        self.assertEqual(5, len(results["scores"]["SMCE"]["dimensions"]))
        roadmap = self.request("GET", f"/api/roadmap/{assessment_id}", token=token)
        self.assertEqual(7, sum(len(items) for items in roadmap["roadmap"].values()))
        report = self.request("POST", "/api/reports", {"assessment_id": assessment_id, "report_type": "EXECUTIVE"}, token, 201)
        pdf, content_type = self.request("GET", report["download_url"], token=token, raw=True)
        self.assertTrue(pdf.startswith(b"%PDF-1.4"))
        self.assertIn("application/pdf", content_type)
        benchmark = self.request("GET", f"/api/benchmark/{assessment_id}", token=token)
        self.assertFalse(benchmark["available"])
        self.assertEqual("NON_REAL_ASSESSMENT", benchmark["reason"])

        admin = self.login("admin@nudj.local", "Nudj-Admin-2026!")
        export = self.request("POST", "/api/research/exports", {"format": "XLSX", "data_origin": "DEMO"}, admin, 201)
        workbook, workbook_type = self.request("GET", export["download_url"], token=admin, raw=True)
        self.assertIn("spreadsheetml", workbook_type)
        with zipfile.ZipFile(BytesIO(workbook)) as archive:
            workbook_xml = archive.read("xl/workbook.xml").decode()
            self.assertEqual(10, workbook_xml.count("<sheet "))
            self.assertIn("01_RESPONSES_WIDE", workbook_xml)
            self.assertIn("10_METADATA", workbook_xml)
        spss = self.request("POST", "/api/research/exports", {"format": "SPSS", "data_origin": "DEMO"}, admin, 201)
        package, _ = self.request("GET", spss["download_url"], token=admin, raw=True)
        with zipfile.ZipFile(BytesIO(package)) as archive:
            self.assertEqual({"dataset.csv", "codebook.xlsx", "labels.xlsx", "import.sps", "README.txt"}, set(archive.namelist()))

    def test_registration_rbac_tenant_boundary_and_security(self):
        registered = self.request("POST", "/api/auth/register", {
            "name": "شركة اختبار", "email": "owner@example.test", "password": "SecurePass2026",
            "organization_name": "منظمة مستقلة", "service_consent": True,
        }, expected=201)
        token = registered["token"]
        denied = self.request("GET", "/api/research/summary", token=token, expected=403)
        self.assertEqual("permission_denied", denied["error"])
        escalation = self.request("PATCH", "/api/company/team", {
            "user_id": registered["user"]["id"], "role": "RESEARCHER", "status": "ACTIVE",
        }, token=token, expected=403)
        self.assertEqual("permission_denied", escalation["error"])
        foreign = self.request("GET", "/api/assessments/1", token=token, expected=404)
        self.assertEqual("assessment_not_found", foreign["error"])
        for path in ("/server.py", "/mcm.sqlite3", "/متطلبات_منصة_نضج_MCM.docx"):
            blocked = self.request("GET", path, token=token, expected=404)
            self.assertEqual("not_found", blocked["error"])
        self.request("POST", "/api/auth/logout", {}, token)
        self.request("GET", "/api/me", token=token, expected=401)

    def test_instrument_specification_is_not_misrepresented_as_item_bank(self):
        admin = self.login("admin@nudj.local", "Nudj-Admin-2026!")
        document = (Path(__file__).parents[1] / "متطلبات_منصة_نضج_MCM.docx").read_bytes()
        preview = self.request("POST", "/api/instrument-versions/preview", {
            "filename": "متطلبات_منصة_نضج_MCM.docx",
            "mime_type": "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
            "docx_base64": base64.b64encode(document).decode(),
        }, admin)
        self.assertFalse(preview["valid"])
        self.assertGreater(len(preview["errors"]), 0)

    def test_participant_submission_is_scoped_and_one_time(self):
        owner = self.login()
        created = self.request("POST", "/api/assessments", {"assessment_type": "FULL"}, owner, 201)
        assessment_id = created["id"]
        invitation = self.request("POST", "/api/invitations", {
            "assessment_id": assessment_id, "email": "participant@example.test", "full_name": "مشارك مستقل",
            "assessment_role": "RESPONDENT",
        }, owner, 201)
        raw_token = urllib.parse.parse_qs(urllib.parse.urlsplit(invitation["invitation_url"]).fragment.split("?", 1)[1])["token"][0]
        accepted = self.request("POST", f"/api/invitations/{raw_token}/accept", {
            "service_consent": True, "research_consent": False, "full_name": "مشارك مستقل",
        })
        participant_token = accepted["token"]

        owner_detail = self.request("GET", f"/api/assessments/{assessment_id}", token=owner)
        owner_answers = [{"item_id": item["id"], "value": 3} for item in owner_detail["items"]]
        self.request("POST", f"/api/assessments/{assessment_id}/answers", {"answers": owner_answers}, owner)
        owner_submit = self.request("POST", f"/api/assessments/{assessment_id}/submit", {}, owner)
        self.assertFalse(owner_submit["assessment_complete"])
        self.assertEqual(1, owner_submit["pending_participants"])

        participant = self.request("GET", f"/api/participant/session/{participant_token}")
        participant_answers = [{"item_id": item["id"], "value": 4} for item in participant["items"]]
        self.request("POST", f"/api/participant/session/{participant_token}/answers", {"answers": participant_answers})
        participant_submit = self.request("POST", f"/api/participant/session/{participant_token}/submit", {})
        self.assertTrue(participant_submit["assessment_complete"])
        locked = self.request("POST", f"/api/participant/session/{participant_token}/submit", {}, expected=409)
        self.assertIn(locked["error"], {"assessment_locked", "participant_submission_locked"})
        self.request("GET", f"/api/results/{assessment_id}", token=owner)

    def test_real_research_data_requires_controller_and_contributor_consent(self):
        researcher = self.login("admin@nudj.local", "Nudj-Admin-2026!")
        baseline = self.request("GET", "/api/research/dataset?data_origin=REAL", token=researcher)["row_count"]
        registered = self.request("POST", "/api/auth/register", {
            "name": "مالك الموافقة", "email": "consent-owner@example.test", "password": "SecurePass2026",
            "organization_name": "منظمة الموافقة", "service_consent": True,
        }, expected=201)
        owner = registered["token"]
        self.request("PATCH", "/api/company/profile", {"research_consent": True}, owner)
        self.request("PATCH", "/api/consents", {"consent_type": "RESEARCH_USE", "consent_version": "1.0", "accepted": True}, owner)
        assessment = self.request("POST", "/api/assessments", {"assessment_type": "FULL"}, owner, 201)
        detail = self.request("GET", f"/api/assessments/{assessment['id']}", token=owner)
        answers = [{"item_id": item["id"], "value": 4} for item in detail["items"]]
        self.request("POST", f"/api/assessments/{assessment['id']}/answers", {"answers": answers}, owner)
        self.request("POST", f"/api/assessments/{assessment['id']}/submit", {}, owner)
        included = self.request("GET", "/api/research/dataset?data_origin=REAL", token=researcher)["row_count"]
        self.assertEqual(baseline + 1, included)
        self.request("PATCH", "/api/consents", {"consent_type": "RESEARCH_USE", "consent_version": "1.0", "accepted": False}, owner)
        excluded = self.request("GET", "/api/research/dataset?data_origin=REAL", token=researcher)["row_count"]
        self.assertEqual(baseline, excluded)

    def test_scoring_formula_and_reverse_coding(self):
        self.assertEqual(0.0, _normalize(1, 1, 5, False))
        self.assertEqual(50.0, _normalize(3, 1, 5, False))
        self.assertEqual(100.0, _normalize(5, 1, 5, False))
        self.assertEqual(100.0, _normalize(1, 1, 5, True))


if __name__ == "__main__":
    unittest.main()
