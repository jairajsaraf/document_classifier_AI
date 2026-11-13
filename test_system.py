"""System tests (pytest). No API key or network needed: the Anthropic call is faked.

Run in the project image (needs tesseract, poppler, libmagic):
    docker run --rm -v "$PWD":/app -v <empty-file>:/app/.env:ro -w /app docclf-eval:phase2 python -m pytest -q test_system.py
(the empty-file mount hides a real .env, which would override the defaults these tests check)
Known defects are pinned as xfail(strict=True) with their docs/FAILURES.md id, so a fix flips them red.
"""
import json
import os
import sys
import tempfile
from pathlib import Path
from types import SimpleNamespace

import pytest

ROOT = Path(__file__).resolve().parent
TMP = Path(tempfile.mkdtemp())
# settings are read at import time, so point the DB and upload dir at a temp dir first
os.environ.update(DATABASE_URL=f"sqlite:///{(TMP / 't.db').as_posix()}", UPLOAD_DIR=str(TMP / "uploads"),
                  ANTHROPIC_API_KEY="test-key-not-real", OPENAI_API_KEY="")
for k in ("PRIMARY_LLM_MODEL", "USE_DUAL_VERIFICATION"):
    os.environ.pop(k, None)
sys.path.insert(0, str(ROOT))

from backend.config import settings  # noqa: E402
from backend.services.classifier import DocumentClassifier  # noqa: E402
from backend.services.content_safety import ContentSafetyChecker  # noqa: E402
from backend.services.document_processor import DocumentProcessor  # noqa: E402
from backend.services.pii_detector import PIIDetector  # noqa: E402
from backend.services.prompt_manager import PromptManager  # noqa: E402

TC3 = ROOT / "HitachiDS_Datathon_Challenges_Package" / "TC3_Sample_Internal_Memo.pdf"
DOCX_UNSAFE = ("Unsafe Content: In any case all content should be evaluated for Child Safety and should not "
               "include Hate speech, exploitative, violent, criminal, political news or cyber-threat content.")
ORIG_CLASSIFY = DocumentClassifier.classify_document


# ---------------------------------------------------------------- helpers
def fake_llm(clf, reply):
    """Replace the Anthropic call; return the list of prompts it received."""
    prompts = []

    def create(**kw):
        prompts.append(kw["messages"][0]["content"])
        body = reply if isinstance(reply, str) else json.dumps(reply)
        return SimpleNamespace(content=[SimpleNamespace(type="text", text=body)])
    clf.anthropic_client = SimpleNamespace(messages=SimpleNamespace(create=create))
    return prompts


def fake_doc(clf, text):
    clf.doc_processor.process_document = lambda path: {
        "page_count": 1, "image_count": 0, "has_text": True, "is_legible": True, "legibility_score": 1.0,
        "pages": [{"page_number": 1, "text": text, "has_text": True, "images": []}], "file_info": {"size_mb": 0}}


REPLY = {"sensitivity": "Confidential", "unsafe": True, "confidence": 0.9, "summary": "s", "reasoning": "r",
         "citations": [{"page_number": 1, "evidence_type": "text", "evidence_text": "x", "relevance": "y"}]}


# ---------------------------------------------------------------- configuration and plumbing
def test_configuration_defaults():
    assert settings.PRIMARY_LLM_MODEL == "claude-haiku-5-5"
    # F4: on by default, every /classify call failed without an OpenAI key
    assert settings.USE_DUAL_VERIFICATION is False


def test_database_init_and_session():
    from sqlalchemy import inspect
    from backend.database.db import SessionLocal, engine, init_db
    init_db()
    db = SessionLocal()
    db.close()
    tables = set(inspect(engine).get_table_names())
    assert {"documents", "classifications", "citation_evidence", "feedback", "audit_logs"} <= tables


def test_document_processor_validates_and_extracts_pdf():
    proc = DocumentProcessor()
    ok = proc.validate_file(str(TC3))
    assert ok["valid"] and ok["file_info"]["extension"] == "pdf"
    bad = proc.validate_file(__file__)
    assert not bad["valid"] and any("Unsupported" in e for e in bad["errors"])
    content = proc.process_document(str(TC3))
    assert content["page_count"] == 3 and content["has_text"]


# ---------------------------------------------------------------- PII regex detector
def test_pii_detects_ssn_and_email():
    r = PIIDetector().detect_pii("Name: John Doe\nSSN: 912-45-6789\nEmail: john.doe@example.com\n", page_number=1)
    assert r["pii_detected"]
    assert {"ssn", "email"} <= set(r["pii_types"])
    ssn = next(d for d in r["detections"] if d["type"] == "ssn")
    assert "912-45-6789" not in ssn["context"]  # a detection's own value is redacted in its context


@pytest.mark.xfail(strict=True, reason="FAILURES.md F10: context keeps OTHER PII values unredacted")
def test_pii_context_redacts_neighbouring_pii():
    r = PIIDetector().detect_pii("SSN: 912-45-6789\nEmail: john.doe@example.com\n", page_number=1)
    assert all("912-45-6789" not in d["context"] for d in r["detections"])


@pytest.mark.xfail(strict=True, reason="FAILURES.md F8: card regex needs contiguous digits")
def test_pii_detects_spaced_card_number():
    r = PIIDetector().detect_pii("Card number: 4111 1111 1111 1111", page_number=1)
    assert "credit_card" in r["pii_types"]


@pytest.mark.xfail(strict=True, reason="FAILURES.md F7: SSN-shaped order IDs are flagged as SSNs")
def test_pii_ignores_ssn_shaped_order_id():
    r = PIIDetector().detect_pii("Your order ID is 917-42-3086. Track it online.", page_number=1)
    assert "ssn" not in r["pii_types"]


# ---------------------------------------------------------------- content safety regex
def test_content_safety_flags_and_passes():
    c = ContentSafetyChecker()
    assert c.check_content_safety("This is a marketing brochure for our new product line.", 1)["is_safe"]
    assert not c.check_content_safety("Instructions for violent activities and exploitation.", 1)["is_safe"]


@pytest.mark.xfail(strict=True, reason="FAILURES.md F9: keyword 'minor' raises a critical child_safety flag")
def test_content_safety_ignores_minor_changes():
    assert ContentSafetyChecker().check_content_safety("We made minor changes to the schedule.", 1)["is_safe"]


# ---------------------------------------------------------------- prompt
def test_prompt_uses_two_field_schema():
    pm = PromptManager()
    assert list(pm.get_category_definitions()) == ["Public", "Confidential", "Highly Sensitive"]
    p = pm.generate_final_classification_prompt("doc text", {"pii_detected": False}, {"is_safe": True})
    assert DOCX_UNSAFE in p
    assert '"sensitivity"' in p and '"unsafe"' in p and '"category"' not in p


# ---------------------------------------------------------------- classifier (LLM faked)
def test_classifier_returns_sensitivity_and_unsafe_together():
    clf = DocumentClassifier()
    fake_doc(clf, "Internal memo about staffing.")
    fake_llm(clf, REPLY)
    r = clf.classify_document("x.pdf", use_dual_verification=False)
    assert r["status"] == "completed"
    assert (r["sensitivity"], r["unsafe"]) == ("Confidential", True)
    assert "category" not in r
    assert r["hitl_decision"]["requires_hitl"]  # docx: "detect Unsafe content and flag for human review"


def test_critical_safety_hit_still_classified():
    # F5: a critical regex hit used to return category Unsafe and skip classification entirely
    clf = DocumentClassifier()
    fake_doc(clf, "Report on child abuse allegations at the facility. Customer SSN 912-45-6789.")
    prompts = fake_llm(clf, {**REPLY, "sensitivity": "Highly Sensitive"})
    r = clf.classify_document("x.pdf", use_dual_verification=False)
    assert len(prompts) == 1
    assert (r["status"], r["sensitivity"], r["unsafe"]) == ("completed", "Highly Sensitive", True)
    assert r["safety_results"]["is_safe"] is False  # regex signal kept as a secondary field


@pytest.mark.parametrize("raw,expected", [("yes", True), ("no", False), ("false", False), (False, False)])
def test_classifier_normalises_unsafe(raw, expected):
    clf = DocumentClassifier()
    fake_doc(clf, "text")
    fake_llm(clf, {**REPLY, "unsafe": raw})
    assert clf.classify_document("x.pdf", use_dual_verification=False)["unsafe"] is expected


@pytest.mark.parametrize("reply", ["not json at all", {**REPLY, "sensitivity": "Unsafe"}])
def test_classifier_fails_on_invalid_sensitivity(reply):
    clf = DocumentClassifier()
    fake_doc(clf, "text")
    fake_llm(clf, reply)
    assert clf.classify_document("x.pdf", use_dual_verification=False)["status"] == "failed"


# ---------------------------------------------------------------- API
@pytest.fixture
def client(monkeypatch):
    from fastapi.testclient import TestClient
    from backend import main
    from backend.database import init_db
    init_db()
    calls = []

    def classify(self, path, use_dual_verification=None):
        calls.append(path)
        fake_doc(self, "Internal memo.")
        fake_llm(self, REPLY)
        return ORIG_CLASSIFY(self, path, use_dual_verification)
    monkeypatch.setattr(DocumentClassifier, "classify_document", classify)
    c = TestClient(main.app)
    c.classify_calls = calls
    return c


def upload(client, name, body=b"%PDF-1.4 test"):
    return client.post("/api/documents/upload", files={"file": (name, body, "application/pdf")})


def files_outside(up):
    return {p.resolve() for p in list(TMP.rglob("*")) + list(Path("/tmp").glob("*escape*"))
            if p.is_file() and p.resolve().parent != up}


@pytest.mark.parametrize("name", ["../../escape.pdf", "..\\..\\escape.pdf", "/tmp/abs_escape.pdf",
                                  "a/../../../escape.pdf"])
def test_upload_keeps_client_filename_out_of_save_path(client, name):
    from backend.database import SessionLocal
    from backend.models import Document
    up = Path(settings.UPLOAD_DIR).resolve()
    before = files_outside(up)
    r = upload(client, name)
    assert r.status_code == 200, r.text
    db = SessionLocal()
    doc = db.get(Document, r.json()["document_id"])
    saved, original = Path(doc.file_path).resolve(), doc.original_filename
    db.close()
    assert saved.parent == up and saved.is_file() and saved.suffix == ".pdf"
    assert "escape" not in saved.name and "escape" in original  # client name kept only as data
    assert files_outside(up) - before == set()


def test_upload_rejects_disallowed_extension(client):
    assert upload(client, "run.sh").status_code == 400


def test_upload_does_not_classify(client):
    # F3: upload also ran a full background classification whose result was thrown away
    assert upload(client, "memo.pdf").status_code == 200
    assert client.classify_calls == []


def test_classify_saves_and_serves_two_fields(client):
    doc_id = upload(client, "memo.pdf").json()["document_id"]
    r = client.post(f"/api/documents/{doc_id}/classify")
    assert r.status_code == 200, r.text
    assert (r.json()["sensitivity"], r.json()["unsafe"], r.json()["requires_review"]) == ("Confidential", True, True)
    got = client.get(f"/api/documents/{doc_id}").json()
    assert (got["classification"]["sensitivity"], got["classification"]["unsafe"]) == ("Confidential", True)
    assert got["citations"]
    listed = {d["id"]: d for d in client.get("/api/documents").json()["documents"]}
    assert (listed[doc_id]["sensitivity"], listed[doc_id]["unsafe"]) == ("Confidential", True)


def test_classify_with_default_settings_and_no_openai_key(client):
    # the shipped path: classify_document is called without use_dual_verification and there is no OpenAI key
    doc_id = upload(client, "memo.pdf").json()["document_id"]
    r = client.post(f"/api/documents/{doc_id}/classify")
    assert r.status_code == 200 and r.json()["status"] != "failed", r.text


def test_feedback_overrides_both_fields(client):
    doc_id = upload(client, "memo.pdf").json()["document_id"]
    client.post(f"/api/documents/{doc_id}/classify")
    r = client.post("/api/feedback", params={"document_id": doc_id, "feedback_type": "correction",
                                              "reviewer_name": "t", "corrected_category": "Public",
                                              "corrected_unsafe": False})
    assert r.status_code == 200, r.text
    listed = {d["id"]: d for d in client.get("/api/documents").json()["documents"]}
    assert (listed[doc_id]["sensitivity"], listed[doc_id]["unsafe"]) == ("Public", False)
