from __future__ import annotations

import base64
import json
import sqlite3
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
from mcm.database import POSTGRES_SCHEMA, POSTGRES_TABLES, _migrate_legacy, init_db
from mcm.postgres import (
    HybridRow,
    connection_security_options,
    normalize_database_url,
    postgres_sql,
)
from mcm.scoring import _normalize


class PlatformJourneyTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        # `connect()` prefers DATABASE_URL over DB_PATH, so a developer whose
        # .env points at Supabase would otherwise run these write-heavy
        # journeys against the production database. Force the SQLite path.
        config.DATABASE_URL = ""
        config.DATABASE_MIGRATION_URL = ""
        cls.tempdir = tempfile.TemporaryDirectory()
        config.DB_PATH = Path(cls.tempdir.name) / "test.sqlite3"
        config.PLATFORM_ADMIN_EMAIL = "platform-admin@example.test"
        config.PLATFORM_ADMIN_NAME = "مدير اختبار المنصة"
        config.PLATFORM_ADMIN_PASSWORD = "TestAdminPass2026"
        config.ALLOW_REGISTRATION = True
        config.EPHEMERAL_STORAGE = False
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

    def login(self, email="platform-admin@example.test", password="TestAdminPass2026"):
        return self.request("POST", "/api/auth/login", {"email": email, "password": password})["token"]

    def test_complete_company_journey_and_exports(self):
        token = self.login()
        me = self.request("GET", "/api/me", token=token)
        self.assertEqual("SUPER_ADMIN", me["user"]["role"])
        created = self.request("POST", "/api/assessments", {"assessment_type": "FULL"}, token, 201)
        assessment_id = created["id"]
        detail = self.request("GET", f"/api/assessments/{assessment_id}", token=token)
        self.assertEqual(67, len(detail["items"]))
        self.assertEqual(12, sum(item["construct"] == "ENABLER" for item in detail["items"]))
        self.assertEqual(12, sum(item["construct"] == "OUTCOME" for item in detail["items"]))
        self.assertEqual(3, sum(item["response_type"] == "LIKERT_RELATIVE" for item in detail["items"]))
        first_ten = [{"item_id": item["id"], "value": 4} for item in detail["items"][:10]]
        save = self.request("POST", f"/api/assessments/{assessment_id}/answers", {"answers": first_ten}, token)
        self.assertEqual(10, save["saved"])
        self.request("POST", "/api/auth/logout", {}, token)
        token = self.login()
        resumed = self.request("GET", f"/api/assessments/{assessment_id}", token=token)
        self.assertEqual(10, len(resumed["responses"]))
        remaining = [
            {"item_id": item["id"], "value": 3 if item["construct"] == "SMCE" else 4}
            for item in resumed["items"]
        ]
        self.request("POST", f"/api/assessments/{assessment_id}/answers", {"answers": remaining}, token)
        review = self.request("GET", f"/api/assessments/{assessment_id}/review", token=token)
        self.assertTrue(review["complete"])
        results = self.request("POST", f"/api/assessments/{assessment_id}/submit", {}, token)
        self.assertEqual(75.0, results["scores"]["MCM"]["total"])
        self.assertEqual(50.0, results["scores"]["SMCE"]["total"])
        self.assertEqual("PROACTIVE_ADAPTIVE", results["scores"]["MCM"]["maturity_level"]["code"])
        self.assertEqual("PROVISIONAL_ASSOCIATION_NOT_CAUSAL", results["relationship"]["status"])
        self.assertEqual(-25.0, results["relationship"]["efficiency_minus_maturity"])
        self.assertEqual(7, len(results["scores"]["MCM"]["dimensions"]))
        self.assertEqual(5, len(results["scores"]["SMCE"]["dimensions"]))
        self.assertEqual(4, len(results["scores"]["ENABLER"]["dimensions"]))
        self.assertEqual(4, len(results["scores"]["OUTCOME"]["dimensions"]))
        self.assertEqual("0.2", results["source_instrument_version"])
        self.assertEqual("PROVISIONAL_NOT_VALIDATED", results["validation_status"])
        self.assertEqual(3, len(results["dashboard"]["opportunities"]))
        self.assertEqual({"0-30", "31-90", "3-6"}, set(results["dashboard"]["roadmap"]))
        roadmap = self.request("GET", f"/api/roadmap/{assessment_id}", token=token)
        self.assertEqual(7, sum(len(items) for items in roadmap["roadmap"].values()))
        report = self.request("POST", "/api/reports", {"assessment_id": assessment_id, "report_type": "EXECUTIVE"}, token, 201)
        pdf, content_type = self.request("GET", report["download_url"], token=token, raw=True)
        self.assertTrue(pdf.startswith(b"%PDF-1.4"))
        self.assertGreater(len(pdf), 5000)
        self.assertIn(b"Five-stage maturity progression", pdf)
        self.assertIn("application/pdf", content_type)
        benchmark = self.request("GET", f"/api/benchmark/{assessment_id}", token=token)
        self.assertFalse(benchmark["available"])
        self.assertEqual("NON_REAL_ASSESSMENT", benchmark["reason"])
        ai_plan = self.request("POST", f"/api/assessments/{assessment_id}/ai-plan", {}, token)
        self.assertEqual("deterministic", ai_plan["plan"]["generation"]["mode"])
        self.assertTrue(ai_plan["plan"]["safeguards"]["score_unchanged"])
        self.assertNotIn("organization_name", json.dumps(ai_plan["plan"]))

        admin = self.login()
        export = self.request("POST", "/api/research/exports", {"format": "XLSX", "data_origin": "TEST"}, admin, 201)
        workbook, workbook_type = self.request("GET", export["download_url"], token=admin, raw=True)
        self.assertIn("spreadsheetml", workbook_type)
        with zipfile.ZipFile(BytesIO(workbook)) as archive:
            workbook_xml = archive.read("xl/workbook.xml").decode()
            self.assertEqual(10, workbook_xml.count("<sheet "))
            self.assertIn("01_RESPONSES_WIDE", workbook_xml)
            self.assertIn("10_METADATA", workbook_xml)
            first_sheet = archive.read("xl/worksheets/sheet1.xml").decode()
            self.assertIn("FIRM_AGE_YEARS", first_sheet)
            self.assertIn("EFFICIENCY_MINUS_MATURITY", first_sheet)
        spss = self.request("POST", "/api/research/exports", {"format": "SPSS", "data_origin": "TEST"}, admin, 201)
        package, _ = self.request("GET", spss["download_url"], token=admin, raw=True)
        with zipfile.ZipFile(BytesIO(package)) as archive:
            self.assertEqual({"dataset.csv", "dataset.xlsx", "codebook.xlsx", "labels.xlsx", "value_labels.xlsx", "import.sps", "README.txt"}, set(archive.namelist()))
            dataset = archive.read("dataset.csv").decode("utf-8-sig")
            self.assertIn(",-25.0,", dataset)
            self.assertNotIn("'-25.0", dataset)
            syntax = archive.read("import.sps").decode()
            self.assertIn("F12.2", syntax)
            self.assertIn("VALUE LABELS", syntax)
            self.assertIn("Does not apply at all", syntax)
            self.assertIn("Much worse than major competitors", syntax)
        statistics = self.request("GET", "/api/research/statistics?data_origin=TEST", token=admin)
        self.assertGreaterEqual(statistics["MCM"]["n"], 1)
        self.assertGreaterEqual(statistics["SMCE"]["n"], 1)

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

    def test_maturity_stage_labels_and_public_stage_content(self):
        payload = self.request("GET", "/api/public/maturity-levels")
        levels = payload["levels"]
        self.assertEqual(5, len(levels))
        self.assertEqual([1, 2, 3, 4, 5], [level["level_order"] for level in levels])

        expected = [
            ("REACTIVE_AD_HOC", "ردّة فعل / عشوائي", "Reactive / Ad hoc"),
            ("RESPONSIVE_EMERGING", "منظم أوليًا / مستجيب", "Responsive / Emerging"),
            ("MANAGED_INTEGRATED", "مدار / متكامل", "Managed & Integrated"),
            ("PROACTIVE_ADAPTIVE", "استباقي / متكيّف", "Proactive & Adaptive"),
            ("مستدام", "مستدام / ذكي / قابل للتوسع", "Institutionalised & Intelligent"),
        ]
        for level, (_, label_ar, label_en) in zip(levels, expected):
            self.assertEqual(label_ar, level["label_ar"])
            # The English label is explicitly unchanged by this revision.
            self.assertEqual(label_en, level["label_en"])
            # Every stage carries the narrative the public section renders, so
            # no component has to hardcode a second copy of the wording.
            for field in ("summary_ar", "description_ar"):
                self.assertTrue(level[field], f"{level['code']} is missing {field}")
            for field in ("characteristics_ar", "risks_ar", "focus_ar", "transition_ar"):
                self.assertTrue(level[field], f"{level['code']} is missing {field}")

        # The identifying codes are stable data and must survive a rename.
        self.assertEqual(
            ["REACTIVE_AD_HOC", "RESPONSIVE_EMERGING", "MANAGED_INTEGRATED",
             "PROACTIVE_ADAPTIVE", "INSTITUTIONALISED_INTELLIGENT"],
            [level["code"] for level in levels],
        )
        # So must the score bands, so no historical classification moves.
        self.assertEqual([0.0, 20.0, 40.0, 60.0, 80.0], [level["min_score"] for level in levels])

        superseded = {"عشوائي", "ناشئ", "متكامل", "استباقي ومتكيف", "مؤسسي وذكي", "تفاعلي / عشوائي"}
        self.assertFalse(superseded.intersection({level["label_ar"] for level in levels}))

    def test_public_model_status_is_evidence_informed_not_pilot_or_validated(self):
        config_payload = self.request("GET", "/api/public-config")
        model = config_payload["model"]
        self.assertEqual("نموذج تطبيقي قائم على الأدلة العلمية", model["label_ar"])
        self.assertEqual("Evidence-Informed Applied Model", model["label_en"])
        self.assertTrue(model["result_disclaimer_ar"])
        self.assertEqual(2, len(model["methodology_ar"]))

        serialized = json.dumps(config_payload, ensure_ascii=False)
        for banned in ("Pilot", "PILOT", "Research Beta", "نموذج تجريبي", "نسخة تجريبية بحثية"):
            self.assertNotIn(banned, serialized)
        # An unearned validation claim is as wrong as the pilot wording.
        for overclaim in ("Scientifically Validated", "معتمد علميًا", "مقياس محقق نهائيًا"):
            self.assertNotIn(overclaim, serialized)

    def test_participant_facing_client_uses_results_not_dashboard_wording(self):
        client = (Path(__file__).parents[1] / "app.js").read_text(encoding="utf-8")
        shell = (Path(__file__).parents[1] / "index.html").read_text(encoding="utf-8")
        for banned in ("داشبورد", "لوحة التحكم", "Research Beta"):
            self.assertNotIn(banned, client, f"{banned} still reaches the participant")
            self.assertNotIn(banned, shell, f"{banned} still reaches the participant")
        # The stage section and its drawer must be driven by the served data.
        self.assertIn("/api/public/maturity-levels", client)
        self.assertIn("data-action=\"stage-detail\"", client)
        self.assertIn("اكتشف مستوى منشأتك", client)
        self.assertIn("تعرف على هذه المرحلة", client)
        # No stage label may be hardcoded in the client any more.
        for label in ("ردّة فعل / عشوائي", "منظم أوليًا / مستجيب", "مستدام / ذكي / قابل للتوسع"):
            self.assertNotIn(label, client, "stage labels must come from the API")

    def test_stage_rename_preserves_scores_and_writes_an_audit_record(self):
        from mcm import database

        with database.transaction() as db:
            version = db.execute(
                "SELECT id FROM instrument_versions WHERE version='0.4.0' ORDER BY id DESC LIMIT 1"
            ).fetchone()
            level = db.execute(
                "SELECT id,label_ar FROM maturity_levels WHERE version_id=? AND code='REACTIVE_AD_HOC'",
                (version["id"],),
            ).fetchone()
            level_id, current_label = level["id"], level["label_ar"]
            classified = db.execute(
                "SELECT COUNT(*) FROM assessment_scores WHERE maturity_level_id IS NOT NULL"
            ).fetchone()[0]
            db.execute(
                "UPDATE maturity_levels SET label_ar='عشوائي' WHERE id=?", (level_id,)
            )
            db.execute("DELETE FROM audit_logs WHERE action='MATURITY_LABEL_RENAMED'")

        database.init_db()

        with database.transaction() as db:
            renamed = db.execute(
                "SELECT label_ar FROM maturity_levels WHERE id=?", (level_id,)
            ).fetchone()["label_ar"]
            self.assertEqual(current_label, renamed)
            # The row is updated in place, so every score keeps its foreign key
            # and no classification is recomputed.
            self.assertEqual(
                classified,
                db.execute(
                    "SELECT COUNT(*) FROM assessment_scores WHERE maturity_level_id IS NOT NULL"
                ).fetchone()[0],
            )
            record = db.execute(
                "SELECT metadata_json FROM audit_logs WHERE action='MATURITY_LABEL_RENAMED' ORDER BY id DESC LIMIT 1"
            ).fetchone()
            self.assertIsNotNone(record, "a stage rename must be audited")
            metadata = json.loads(record["metadata_json"])
            self.assertEqual("عشوائي", metadata["previous_label_ar"])
            self.assertEqual(current_label, metadata["new_label_ar"])
            self.assertFalse(metadata["scores_rewritten"])

    def test_product_status_and_scientific_status_are_separate(self):
        admin = self.login()
        versions = self.request("GET", "/api/instruments", token=admin)["versions"]
        current = next(item for item in versions if item["version"] == "0.4.0")
        # Publishing made the version operationally ACTIVE, but the scientific
        # claim stayed at the weakest value. One must never imply the other.
        self.assertEqual("ACTIVE", current["product_status"])
        self.assertEqual("EVIDENCE_INFORMED", current["scientific_status"])
        self.assertIsNone(current["scientific_status_changed_at"])

        payload = self.request("GET", "/api/public/maturity-levels")
        self.assertEqual("EVIDENCE_INFORMED", payload["model"]["scientific_status"])
        # No validation sentence is emitted below EMPIRICALLY_VALIDATED.
        self.assertIsNone(payload["model"]["validation_claim_ar"])

    def test_scientific_status_change_requires_authorisation_and_is_audited(self):
        admin = self.login()
        versions = self.request("GET", "/api/instruments", token=admin)["versions"]
        version_id = next(item for item in versions if item["version"] == "0.4.0")["id"]
        path = f"/api/instrument-versions/{version_id}/scientific-status"

        # A company administrator may not make an evidentiary claim.
        self.request("POST", "/api/auth/register", {
            "name": "مسؤول شركة", "email": "status-probe@example.test",
            "password": "StatusProbe2026", "organization_name": "منشأة اختبار الحالة",
            "service_consent": True,
        }, expected=201)
        company = self.login("status-probe@example.test", "StatusProbe2026")
        denied = self.request("PATCH", path, {
            "scientific_status": "EMPIRICALLY_VALIDATED", "rationale": "محاولة غير مصرح بها",
        }, token=company, expected=403)
        self.assertEqual("permission_denied", denied["error"])

        # An unknown value and a missing rationale are both refused.
        self.assertEqual("unsupported_scientific_status", self.request(
            "PATCH", path, {"scientific_status": "TOTALLY_PROVEN", "rationale": "x" * 20},
            token=admin, expected=422)["error"])
        self.assertEqual("scientific_status_rationale_required", self.request(
            "PATCH", path, {"scientific_status": "EXPERT_REVIEWED"},
            token=admin, expected=422)["error"])

        result = self.request("PATCH", path, {
            "scientific_status": "EXPERT_REVIEWED",
            "rationale": "اكتملت مراجعة لجنة الخبراء للبنود والأبعاد.",
        }, token=admin)
        self.assertEqual("EXPERT_REVIEWED", result["scientific_status"])
        self.assertEqual("EVIDENCE_INFORMED", result["previous_scientific_status"])

        # The product status is untouched by a scientific decision.
        versions = self.request("GET", "/api/instruments", token=admin)["versions"]
        updated = next(item for item in versions if item["id"] == version_id)
        self.assertEqual("ACTIVE", updated["product_status"])
        self.assertEqual("EXPERT_REVIEWED", updated["scientific_status"])

        from mcm import database
        with database.transaction() as db:
            record = db.execute(
                """SELECT user_id,metadata_json FROM audit_logs
                   WHERE action='instrument_scientific_status' ORDER BY id DESC LIMIT 1"""
            ).fetchone()
        self.assertIsNotNone(record, "a scientific status change must be audited")
        metadata = json.loads(record["metadata_json"])
        self.assertEqual("EVIDENCE_INFORMED", metadata["previous_scientific_status"])
        self.assertEqual("EXPERT_REVIEWED", metadata["new_scientific_status"])
        self.assertIn("لجنة الخبراء", metadata["rationale"])
        self.assertIsNotNone(record["user_id"], "the actor must be recorded")

        # Restore, so the ordering of other tests cannot depend on this one.
        self.request("PATCH", path, {
            "scientific_status": "EVIDENCE_INFORMED", "rationale": "إعادة الضبط بعد الاختبار.",
        }, token=admin)

    def test_instrument_specification_is_not_misrepresented_as_item_bank(self):
        admin = self.login()
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
        late_save = self.request(
            "POST",
            f"/api/participant/session/{participant_token}/answers",
            {"answers": participant_answers[:1]},
            expected=409,
        )
        self.assertIn(late_save["error"], {"assessment_locked", "participant_submission_locked"})
        self.request("GET", f"/api/results/{assessment_id}", token=owner)

    def test_real_research_data_requires_controller_and_contributor_consent(self):
        researcher = self.login()
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

    def test_legacy_global_dimension_constraint_is_migrated(self):
        db = sqlite3.connect(":memory:")
        db.row_factory = sqlite3.Row
        db.executescript("""
            CREATE TABLE instrument_versions(id INTEGER PRIMARY KEY, version TEXT);
            INSERT INTO instrument_versions VALUES (1,'0.3.0');
            CREATE TABLE dimensions(
              id INTEGER PRIMARY KEY, code TEXT NOT NULL UNIQUE, construct TEXT NOT NULL,
              name TEXT NOT NULL, version_id INTEGER, name_en TEXT, weight REAL DEFAULT 1,
              source_type TEXT, source_reference TEXT, sort_order INTEGER DEFAULT 0
            );
            INSERT INTO dimensions(id,code,construct,name,version_id) VALUES (1,'MCM01','MCM','قديم',1);
            CREATE TABLE memberships(user_id INTEGER, organization_id INTEGER, role TEXT);
        """)
        _migrate_legacy(db)
        db.execute("INSERT INTO dimensions(code,construct,name,version_id) VALUES ('MCM01','MCM','جديد',2)")
        self.assertEqual(2, db.execute("SELECT COUNT(*) FROM dimensions WHERE code='MCM01'").fetchone()[0])
        db.close()

    def test_direct_participant_flow_demographics_admin_and_no_sara_demo(self):
        public_config = self.request("GET", "/api/public-config")
        self.assertTrue(public_config["direct_participant_enabled"])
        self.assertNotIn("demo_email", public_config)
        missing_consent = self.request("POST", "/api/public/assessments", {
            "organization_name": "منشأة مباشرة", "sector": "التقنية", "firm_size": "SMALL",
            "employee_count": 25, "firm_age_years": 4, "business_model": "B2B", "region": "الرياض", "social_platform_count": 3,
            "social_team_size": 2, "regulated_sector": "NO",
            "respondent_role": "مدير تسويق", "service_consent": False,
        }, expected=422)
        self.assertEqual("service_consent_required", missing_consent["error"])
        created = self.request("POST", "/api/public/assessments", {
            "organization_name": "منشأة مباشرة", "sector": "التقنية", "firm_size": "SMALL",
            "employee_count": 25, "firm_age_years": 4, "business_model": "B2B", "region": "الرياض", "social_platform_count": 3,
            "social_team_size": 2, "regulated_sector": "NO",
            "respondent_role": "مدير تسويق", "service_consent": True, "research_consent": True,
        }, expected=201)
        participant = self.request("GET", f"/api/participant/session/{created['token']}")
        self.assertEqual(0, len(participant["responses"]))
        self.assertEqual(67, len(participant["items"]))
        self.assertEqual(12, sum(item["construct"] == "ENABLER" for item in participant["items"]))
        self.assertEqual(4, participant["context"]["firm_age_years"])
        self.assertEqual(25, participant["context"]["employee_count"])
        self.assertEqual("B2B", participant["context"]["business_model"])
        answers = [{"item_id": item["id"], "value": 4} for item in participant["items"]]
        answers[0] = {"item_id": participant["items"][0]["id"], "missing_type": "DONT_KNOW"}
        self.request("POST", f"/api/participant/session/{created['token']}/answers", {"answers": answers})
        result = self.request("POST", f"/api/participant/session/{created['token']}/submit", {})
        self.assertTrue(result["assessment_complete"])
        self.assertEqual("PROACTIVE_ADAPTIVE", result["scores"]["MCM"]["maturity_level"]["code"])
        self.assertEqual("استباقي / متكيّف", result["scores"]["MCM"]["maturity_level"]["label_ar"])
        self.assertEqual(
            ["ردّة فعل / عشوائي", "منظم أوليًا / مستجيب", "مدار / متكامل",
             "استباقي / متكيّف", "مستدام / ذكي / قابل للتوسع"],
            [level["label_ar"] for level in result["maturity_progression"]],
        )
        self.assertEqual("MCM_TO_SMCE_PROPOSED_POSITIVE_EFFECT", result["relationship"]["model"])
        self.assertEqual(4, len(result["dashboard"]["enablers"]["dimensions"]))
        self.assertEqual(5, len(result["dashboard"]["priorities"]))
        returning = self.request("GET", f"/api/participant/session/{created['token']}")
        self.assertIsNotNone(returning["result"])

        admin = self.login()
        users = self.request("GET", "/api/admin/users", token=admin)["users"]
        self.assertFalse(any(user["name"] == "سارة الحربي" or user["email"].lower() == "sara@example.com" for user in users))
        organizations = self.request("GET", "/api/organizations", token=admin)["organizations"]
        self.assertTrue(any(item["name"] == "منشأة مباشرة" for item in organizations))


class PostgresAdapterTests(unittest.TestCase):
    def test_sql_translation_and_hybrid_rows(self):
        query, returns_id = postgres_sql("SELECT '?' AS literal,id FROM users WHERE id=?")
        self.assertEqual("SELECT '?' AS literal,id FROM users WHERE id=%s", query)
        self.assertFalse(returns_id)

        query, returns_id = postgres_sql("INSERT OR IGNORE INTO users(email) VALUES (?)")
        self.assertIn("INSERT INTO users(email) VALUES (%s)", query)
        self.assertIn("ON CONFLICT DO NOTHING", query)
        self.assertTrue(query.endswith("RETURNING id"))
        self.assertTrue(returns_id)

        query, returns_id = postgres_sql("INSERT OR REPLACE INTO scores VALUES (?,?,?,?)")
        self.assertIn("ON CONFLICT (assessment_id,construct,dimension_code)", query)
        self.assertIn("score=EXCLUDED.score", query)
        self.assertFalse(returns_id)

        row = HybridRow(("id", "name"), (7, "منشأة"))
        self.assertEqual(7, row[0])
        self.assertEqual("منشأة", row["name"])
        self.assertEqual({"id": 7, "name": "منشأة"}, dict(row))
        self.assertEqual({"sslmode": "require"}, connection_security_options("postgresql://db.example/app"))
        self.assertEqual({}, connection_security_options("postgresql://db.example/app?sslmode=verify-full"))
        with self.assertRaises(ValueError):
            connection_security_options("postgresql://db.example/app?sslmode=disable")

    def test_supabase_vendor_query_parameter_is_stripped(self):
        # Supabase hands out pooler URLs ending in ?supa=base-pooler.x, which
        # libpq refuses with `invalid URI query parameter: "supa"`.
        base = "postgresql://user:pass@db.pooler.supabase.com:6543/postgres"
        self.assertEqual(base, normalize_database_url(f"{base}?supa=base-pooler.x"))
        self.assertEqual(
            f"{base}?sslmode=require",
            normalize_database_url(f"{base}?sslmode=require&supa=base-pooler.x"),
        )
        self.assertEqual(base, normalize_database_url(base))
        # A stripped vendor marker must not weaken the transport requirement.
        self.assertEqual(
            {"sslmode": "require"},
            connection_security_options(normalize_database_url(f"{base}?supa=base-pooler.x")),
        )

    def test_postgres_schema_matches_sqlite_surface(self):
        self.assertEqual(44, len(POSTGRES_TABLES))
        self.assertEqual(len(POSTGRES_TABLES), len(set(POSTGRES_TABLES)))
        self.assertNotIn("AUTOINCREMENT", POSTGRES_SCHEMA)
        self.assertNotIn(" BLOB", POSTGRES_SCHEMA)
        self.assertIn("GENERATED BY DEFAULT AS IDENTITY", POSTGRES_SCHEMA)
        self.assertIn("DEFAULT 'REAL'", POSTGRES_SCHEMA)
        self.assertNotIn("DEFAULT 'DOUBLE PRECISION'", POSTGRES_SCHEMA)
        self.assertIn("idx_participants_org_user", POSTGRES_SCHEMA)
        snapshot = (Path(__file__).resolve().parent.parent / "supabase/migrations/202608280001_mcm_platform.sql").read_text()
        self.assertIn(POSTGRES_SCHEMA.strip(), snapshot)


if __name__ == "__main__":
    unittest.main()
