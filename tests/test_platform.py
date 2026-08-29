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

    def setUp(self):
        # Every test speaks to the server from 127.0.0.1, so the per-IP spam
        # limiter would otherwise leak across unrelated cases. Production limits
        # stay as configured; only this shared-address artefact is reset.
        from mcm import api as api_module
        api_module._RATE_LIMITS.clear()

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

    def test_dimension_names_follow_the_instrument_everywhere(self):
        """A dimension rename must reach the database and the client.

        Seeding syncs maturity labels but did not sync dimension names, so a
        rename in the instrument left the interface showing the old wording.
        The client also held two hardcoded copies of the dimension lists.
        """
        payload = self.request("GET", "/api/public/maturity-levels")
        smce = {item["code"]: item for item in payload["dimensions"]["SMCE"]}
        self.assertEqual("وضوح وسلاسة التواصل", smce["SMCE04"]["name_ar"])
        # The code and the English name are identifying data and are unchanged.
        self.assertEqual("Low Communication Friction", smce["SMCE04"]["name_en"])
        self.assertEqual(7, len(payload["dimensions"]["MCM"]))
        self.assertEqual(5, len(payload["dimensions"]["SMCE"]))

        client = (Path(__file__).parents[1] / "app.js").read_text(encoding="utf-8")
        self.assertNotIn("انخفاض الاحتكاك", client)
        # No dimension name may be hardcoded in the client any more.
        for name in ("كفاءة الاستجابة والحل", "الحوكمة والتوجيه الاستراتيجي", "وضوح وسلاسة التواصل"):
            self.assertNotIn(name, client, "dimension names must come from the API")

        # The improvement-plan catalogue derives its labels from the instrument.
        from mcm.ai_plans import _SMCE_DIMENSIONS
        self.assertEqual("وضوح وسلاسة التواصل", _SMCE_DIMENSIONS["SMCE04"])

        from mcm import database
        with database.transaction() as db:
            stored = db.execute(
                """SELECT d.name,d.name_en FROM dimensions d
                   JOIN instrument_versions v ON v.id=d.version_id
                   WHERE d.code='SMCE04' AND v.version='0.4.0'"""
            ).fetchone()
        self.assertEqual("وضوح وسلاسة التواصل", stored["name"])
        self.assertEqual("Low Communication Friction", stored["name_en"])

    def test_diagnostic_rule_names_follow_the_configuration(self):
        """Rules are seeded once and were never updated afterwards.

        Like dimension names, a rename in the source would otherwise never
        reach the database the interface reads.
        """
        from mcm import database

        with database.transaction() as db:
            row = db.execute(
                """SELECT r.name_ar,r.dimensions,r.operator,r.threshold,r.severity
                   FROM diagnostic_rules r JOIN instrument_versions v ON v.id=r.version_id
                   WHERE r.code='COMMUNICATION_FRICTION' AND v.version='0.4.0'"""
            ).fetchone()
        self.assertEqual("خفض معوقات الاستجابة", row["name_ar"])
        # The measurement itself is untouched by a wording change.
        self.assertEqual("SMCE01:SMCE03", row["dimensions"])
        self.assertEqual("average_lt", row["operator"])
        self.assertEqual(55, row["threshold"])
        self.assertEqual("MEDIUM", row["severity"])

        for source in ("mcm/config.py", "app.js"):
            text = (Path(__file__).parents[1] / source).read_text(encoding="utf-8")
            self.assertNotIn("احتكاك في الاستجابة", text)

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

    def _direct_participant_assessment(self, name="منشأة الاستشارة"):
        created = self.request("POST", "/api/public/assessments", {
            "organization_name": name, "sector": "التقنية والاتصالات", "firm_size": "SMALL",
            "employee_count": 12, "firm_age_years": 3, "business_model": "B2B",
            "region": "الرياض", "social_platform_count": 3, "social_team_size": 2,
            "regulated_sector": "NO", "respondent_role": "مالك / مؤسس",
            "service_consent": True, "research_consent": True,
        }, expected=201)
        return created["token"], created["assessment_id"]

    def test_phone_numbers_are_stored_in_one_canonical_shape(self):
        token, assessment_id = self._direct_participant_assessment("منشأة تطبيع الهاتف")
        shapes = ["0501234567", "+966 50 123 4567", "00966501234567", "٠٥٠١٢٣٤٥٦٧"]
        stored = set()
        for index, shape in enumerate(shapes):
            result = self.request("POST", "/api/consultations", {
                "assessment_id": assessment_id, "participant_token": token,
                "full_name": "مالك المنشأة", "email": "phone-shapes@example.test",
                "phone_number": shape, "consent_to_contact": True,
            }, expected=201 if index == 0 else 200)
            stored.add(result["lead"]["phone_e164"])
        # Four spellings of one number must never become four rows or four
        # formats; the later submissions resolve to the same lead.
        self.assertEqual({"+966501234567"}, stored)

        self.assertEqual("invalid_phone_number", self.request("POST", "/api/consultations", {
            "assessment_id": assessment_id, "participant_token": token,
            "full_name": "مالك المنشأة", "email": "bad-phone@example.test",
            "phone_number": "abc", "consent_to_contact": True,
        }, expected=422)["error"])
        self.assertEqual("invalid_email", self.request("POST", "/api/consultations", {
            "assessment_id": assessment_id, "participant_token": token,
            "full_name": "مالك المنشأة", "email": "not-an-email",
            "phone_number": "0501112223", "consent_to_contact": True,
        }, expected=422)["error"])

    def test_consultation_consent_is_explicit_separate_and_versioned(self):
        token, assessment_id = self._direct_participant_assessment("منشأة الموافقات")
        base = {
            "assessment_id": assessment_id, "participant_token": token,
            "full_name": "مسؤول التسويق", "email": "consent@example.test",
            "phone_number": "0555000111",
        }
        # Contact consent is the lawful basis; without it nothing is stored.
        self.assertEqual("contact_consent_required", self.request(
            "POST", "/api/consultations", dict(base), expected=422)["error"])

        created = self.request("POST", "/api/consultations", dict(
            base, consent_to_contact=True,
            consultation_topics=["CUSTOMER_JOURNEY", "FULL_90_DAY_PLAN"],
            preferred_contact_method="WHATSAPP",
        ), expected=201)["lead"]
        # Marketing consent is a separate decision and defaults to off, even
        # though the participant granted research consent on the assessment.
        self.assertFalse(created["marketing_consent"])
        self.assertEqual("CONTACT_CONSENT_1.0", created["contact_consent_version"])
        self.assertEqual("PRIVACY_NOTICE_1.0", created["privacy_notice_version"])
        self.assertEqual(["CUSTOMER_JOURNEY", "FULL_90_DAY_PLAN"], created["consultation_topics"])

        self.assertEqual("unsupported_consultation_topic", self.request(
            "POST", "/api/consultations",
            dict(base, email="topics@example.test", consent_to_contact=True,
                 consultation_topics=["ANYTHING"]),
            expected=422)["error"])

        # Withdrawing consent stops contact and is recorded as an event.
        withdrawn = self.request("POST", f"/api/consultations/{created['id']}/consent", {
            "participant_token": token,
        })
        self.assertEqual("DO_NOT_CONTACT", withdrawn["status"])

        from mcm import database
        with database.transaction() as db:
            events = [row["event_type"] for row in db.execute(
                "SELECT event_type FROM consultation_lead_events WHERE consultation_lead_id=? ORDER BY id",
                (created["id"],),
            )]
            marketing_at = db.execute(
                "SELECT marketing_consent,marketing_consent_at FROM consultation_leads WHERE id=?",
                (created["id"],),
            ).fetchone()
        self.assertEqual(["CREATED", "CONSENT_WITHDRAWN"], events)
        self.assertEqual(0, marketing_at["marketing_consent"])
        self.assertIsNone(marketing_at["marketing_consent_at"])

    def test_results_stay_available_and_contact_data_never_reaches_research(self):
        token, assessment_id = self._direct_participant_assessment("منشأة عزل البيانات")
        session = self.request("GET", f"/api/participant/session/{token}")
        # The result and its details are reachable without ever submitting a
        # consultation request.
        self.assertEqual(67, len(session["items"]))

        self.request("POST", "/api/consultations", {
            "assessment_id": assessment_id, "participant_token": token,
            "full_name": "جهة الاتصال", "email": "isolation@example.test",
            "phone_number": "0533444555", "consent_to_contact": True,
            "notes": "ملاحظة خاصة بالطلب",
        }, expected=201)

        admin = self.login()
        for path in ("/api/research/dataset", "/api/research/summary", "/api/research/statistics"):
            serialized = json.dumps(self.request("GET", path, token=admin), ensure_ascii=False)
            for secret in ("isolation@example.test", "+966533444555", "0533444555", "جهة الاتصال"):
                self.assertNotIn(secret, serialized, f"{secret} leaked into {path}")

        from mcm import database
        from mcm.exports import build_research_sheets, spss_package
        with database.transaction() as db:
            sheets = build_research_sheets(db)
            package = spss_package(db)
        flattened = json.dumps(
            {name: [headers, rows] for name, (headers, rows) in sheets.items()},
            ensure_ascii=False, default=str,
        )
        for secret in ("isolation@example.test", "+966533444555", "جهة الاتصال", "ملاحظة خاصة بالطلب"):
            self.assertNotIn(secret, flattened, "contact data reached the research sheets")
            self.assertNotIn(secret.encode(), package, "contact data reached the SPSS package")

    def test_a_participant_cannot_read_another_participants_consultation(self):
        first_token, first_assessment = self._direct_participant_assessment("منشأة أولى")
        second_token, _ = self._direct_participant_assessment("منشأة ثانية")
        lead = self.request("POST", "/api/consultations", {
            "assessment_id": first_assessment, "participant_token": first_token,
            "full_name": "صاحب الطلب", "email": "owner@example.test",
            "phone_number": "0544333222", "consent_to_contact": True,
        }, expected=201)["lead"]

        self.request("GET", f"/api/consultations/{lead['id']}?participant_token={first_token}")
        # Another participant's token, and an anonymous caller, are both refused
        # the same way, without revealing that the lead exists.
        self.assertEqual("consultation_lead_not_found", self.request(
            "GET", f"/api/consultations/{lead['id']}?participant_token={second_token}",
            expected=404)["error"])
        self.assertEqual("consultation_lead_not_found", self.request(
            "GET", f"/api/consultations/{lead['id']}", expected=404)["error"])
        self.assertEqual("consultation_lead_not_found", self.request(
            "POST", f"/api/consultations/{lead['id']}/consent",
            {"participant_token": second_token}, expected=404)["error"])

    def test_privacy_notice_is_served_with_versioned_consent_texts(self):
        notice = self.request("GET", "/api/public/privacy")
        self.assertEqual("PRIVACY_NOTICE_1.0", notice["version"])
        self.assertEqual("CONTACT_CONSENT_1.0", notice["consent_texts"]["contact"]["version"])
        self.assertEqual("MARKETING_CONSENT_1.0", notice["consent_texts"]["marketing"]["version"])
        self.assertNotEqual(
            notice["consent_texts"]["contact"]["text_ar"],
            notice["consent_texts"]["marketing"]["text_ar"],
        )
        titles = [section["title_ar"] for section in notice["sections"]]
        for required in ("البيانات التي نجمعها", "أساس المعالجة", "الاحتفاظ", "حقوقك"):
            self.assertIn(required, titles)

    def test_interface_uses_western_digits(self):
        client = (Path(__file__).parents[1] / "app.js").read_text(encoding="utf-8")
        arabic_indic = [char for char in client if "٠" <= char <= "٩"]
        self.assertEqual([], arabic_indic, "Arabic-Indic digits still reach the interface")
        # Number and date formatting must not reintroduce them through a locale.
        self.assertIn("Intl.NumberFormat('en-US'", client)
        self.assertIn("nu-latn", client)

    def test_only_the_platform_administrator_may_delete_an_assessment(self):
        admin = self.login()
        _, assessment_id = self._direct_participant_assessment("منشأة الحذف")

        self.request("POST", "/api/auth/register", {
            "name": "مسؤول شركة للحذف", "email": "delete-probe@example.test",
            "password": "DeleteProbe2026", "organization_name": "منشأة فحص الحذف",
            "service_consent": True,
        }, expected=201)
        company = self.login("delete-probe@example.test", "DeleteProbe2026")
        self.assertEqual("permission_denied", self.request(
            "DELETE", f"/api/assessments/{assessment_id}", token=company, expected=403)["error"])

        from mcm import database
        with database.transaction() as db:
            before = db.execute("SELECT COUNT(*) FROM responses WHERE assessment_id=?", (assessment_id,)).fetchone()[0]
        result = self.request("DELETE", f"/api/assessments/{assessment_id}", token=admin)
        self.assertTrue(result["deleted"])

        with database.transaction() as db:
            self.assertIsNone(db.execute("SELECT id FROM assessments WHERE id=?", (assessment_id,)).fetchone())
            # No orphan may survive in any table keyed by the assessment.
            for table in ("responses", "assessment_context", "assessment_scores",
                          "dimension_scores", "score_runs", "roadmap_items",
                          "diagnostic_results", "consultation_leads"):
                self.assertEqual(0, db.execute(
                    f"SELECT COUNT(*) FROM {table} WHERE assessment_id=?", (assessment_id,)).fetchone()[0],
                    f"{table} kept an orphan row")
            record = db.execute(
                "SELECT metadata_json FROM audit_logs WHERE action='assessment_deleted' ORDER BY id DESC LIMIT 1"
            ).fetchone()
        self.assertIsNotNone(record, "an assessment deletion must be audited")
        metadata = json.loads(record["metadata_json"])
        # The audit entry records what was destroyed, since the rows are gone.
        self.assertEqual(before, metadata["deleted_rows"]["responses"])
        self.assertIn("organization_name", metadata)

    def test_memberships_are_managed_per_organisation_without_touching_the_account(self):
        admin = self.login()
        self.request("POST", "/api/auth/register", {
            "name": "عضو متعدد", "email": "multi-org@example.test",
            "password": "MultiOrgUser2026", "organization_name": "المؤسسة الأولى للعضويات",
            "service_consent": True,
        }, expected=201)
        users = self.request("GET", "/api/admin/users", token=admin)["users"]
        account = next(u for u in users if u["email"] == "multi-org@example.test")
        user_id = account["id"]
        first_org = account["memberships"][0]["organization_id"]

        # One account is one row, with its organisations nested. The previous
        # flat shape rendered the same person once per membership.
        self.assertEqual(1, sum(1 for u in users if u["email"] == "multi-org@example.test"))
        self.assertEqual(1, len(account["memberships"]))

        organizations = self.request("GET", "/api/admin/organizations", token=admin)["organizations"]
        second_org = next(o["id"] for o in organizations if o["id"] != first_org)
        self.request("PATCH", f"/api/admin/users/{user_id}", {
            "organization_id": second_org, "role": "CONSULTANT",
        }, token=admin)

        account = next(u for u in self.request("GET", "/api/admin/users", token=admin)["users"] if u["id"] == user_id)
        self.assertEqual(2, len(account["memberships"]))

        # Changing a role in one organisation leaves the other untouched.
        self.request("PATCH", f"/api/admin/users/{user_id}/memberships/{first_org}",
                     {"role": "COMPANY_RESPONDENT"}, token=admin)
        account = next(u for u in self.request("GET", "/api/admin/users", token=admin)["users"] if u["id"] == user_id)
        roles = {m["organization_id"]: m["role"] for m in account["memberships"]}
        self.assertEqual("COMPANY_RESPONDENT", roles[first_org])
        self.assertEqual("CONSULTANT", roles[second_org])

        self.assertEqual("invalid_role", self.request(
            "PATCH", f"/api/admin/users/{user_id}/memberships/{first_org}",
            {"role": "WIZARD"}, token=admin, expected=422)["error"])

        # Removing one membership keeps the account and its other membership.
        self.request("DELETE", f"/api/admin/users/{user_id}/memberships/{first_org}", token=admin)
        account = next(u for u in self.request("GET", "/api/admin/users", token=admin)["users"] if u["id"] == user_id)
        self.assertEqual([second_org], [m["organization_id"] for m in account["memberships"]])

        from mcm import database
        with database.transaction() as db:
            self.assertIsNotNone(db.execute("SELECT id FROM users WHERE id=?", (user_id,)).fetchone())
            record = db.execute(
                "SELECT metadata_json FROM audit_logs WHERE action='membership_removed' ORDER BY id DESC LIMIT 1"
            ).fetchone()
        self.assertIsNotNone(record, "a membership removal must be audited")
        self.assertFalse(json.loads(record["metadata_json"])["account_deleted"])

        self.assertEqual("membership_not_found", self.request(
            "DELETE", f"/api/admin/users/{user_id}/memberships/{first_org}",
            token=admin, expected=404)["error"])

    def test_the_last_platform_administrator_membership_cannot_be_removed(self):
        admin = self.login()
        me = self.request("GET", "/api/me", token=admin)["user"]
        account = next(u for u in self.request("GET", "/api/admin/users", token=admin)["users"] if u["id"] == me["id"])
        super_admin_orgs = [m["organization_id"] for m in account["memberships"] if m["role"] == "SUPER_ADMIN"]
        self.assertTrue(super_admin_orgs)

        # Removing them one at a time must stop before the platform is left
        # without an administrator, whether by removal or by demotion.
        for organization_id in super_admin_orgs[:-1]:
            self.request("DELETE", f"/api/admin/users/{me['id']}/memberships/{organization_id}", token=admin)
        last = super_admin_orgs[-1]
        # Tidying your own memberships keeps you signed in, moving the session
        # to a workspace you still belong to.
        self.assertEqual("SUPER_ADMIN", self.request("GET", "/api/me", token=admin)["user"]["role"])
        self.assertEqual("last_platform_administrator", self.request(
            "DELETE", f"/api/admin/users/{me['id']}/memberships/{last}", token=admin, expected=409)["error"])
        self.assertEqual("last_platform_administrator", self.request(
            "PATCH", f"/api/admin/users/{me['id']}/memberships/{last}",
            {"role": "COMPANY_RESPONDENT"}, token=admin, expected=409)["error"])
        # The account still works after the refusals.
        self.assertEqual("SUPER_ADMIN", self.request("GET", "/api/me", token=admin)["user"]["role"])

    def test_user_deletion_guards_the_platform_and_spares_organisation_data(self):
        admin = self.login()
        me = self.request("GET", "/api/me", token=admin)
        self.assertEqual("cannot_delete_own_account", self.request(
            "DELETE", f"/api/admin/users/{me['user']['id']}", token=admin, expected=409)["error"])

        self.request("POST", "/api/auth/register", {
            "name": "حساب للحذف", "email": "removable@example.test",
            "password": "RemovableUser2026", "organization_name": "منشأة الحساب المحذوف",
            "service_consent": True,
        }, expected=201)
        victim = self.login("removable@example.test", "RemovableUser2026")
        created = self.request("POST", "/api/assessments", {"assessment_type": "FULL"}, victim, 201)

        users = self.request("GET", "/api/admin/users", token=admin)["users"]
        user_id = next(u["id"] for u in users if u["email"] == "removable@example.test")
        self.request("DELETE", f"/api/admin/users/{user_id}", token=admin)

        from mcm import database
        with database.transaction() as db:
            self.assertIsNone(db.execute("SELECT id FROM users WHERE id=?", (user_id,)).fetchone())
            self.assertEqual(0, db.execute("SELECT COUNT(*) FROM memberships WHERE user_id=?", (user_id,)).fetchone()[0])
            self.assertEqual(0, db.execute("SELECT COUNT(*) FROM sessions WHERE user_id=?", (user_id,)).fetchone()[0])
            # The organisation's assessment survives the person's removal.
            self.assertIsNotNone(db.execute("SELECT id FROM assessments WHERE id=?", (created["id"],)).fetchone())
        # The deleted account's session no longer authenticates.
        self.request("GET", "/api/me", token=victim, expected=401)

    def _completed_direct_assessment(self, name):
        token, assessment_id = self._direct_participant_assessment(name)
        session = self.request("GET", f"/api/participant/session/{token}")
        self.request("POST", f"/api/participant/session/{token}/answers", {
            "answers": [{"item_id": item["id"], "value": 4} for item in session["items"]]
        })
        self.request("POST", f"/api/participant/session/{token}/submit", {})
        return token, assessment_id

    def test_only_the_platform_manager_grants_platform_roles(self):
        admin = self.login()
        self.request("POST", "/api/auth/register", {
            "name": "مدير شركة", "email": "company-owner@example.test",
            "password": "CompanyOwner2026", "organization_name": "منشأة الأدوار",
            "service_consent": True,
        }, expected=201)
        owner = self.login("company-owner@example.test", "CompanyOwner2026")
        # Self-registration produces a company account and nothing wider.
        self.assertEqual("COMPANY_ADMIN", self.request("GET", "/api/me", token=owner)["user"]["role"])

        self.request("POST", "/api/admin/users", {
            "name": "عضو", "email": "member@example.test", "password": "MemberPass2026",
            "role": "COMPANY_RESPONDENT", "organization_id": 1,
        }, token=admin, expected=201)
        users = self.request("GET", "/api/admin/users", token=admin)["users"]
        member_id = next(u["id"] for u in users if u["email"] == "member@example.test")

        # A company administrator may shape their own organisation's roles but
        # cannot mint a platform role of any kind.
        for platform_role in ("SUPER_ADMIN", "RESEARCHER", "CONSULTANT"):
            self.assertEqual("permission_denied", self.request(
                "POST", "/api/company/team",
                {"user_id": member_id, "role": platform_role},
                token=owner, expected=403)["error"])
        self.request("POST", "/api/company/team",
                     {"user_id": member_id, "role": "COMPANY_RESPONDENT"}, token=owner)

        # Creating accounts is the platform manager's action alone.
        self.assertEqual("permission_denied", self.request("POST", "/api/admin/users", {
            "name": "مساعد", "email": "assistant-probe@example.test",
            "password": "AssistantPass2026", "role": "CONSULTANT", "organization_id": 1,
        }, token=owner, expected=403)["error"])
        # And the manager can add assistants in any role.
        self.request("POST", "/api/admin/users", {
            "name": "مساعد المنصة", "email": "assistant@example.test",
            "password": "AssistantPass2026", "role": "CONSULTANT", "organization_id": 1,
        }, token=admin, expected=201)

    def test_participants_never_gain_an_account(self):
        token, assessment_id = self._direct_participant_assessment("منشأة المشارك بلا حساب")
        from mcm import database
        with database.transaction() as db:
            assessment = db.execute("SELECT organization_id FROM assessments WHERE id=?", (assessment_id,)).fetchone()
            participants = db.execute(
                "SELECT user_id FROM participants WHERE organization_id=?", (assessment["organization_id"],)
            ).fetchall()
            memberships = db.execute(
                """SELECT m.role,u.email FROM memberships m JOIN users u ON u.id=m.user_id
                   WHERE m.organization_id=?""",
                (assessment["organization_id"],),
            ).fetchall()
        # Taking the assessment creates a participant with a scoped session and
        # no user account, so answering can never become a route to one.
        self.assertTrue(participants)
        self.assertTrue(all(row["user_id"] is None for row in participants))
        # The one membership on the new organisation is the platform manager's
        # oversight, not the participant's.
        self.assertEqual(
            [("SUPER_ADMIN", "platform-admin@example.test")],
            [(row["role"], row["email"]) for row in memberships],
        )
        # The participant token reaches the assessment and nothing else.
        self.request("GET", "/api/me", expected=401)
        self.request("GET", "/api/admin/users", expected=401)

    def test_analysis_centre_describes_without_combining_constructs(self):
        admin = self.login()
        for index in range(3):
            self._completed_direct_assessment(f"منشأة التحليل {index}")

        payload = self.request("GET", "/api/analytics", token=admin)
        self.assertEqual("LATEST_PER_ORGANIZATION", payload["unit_of_analysis"])
        self.assertEqual("REAL", payload["data_origin"])
        self.assertGreaterEqual(payload["n"], 3)
        # Both constructs are described, separately, and never merged.
        self.assertTrue(payload["summary"]["mcm"]["n"])
        self.assertTrue(payload["summary"]["smce"]["n"])
        self.assertNotIn("combined", json.dumps(payload))
        for stats in (payload["summary"]["mcm"], payload["summary"]["smce"]):
            for field in ("mean", "median", "sd", "min", "max", "p25", "p75"):
                self.assertIn(field, stats)

        # A correlation below the configured minimum is withheld with a reason
        # rather than printed from a handful of points.
        self.assertFalse(payload["relationship"]["available"])
        self.assertEqual("SAMPLE_BELOW_MINIMUM", payload["relationship"]["reason"])
        self.assertIn("لا يثبت علاقة سببية", payload["relationship"]["causality_notice_ar"])

        # Groups smaller than the minimum are marked, not silently dropped.
        sectors = payload["groups"]["sector"]["groups"]
        self.assertTrue(sectors)
        self.assertTrue(all(group.get("suppressed") for group in sectors if group["n"] < payload["minimum_group_size"]))
        self.assertTrue(all("mcm" not in group for group in sectors if group.get("suppressed")))

        # Every context variable is related to each construct independently.
        variables = {item["variable"] for item in payload["associations"]}
        self.assertIn("employee_count", variables)
        for item in payload["associations"]:
            self.assertIn("with_mcm", item)
            self.assertIn("with_smce", item)

    def test_analysis_centre_access_and_name_disclosure(self):
        admin = self.login()
        self.request("POST", "/api/admin/users", {
            "name": "باحث التحليل", "email": "analyst@example.test",
            "password": "AnalystPass2026", "role": "RESEARCHER", "organization_id": 1,
        }, token=admin, expected=201)
        researcher = self.login("analyst@example.test", "AnalystPass2026")

        self.request("POST", "/api/auth/register", {
            "name": "شركة بلا تحليل", "email": "no-analytics@example.test",
            "password": "NoAnalytics2026", "organization_name": "منشأة بلا تحليل",
            "service_consent": True,
        }, expected=201)
        company = self.login("no-analytics@example.test", "NoAnalytics2026")

        self.assertEqual("permission_denied", self.request(
            "GET", "/api/analytics", token=company, expected=403)["error"])
        self.request("GET", "/api/analytics", expected=401)

        # A researcher may read the analysis, but organisation names are the
        # platform manager's view alone.
        analyst_view = self.request("GET", "/api/analytics", token=researcher)
        self.assertTrue(all(point["organization_name"] is None for point in analyst_view["scatter"]))
        manager_view = self.request("GET", "/api/analytics", token=admin)
        self.assertTrue(any(point["organization_name"] for point in manager_view["scatter"]))

        self.assertEqual("invalid_unit_of_analysis", self.request(
            "GET", "/api/analytics?mode=SOMETHING", token=admin, expected=422)["error"])

    def test_each_lead_appears_once_with_both_construct_scores(self):
        """A scored assessment must not split its lead into two board rows.

        Joining assessment_scores directly yields one row per construct; the
        earlier query grouped by the maturity label, which is present on the
        MCM row and NULL on the SMCE row, so every lead was listed twice and
        every status count was doubled.
        """
        token, assessment_id = self._completed_direct_assessment("منشأة صف واحد")
        self.request("POST", "/api/consultations", {
            "assessment_id": assessment_id, "participant_token": token,
            "full_name": "صاحب الطلب", "email": "single-row@example.test",
            "phone_number": "0501230001", "consent_to_contact": True,
        }, expected=201)

        admin = self.login()
        board = self.request("GET", "/api/admin/consultations", token=admin)
        mine = [lead for lead in board["leads"] if lead.get("email") == "single-row@example.test"]
        self.assertEqual(1, len(mine), "the lead was listed more than once")
        lead = mine[0]
        # Both constructs land on the one row, with the stage label from MCM.
        self.assertIsNotNone(lead["mcm_total"])
        self.assertIsNotNone(lead["smce_total"])
        self.assertTrue(lead["maturity_label"])
        # Counts must match the rows they summarise.
        self.assertEqual(len(board["leads"]), sum(board["counts"].values()))

    def test_a_consultant_works_only_the_leads_assigned_to_them(self):
        admin = self.login()
        token, assessment_id = self._completed_direct_assessment("منشأة الإسناد")
        lead = self.request("POST", "/api/consultations", {
            "assessment_id": assessment_id, "participant_token": token,
            "full_name": "صاحب الإسناد", "email": "assigned@example.test",
            "phone_number": "0501230002", "consent_to_contact": True,
        }, expected=201)["lead"]

        self.request("POST", "/api/admin/users", {
            "name": "مستشار الاختبار", "email": "consultant@example.test",
            "password": "ConsultantPass2026", "role": "CONSULTANT", "organization_id": 1,
        }, token=admin, expected=201)
        consultant = self.login("consultant@example.test", "ConsultantPass2026")

        # The board is reachable, but empty until something is assigned.
        board = self.request("GET", "/api/admin/consultations", token=consultant)
        self.assertEqual("ASSIGNED_TO_ME", board["scope"])
        self.assertEqual([], [item for item in board["leads"] if item["id"] == lead["id"]])
        # An unassigned lead is indistinguishable from a missing one.
        self.assertEqual("consultation_lead_not_found", self.request(
            "GET", f"/api/admin/consultations/{lead['id']}", token=consultant, expected=404)["error"])
        users = self.request("GET", "/api/admin/users", token=admin)["users"]
        consultant_id = next(u["id"] for u in users if u["email"] == "consultant@example.test")
        # Assigning an unassigned lead to themselves is refused as not-found,
        # not as forbidden, so the refusal does not confirm the lead exists.
        self.assertEqual("consultation_lead_not_found", self.request(
            "POST", f"/api/admin/consultations/{lead['id']}/assign",
            {"consultant_id": consultant_id}, token=consultant, expected=404)["error"])

        assigned = self.request("POST", f"/api/admin/consultations/{lead['id']}/assign",
                                {"consultant_id": consultant_id}, token=admin)
        self.assertEqual("ASSIGNED", assigned["status"])
        board = self.request("GET", "/api/admin/consultations", token=consultant)
        self.assertEqual([lead["id"]], [item["id"] for item in board["leads"]])
        # Now that it is visible to them, reassignment is refused on authority
        # rather than on existence.
        self.assertEqual("permission_denied", self.request(
            "POST", f"/api/admin/consultations/{lead['id']}/assign",
            {"consultant_id": consultant_id}, token=consultant, expected=403)["error"])
        # They can still do their own job on it.
        self.request("POST", f"/api/admin/consultations/{lead['id']}/status",
                     {"status": "CONTACTED", "note": "تم التواصل"}, token=consultant)

        # Creation notifies administrators only; the consultant is told when
        # the lead becomes theirs, so no notification points at a 404.
        from mcm import database
        with database.transaction() as db:
            rows = db.execute(
                """SELECT n.body FROM notifications n WHERE n.user_id=? AND n.type='CONSULTATION_LEAD'""",
                (consultant_id,),
            ).fetchall()
        self.assertEqual(1, len(rows))
        self.assertIn("أُسند", self.request("GET", "/api/notifications", token=consultant)["notifications"][0]["title"])

    def test_withdrawn_consent_withholds_contact_data_and_blocks_outreach(self):
        admin = self.login()
        token, assessment_id = self._completed_direct_assessment("منشأة السحب")
        lead = self.request("POST", "/api/consultations", {
            "assessment_id": assessment_id, "participant_token": token,
            "full_name": "صاحب السحب", "email": "withdrawn@example.test",
            "phone_number": "0501230003", "consent_to_contact": True,
        }, expected=201)["lead"]

        board = self.request("GET", "/api/admin/consultations", token=admin)
        before = next(item for item in board["leads"] if item["id"] == lead["id"])
        self.assertEqual("withdrawn@example.test", before["email"])

        self.request("POST", f"/api/consultations/{lead['id']}/consent", {"participant_token": token})

        board = self.request("GET", "/api/admin/consultations", token=admin)
        after = next(item for item in board["leads"] if item["id"] == lead["id"])
        # The lead stays visible so the team knows not to contact it, but the
        # details it no longer has a basis to hold are gone from the payload.
        self.assertEqual("DO_NOT_CONTACT", after["status"])
        self.assertIsNone(after.get("email"))
        self.assertIsNone(after.get("phone_e164"))
        self.assertEqual("CONTACT_CONSENT_WITHDRAWN", after["contact_withheld_reason"])
        self.assertFalse(after["consent_to_contact"])

        # Outreach transitions are refused; only closing remains available.
        self.assertEqual("contact_consent_withdrawn", self.request(
            "POST", f"/api/admin/consultations/{lead['id']}/status",
            {"status": "CONVERTED"}, token=admin, expected=409)["error"])
        self.request("POST", f"/api/admin/consultations/{lead['id']}/status",
                     {"status": "CLOSED", "closure_reason": "سحب الموافقة"}, token=admin)

        # Fulfilling the deletion request erases the details for good.
        self.request("DELETE", f"/api/admin/consultations/{lead['id']}", token=admin)
        board = self.request("GET", "/api/admin/consultations", token=admin)
        self.assertEqual([], [item for item in board["leads"] if item["id"] == lead["id"]])
        from mcm import database
        with database.transaction() as db:
            row = db.execute("SELECT email,phone_e164,deleted_at FROM consultation_leads WHERE id=?", (lead["id"],)).fetchone()
        self.assertEqual("", row["email"])
        self.assertEqual("", row["phone_e164"])
        self.assertIsNotNone(row["deleted_at"])

    def test_board_filters_narrow_results_without_widening_scope(self):
        admin = self.login()
        token, assessment_id = self._completed_direct_assessment("منشأة الفلاتر")
        lead = self.request("POST", "/api/consultations", {
            "assessment_id": assessment_id, "participant_token": token,
            "full_name": "صاحب الفلاتر", "email": "filters@example.test",
            "phone_number": "0501230004", "consent_to_contact": True,
            "consultation_topics": ["INFORMATION_GOVERNANCE"],
        }, expected=201)["lead"]

        matched = self.request("GET", "/api/admin/consultations?status=NEW&topic=INFORMATION_GOVERNANCE", token=admin)
        self.assertIn(lead["id"], [item["id"] for item in matched["leads"]])
        self.assertEqual({"status": "NEW", "topic": "INFORMATION_GOVERNANCE"}, matched["filters"])

        missed = self.request("GET", "/api/admin/consultations?topic=CUSTOMER_JOURNEY&status=CONVERTED", token=admin)
        self.assertNotIn(lead["id"], [item["id"] for item in missed["leads"]])
        # Counts describe the filtered set, not the whole table.
        self.assertEqual(len(missed["leads"]), sum(missed["counts"].values()))
        self.assertEqual("invalid_filter", self.request(
            "GET", "/api/admin/consultations?assigned_consultant_id=abc", token=admin, expected=422)["error"])

    def test_consultation_admin_screen_is_restricted_and_reads_scores_from_the_assessment(self):
        token, assessment_id = self._direct_participant_assessment("منشأة لوحة الاستشارات")
        self.request("POST", "/api/consultations", {
            "assessment_id": assessment_id, "participant_token": token,
            "full_name": "طالب الاستشارة", "email": "board@example.test",
            "phone_number": "0566777888", "consent_to_contact": True,
            "consultation_topics": ["MEASUREMENT_AND_LEARNING"],
        }, expected=201)

        admin = self.login()
        board = self.request("GET", "/api/admin/consultations", token=admin)
        lead = next(item for item in board["leads"] if item["email"] == "board@example.test")
        self.assertEqual("NEW", lead["status"])
        self.assertIsNone(lead["assigned_consultant_id"])
        # Counts are aggregates over every lead in the database, so assert the
        # relationship rather than a figure another test could move.
        self.assertGreaterEqual(board["unassigned"], 1)
        self.assertEqual(
            sum(1 for item in board["leads"] if not item["assigned_consultant_id"]),
            board["unassigned"],
        )
        # Scores come from the linked assessment, not from a field on the lead.
        self.assertIn("mcm_total", lead)
        self.assertEqual(["MEASUREMENT_AND_LEARNING"], lead["consultation_topics"])

    def test_results_navigation_states_and_dashboard_alias(self):
        client = (Path(__file__).parents[1] / "app.js").read_text(encoding="utf-8")
        shell = (Path(__file__).parents[1] / "index.html").read_text(encoding="utf-8")
        # The participant navigation item and the mobile bar both point at the
        # results route, in both the sidebar and the compact navigation.
        self.assertIn('href="#results" data-route="results"', shell)
        self.assertIn('<a href="#results">النتائج</a>', shell)
        # Anything still aiming at a dashboard route resolves to the results
        # page rather than falling through to "page not found".
        self.assertIn("if (route.parts[0] === 'dashboard') return navigate('results/latest');", client)
        # Both empty states are explicit, each with its own call to action.
        self.assertIn("لم تكمل أي تقييم حتى الآن.", client)
        self.assertIn("ابدأ التقييم", client)
        self.assertIn("لديك تقييم غير مكتمل.", client)
        self.assertIn("استكمال التقييم", client)
        self.assertNotIn("BETA", shell)

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

    def test_participant_session_is_scoped_and_submission_is_one_time(self):
        """The invariants that used to be reached through an invitation.

        Entry is direct now, so the participant session comes from the public
        start endpoint; the guarantees it must uphold are unchanged.
        """
        participant_token, assessment_id = self._direct_participant_assessment("منشأة جلسة المشارك")
        other_token, other_assessment = self._direct_participant_assessment("منشأة أخرى للجلسة")

        participant = self.request("GET", f"/api/participant/session/{participant_token}")
        self.assertEqual(assessment_id, participant["assessment"]["id"])
        answers = [{"item_id": item["id"], "value": 4} for item in participant["items"]]
        self.request("POST", f"/api/participant/session/{participant_token}/answers", {"answers": answers})
        submitted = self.request("POST", f"/api/participant/session/{participant_token}/submit", {})
        self.assertTrue(submitted["assessment_complete"])

        # Submission is one-time and the session becomes read-only.
        locked = self.request("POST", f"/api/participant/session/{participant_token}/submit", {}, expected=409)
        self.assertIn(locked["error"], {"assessment_locked", "participant_submission_locked"})
        late_save = self.request(
            "POST", f"/api/participant/session/{participant_token}/answers",
            {"answers": answers[:1]}, expected=409,
        )
        self.assertIn(late_save["error"], {"assessment_locked", "participant_submission_locked"})

        # A session reaches its own assessment and no other.
        self.assertEqual(other_assessment, self.request(
            "GET", f"/api/participant/session/{other_token}")["assessment"]["id"])
        self.assertEqual("participant_session_invalid", self.request(
            "GET", "/api/participant/session/not-a-real-token", expected=401)["error"])

    def test_participant_account_is_optional_and_claims_the_anonymous_result(self):
        token, assessment_id = self._completed_direct_assessment("منشأة الحساب الاختياري")
        # The result is reachable before any account exists.
        self.assertTrue(self.request("GET", f"/api/participant/session/{token}")["result"])

        created = self.request("POST", "/api/participant/account", {
            "full_name": "مشارك بحساب", "email": "participant-account@example.test",
            "password": "ParticipantPass2026", "participant_token": token,
        }, expected=201)
        self.assertEqual("COMPANY_RESPONDENT", created["user"]["role"])
        self.assertEqual(assessment_id, created["claimed_assessment_id"])

        # Signed in, the participant reaches their own result and roadmap.
        account = created["token"]
        self.assertEqual("COMPANY_RESPONDENT", self.request("GET", "/api/me", token=account)["user"]["role"])
        self.assertEqual(assessment_id, self.request("GET", f"/api/results/{assessment_id}", token=account)["assessment_id"])
        self.request("GET", f"/api/roadmap/{assessment_id}", token=account)

        # A participant account is a company account and can never be more.
        self.assertEqual("permission_denied", self.request(
            "GET", "/api/admin/users", token=account, expected=403)["error"])
        self.assertEqual("permission_denied", self.request(
            "GET", "/api/analytics", token=account, expected=403)["error"])
        self.assertEqual("permission_denied", self.request(
            "POST", "/api/admin/users", {"name": "x", "email": "x@example.test",
                                         "password": "XxPassword2026", "role": "SUPER_ADMIN"},
            token=account, expected=403)["error"])

    def test_registration_adds_depth_without_withholding_the_result(self):
        """The account must open more, never gate what was already shown."""
        token, assessment_id = self._completed_direct_assessment("منشأة العمق")
        anonymous = self.request("GET", f"/api/participant/session/{token}")["result"]
        # The anonymous participant already receives the complete payload.
        self.assertTrue(anonymous["scores"]["MCM"]["total"])
        self.assertEqual(7, len(anonymous["scores"]["MCM"]["dimensions"]))
        self.assertEqual(5, len(anonymous["scores"]["SMCE"]["dimensions"]))
        self.assertTrue(anonymous["dashboard"]["roadmap"])
        self.assertTrue(anonymous["dashboard"]["priorities"])

        account = self.request("POST", "/api/participant/account", {
            "full_name": "مشارك العمق", "email": "depth@example.test",
            "password": "DepthParticipant2026", "participant_token": token,
        }, expected=201)["token"]

        # The signed-in view is the same result, unchanged.
        signed_in = self.request("GET", f"/api/results/{assessment_id}", token=account)
        self.assertEqual(anonymous["scores"]["MCM"]["total"], signed_in["scores"]["MCM"]["total"])

        # Every surface the offer names must actually answer.
        for path in (
            f"/api/results/{assessment_id}/dimensions/MCM01",
            f"/api/diagnostics/{assessment_id}",
            f"/api/gaps/{assessment_id}",
            f"/api/benchmark/{assessment_id}",
            "/api/history",
        ):
            self.request("GET", path, token=account)
        # Including the report, which used to be refused to a participant.
        report = self.request("POST", "/api/reports", {
            "assessment_id": assessment_id, "report_type": "EXECUTIVE",
        }, token=account, expected=201)
        pdf, _ = self.request("GET", report["download_url"], token=account, raw=True)
        self.assertTrue(pdf.startswith(b"%PDF-1.4"))

        # A participant still reaches only their own assessment.
        _, other_assessment = self._completed_direct_assessment("منشأة أخرى للعمق")
        self.assertEqual("assessment_not_found", self.request(
            "GET", f"/api/results/{other_assessment}", token=account, expected=404)["error"])

    def test_knowledge_base_is_empty_until_the_researcher_writes_it(self):
        admin = self.login()
        # The public page shows nothing rather than generated filler.
        public = self.request("GET", "/api/public/knowledge")
        self.assertEqual(0, sum(len(items) for items in public["constructs"].values()))
        self.assertFalse(public["complete"])

        # The authoring view lists every dimension with empty fields.
        editor = self.request("GET", "/api/research/knowledge", token=admin)
        self.assertEqual(20, editor["dimension_count"])
        self.assertEqual(0, editor["written_count"])
        entry = editor["constructs"]["MCM"][0]
        self.assertEqual({"definition", "why_it_matters", "improving_looks_like", "indicators"},
                         set(entry["content"]))
        self.assertTrue(all(value == "" for value in entry["content"].values()))
        self.assertFalse(entry["written"])

        saved = self.request("PATCH", "/api/research/knowledge/MCM01", {
            "definition": "تعريف كتبه الباحث.", "why_it_matters": "سبب أهميته.",
        }, token=admin)
        self.assertEqual("تعريف كتبه الباحث.", saved["content"]["definition"])
        # A field left out of the request is preserved, not blanked.
        self.request("PATCH", "/api/research/knowledge/MCM01", {"indicators": "مؤشر."}, token=admin)
        again = self.request("GET", "/api/research/knowledge", token=admin)
        written = next(item for item in again["constructs"]["MCM"] if item["code"] == "MCM01")
        self.assertEqual("تعريف كتبه الباحث.", written["content"]["definition"])
        self.assertEqual("مؤشر.", written["content"]["indicators"])
        self.assertEqual("", written["content"]["improving_looks_like"])

        # Now the public page shows the written dimension and only that one.
        public = self.request("GET", "/api/public/knowledge")
        self.assertEqual(["MCM01"], [item["code"] for item in public["constructs"]["MCM"]])

        # Authoring is the researcher's, not a participant's.
        self.request("POST", "/api/auth/register", {
            "name": "شركة بلا تحرير", "email": "no-knowledge@example.test",
            "password": "NoKnowledge2026", "organization_name": "منشأة بلا تحرير",
            "service_consent": True,
        }, expected=201)
        company = self.login("no-knowledge@example.test", "NoKnowledge2026")
        self.assertEqual("permission_denied", self.request(
            "PATCH", "/api/research/knowledge/MCM01", {"definition": "تحرير غير مصرح"},
            token=company, expected=403)["error"])
        self.assertEqual("dimension_not_found", self.request(
            "PATCH", "/api/research/knowledge/NOPE", {"definition": "x"},
            token=admin, expected=404)["error"])

    def test_colleagues_join_one_assessment_through_a_shared_code(self):
        owner = self.login()
        created = self.request("POST", "/api/assessments", {"assessment_type": "FULL"}, owner, 201)
        assessment_id = created["id"]

        issued = self.request("POST", f"/api/assessments/{assessment_id}/join-code", {}, owner, 201)["join_code"]
        code = issued["code"]
        # Read aloud and retyped, so the alphabet excludes look-alike glyphs.
        self.assertNotRegex(code, r"[OI01]")
        # Re-issuing returns the live code rather than piling up new ones.
        self.assertEqual(code, self.request(
            "POST", f"/api/assessments/{assessment_id}/join-code", {}, owner, 201)["join_code"]["code"])

        joined = self.request("POST", "/api/participant/join", {
            "code": code.lower(), "full_name": "زميل في المنشأة",
            "job_title": "أخصائي تسويق", "service_consent": True,
        }, expected=201)
        # The colleague answers the same assessment, not a new one.
        self.assertEqual(assessment_id, joined["assessment_id"])
        session = self.request("GET", f"/api/participant/session/{joined['token']}")
        self.assertEqual(assessment_id, session["assessment"]["id"])

        self.assertEqual("service_consent_required", self.request(
            "POST", "/api/participant/join",
            {"code": code, "full_name": "بلا موافقة"}, expected=422)["error"])
        self.assertEqual("join_code_invalid_or_expired", self.request(
            "POST", "/api/participant/join",
            {"code": "ZZZZ-ZZZZ", "full_name": "كود خاطئ", "service_consent": True},
            expected=404)["error"])

    def test_one_assessment_per_organisation_each_cycle(self):
        from mcm import database

        self.request("POST", "/api/auth/register", {
            "name": "صاحب الدورة", "email": "cycle@example.test", "password": "CycleOwner2026",
            "organization_name": "منشأة دورة القياس", "service_consent": True,
        }, expected=201)
        owner = self.login("cycle@example.test", "CycleOwner2026")
        first = self.request("POST", "/api/assessments", {"assessment_type": "FULL"}, owner, 201)

        blocked = self.request("POST", "/api/assessments", {"assessment_type": "FULL"}, owner, expected=409)
        self.assertEqual("assessment_cooldown_active", blocked["error"])
        self.assertEqual(90, blocked["details"]["days"])
        self.assertEqual(first["id"], blocked["details"]["previous_assessment_id"])
        self.assertGreater(blocked["details"]["days_remaining"], 0)

        # A colleague joining the existing assessment adds a respondent and is
        # never treated as starting a new cycle.
        code = self.request("POST", f"/api/assessments/{first['id']}/join-code", {}, owner, 201)["join_code"]["code"]
        self.request("POST", "/api/participant/join", {
            "code": code, "full_name": "زميل داخل الدورة", "service_consent": True,
        }, expected=201)

        # Once the window has passed the next cycle opens.
        with database.transaction() as db:
            db.execute("UPDATE assessments SET created_at=? WHERE id=?",
                       (int(__import__("time").time()) - 91 * 86_400, first["id"]))
        self.request("POST", "/api/assessments", {"assessment_type": "FULL"}, owner, 201)

    def test_the_invitation_system_is_gone(self):
        owner = self.login()
        # Every invitation endpoint is removed, not merely hidden in the client.
        for method, path, body in (
            ("GET", "/api/invitations", None),
            ("POST", "/api/invitations", {"assessment_id": 1, "email": "x@example.test"}),
            ("GET", "/api/invitations/sometoken", None),
            ("POST", "/api/invitations/sometoken/accept", {"service_consent": True}),
        ):
            response = self.request(method, path, body, token=owner, expected=404)
            self.assertEqual("route_not_found", response["error"])

        client = (Path(__file__).parents[1] / "app.js").read_text(encoding="utf-8")
        shell = (Path(__file__).parents[1] / "index.html").read_text(encoding="utf-8")
        for banned in ("رمز الدعوة", "لدي دعوة", "invitation-token-form", "accept-invitation-form", "invite-form"):
            self.assertNotIn(banned, client)
            self.assertNotIn(banned, shell)
        # The participants screen now reports who actually answered.
        self.assertIn("/api/participants", client)
        participants = self.request("GET", "/api/participants", token=owner)
        self.assertIn("participants", participants)

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

    def test_every_generated_id_table_returns_its_id_on_postgres(self):
        """Guard the trap that broke consultation lead creation.

        A table with a generated id that is missing from IDENTITY_TABLES works
        on SQLite and returns lastrowid=None on PostgreSQL, surfacing only as a
        foreign-key violation in a later statement. The set is derived from the
        schema; this asserts the derivation actually covers every such table.
        """
        from mcm.database import SCHEMA
        from mcm.postgres import IDENTITY_TABLES, identity_tables_from_schema

        derived = identity_tables_from_schema(SCHEMA)
        self.assertEqual(derived, set(IDENTITY_TABLES))
        for table in ("consultation_leads", "consultation_lead_events", "assessments", "users"):
            self.assertIn(table, IDENTITY_TABLES)
            query, returns_id = postgres_sql(f"INSERT INTO {table}(x) VALUES (?)")
            self.assertTrue(returns_id, f"{table} must return its generated id")
            self.assertTrue(query.endswith("RETURNING id"))

    def test_grid_children_without_a_span_have_a_default_width(self):
        """Guard the layout bug that squeezed the priorities page.

        `.card-grid` is a twelve-column grid. A child with no `span-*` class
        occupies one column and renders as an unreadable sliver, which is what
        happened to the priorities, diagnoses and notifications pages. The
        stylesheet must give such children a default, at every breakpoint.
        """
        css = (Path(__file__).parents[1] / "platform.css").read_text(encoding="utf-8")
        default_rule = '.card-grid > .card:not([class*="span-"])'
        self.assertIn(default_rule, css)
        # One base rule plus one per responsive breakpoint that remaps spans.
        self.assertEqual(3, css.count(default_rule))
        breakpoints = css.count(".span-4 { grid-column: span 6; }") + css.count(
            ".span-3, .span-4, .span-5, .span-6, .span-7, .span-8, .span-12 { grid-column: 1; }")
        self.assertEqual(2, breakpoints, "a breakpoint remaps spans without remapping the default")

    def test_client_script_is_syntactically_valid(self):
        """Parse app.js with a real JavaScript engine.

        The project has no Node toolchain, so a broken client would otherwise
        only surface in a browser. macOS ships a JS engine through osascript;
        `new Function(source)` parses without executing. Where no engine is
        available the check skips rather than giving false assurance.
        """
        import shutil
        import subprocess

        if not shutil.which("osascript"):
            self.skipTest("no JavaScript engine available on this platform")
        client = Path(__file__).resolve().parents[1] / "app.js"
        script = (
            "ObjC.import('Foundation');\n"
            f"var src = ObjC.unwrap($.NSString.stringWithContentsOfFileEncodingError('{client}', $.NSUTF8StringEncoding, null));\n"
            "try {{ new Function(src); 'OK'; }} catch (e) {{ 'ERROR: ' + e.message; }}"
        ).replace("{{", "{").replace("}}", "}")
        completed = subprocess.run(
            ["osascript", "-l", "JavaScript", "-e", script],
            capture_output=True, text=True, timeout=60,
        )
        self.assertEqual(0, completed.returncode, completed.stderr)
        self.assertEqual("OK", completed.stdout.strip(), completed.stdout)

    def test_postgres_schema_matches_sqlite_surface(self):
        self.assertEqual(47, len(POSTGRES_TABLES))
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
