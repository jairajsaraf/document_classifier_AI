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
for k in ("PRIMARY_LLM_MODEL", "USE_DUAL_VERIFICATION", "LLM_INPUT_MODE", "PROMPT_PII_HINTS",
          "PROMPT_FAIL_CLOSED", "PROMPT_WIDE_HS", "MAX_TOKENS"):
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


# ---------------------------------------------------------------- Phase 3 switches (docs/FEATURES.md)
def cited(text, page=None, quote=None):
    """A text block as the Citations API returns it: `citations` is None or a list of page locations."""
    cites = page and [SimpleNamespace(type="page_location", cited_text=quote, start_page_number=page,
                                      end_page_number=page + 1)]
    return SimpleNamespace(type="text", text=text, citations=cites)


def fake_api(clf, *replies, stop="end_turn"):
    """Replace the Anthropic call with canned replies (a dict = JSON text, a list = content blocks);
    return the request kwargs it received."""
    seen, queue = [], list(replies)

    def create(**kw):
        seen.append(kw)
        reply = queue.pop(0)
        blocks = reply if isinstance(reply, list) else [SimpleNamespace(type="text", text=json.dumps(reply))]
        return SimpleNamespace(content=blocks, stop_reason=stop)
    clf.anthropic_client = SimpleNamespace(messages=SimpleNamespace(create=create))
    return seen


def pdf_classifier(monkeypatch, mode):
    monkeypatch.setattr(settings, "LLM_INPUT_MODE", mode)
    clf = DocumentClassifier()
    fake_doc(clf, "Internal memo about staffing.")
    return clf


def test_prompt_switches(monkeypatch):
    def prompt():
        return PromptManager().generate_final_classification_prompt("doc text", {"pii_detected": True,
                                                                    "pii_types": ["ssn"], "severity": "high"},
                                                                    {"is_safe": True})
    # shipped defaults = the measured `combo` arm (docs/FEATURES.md)
    assert (settings.PROMPT_PII_HINTS, settings.PROMPT_FAIL_CLOSED, settings.PROMPT_WIDE_HS) == (False, True, True)
    monkeypatch.setattr(settings, "PROMPT_PII_HINTS", True)  # the Phase 2 prompt
    monkeypatch.setattr(settings, "PROMPT_FAIL_CLOSED", False)
    monkeypatch.setattr(settings, "PROMPT_WIDE_HS", False)
    base = prompt()
    assert "## PII Detection Results" in base and "Severity: high" in base
    assert "## Decision Rule" not in base and "safeguarding" not in base
    monkeypatch.setattr(settings, "PROMPT_PII_HINTS", False)  # F9: the model no longer sees the regex verdict
    assert "PII Detection" not in prompt() and "Severity: high" not in prompt()
    assert "## Content Safety Results" in prompt()
    monkeypatch.setattr(settings, "PROMPT_FAIL_CLOSED", True)
    assert "## Decision Rule" in prompt() and "assign Confidential" in prompt()
    monkeypatch.setattr(settings, "PROMPT_WIDE_HS", True)
    assert "child-protection or safeguarding" in prompt()


def test_pdf_structured_sends_pdf_and_schema_and_checks_quotes(monkeypatch):
    clf = pdf_classifier(monkeypatch, "pdf_structured")
    cite = {"page_number": 1, "evidence_type": "text", "relevance": "y"}
    seen = fake_api(clf, {**REPLY, "sensitivity": "confidential", "citations": [
        {**cite, "evidence_text": "memo about  STAFFING"}, {**cite, "evidence_text": "not on the page"},
        {**cite, "evidence_type": "image", "evidence_text": "label at the top centre of the drawing"}]})
    r = clf.classify_document(str(TC3), use_dual_verification=False)
    document, text = seen[0]["messages"][0]["content"]
    assert len(seen) == 1 and document["source"]["media_type"] == "application/pdf" and "citations" not in document
    assert "attached as a PDF" in text["text"] and "Internal memo about staffing" not in text["text"]
    schema = seen[0]["output_config"]["format"]["schema"]
    assert seen[0]["output_config"]["format"]["type"] == "json_schema" and "citations" in schema["required"]
    assert (r["status"], r["sensitivity"]) == ("completed", "Confidential")  # enum casing is not guaranteed
    assert [c.get("verified") for c in r["citations"]] == [True, False, None]  # an image region is not checkable


def test_pdf_citations_parses_lines_and_api_citations(monkeypatch):
    clf = pdf_classifier(monkeypatch, "pdf_citations")
    seen = fake_api(clf, [
        cited("sensitivity: Confidential\nunsafe: true\nconfidence: 0.8\nsummary: s\nreasoning: r\nevidence: "),
        cited("the memo is internal", page=1, quote="Internal memo about staffing."),
        cited("\nevidence: a drawing on page 2 shows a schematic")])
    r = clf.classify_document(str(TC3), use_dual_verification=False)
    document = seen[0]["messages"][0]["content"][0]
    assert document["citations"] == {"enabled": True} and "output_config" not in seen[0]  # the API rejects both
    assert (r["sensitivity"], r["unsafe"], r["confidence"]) == ("Confidential", True, 0.8)
    api, uncited = r["citations"]
    assert (api["page_number"], api["evidence_text"], api["source"], api["verified"]) == (
        1, "Internal memo about staffing.", "api", True)
    assert (uncited["page_number"], uncited["evidence_type"]) == (None, "uncited")


def test_pdf_citations_fails_without_a_sensitivity_line(monkeypatch):
    clf = pdf_classifier(monkeypatch, "pdf_citations")
    fake_api(clf, [cited("unsafe: false\nconfidence: 0.9")])
    assert clf.classify_document(str(TC3), use_dual_verification=False)["status"] == "failed"


def test_pdf_two_call_labels_then_cites(monkeypatch):
    clf = pdf_classifier(monkeypatch, "pdf_two_call")
    label = {k: REPLY[k] for k in ("sensitivity", "unsafe", "confidence", "summary", "reasoning")}
    seen = fake_api(clf, label, [cited("evidence: "), cited("internal", page=1, quote="Internal memo")])
    r = clf.classify_document(str(TC3), use_dual_verification=False)
    (doc1, _), (doc2, text2) = (kw["messages"][0]["content"] for kw in seen)
    assert "output_config" in seen[0] and "citations" not in doc1 and "cache_control" in doc1
    assert "citations" not in seen[0]["output_config"]["format"]["schema"]["properties"]
    assert "output_config" not in seen[1] and doc2["citations"] == {"enabled": True} and "cache_control" in doc2
    assert "sensitivity = Confidential, unsafe = True" in text2["text"]
    assert (r["sensitivity"], r["unsafe"]) == ("Confidential", True)
    assert [(c["page_number"], c["source"]) for c in r["citations"]] == [(1, "api")]


def test_pdf_shapes_apply_to_pdf_files_only(monkeypatch):
    clf = pdf_classifier(monkeypatch, "pdf_structured")
    seen = fake_api(clf, REPLY)
    assert clf.classify_document("scan.png", use_dual_verification=False)["status"] == "completed"
    assert isinstance(seen[0]["messages"][0]["content"], str) and "output_config" not in seen[0]


@pytest.mark.parametrize("stop", ["refusal", "max_tokens"])
def test_classifier_fails_on_refusal_or_truncation(stop):
    clf = DocumentClassifier()
    fake_doc(clf, "text")
    fake_api(clf, REPLY, stop=stop)
    r = clf.classify_document("x.pdf", use_dual_verification=False)
    assert r["status"] == "failed" and stop in r["error"]


# ---------------------------------------------------------------- API
@pytest.fixture
def client(monkeypatch):
    from fastapi.testclient import TestClient
    from backend import guard, main
    from backend.database import init_db
    init_db()
    guard.reset()
    monkeypatch.setattr(settings, "UPLOADS_PER_IP_PER_HOUR", 1000)  # the guard tests set their own limits
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
    doc = db.query(Document).filter_by(public_id=r.json()["document_id"]).one()
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


def test_ui_endpoints_serve_file_verified_flag_and_model(client):
    # Phase 4b: the document view loads the upload, shows whether each quote was found, names the model
    doc_id = upload(client, "memo.pdf").json()["document_id"]
    client.post(f"/api/documents/{doc_id}/classify")
    f = client.get(f"/api/documents/{doc_id}/file")
    assert f.status_code == 200 and f.content == b"%PDF-1.4 test"
    cites = client.get(f"/api/documents/{doc_id}").json()["citations"]
    assert [c["verified"] for c in cites if c["evidence_type"] == "text"] == [False]  # "x" is not in "Internal memo."
    assert client.get("/api/documents/999999/file").status_code == 404
    assert client.get("/api/documents/1/file").status_code == 404  # internal integer ids are not addressable
    # the served type comes from the extension, not the uploader's claimed type
    evil = client.post("/api/documents/upload", files={"file": ("x.pdf", b"<script>1</script>", "text/html")})
    served = client.get(f"/api/documents/{evil.json()['document_id']}/file")
    assert served.headers["content-type"] == "application/pdf"
    assert served.headers["x-content-type-options"] == "nosniff"
    assert client.get("/api").json()["model"] == settings.PRIMARY_LLM_MODEL


def test_document_list_pages_without_overlap(client):
    # PR #6 review: the queue reads every page, so skip/limit must not repeat or drop rows
    for i in range(3):
        upload(client, f"p{i}.pdf")
    total = client.get("/api/documents").json()["total"]
    ids = [d["id"] for skip in range(0, total, 2)
           for d in client.get("/api/documents", params={"skip": skip, "limit": 2}).json()["documents"]]
    assert len(ids) == total == len(set(ids))


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
    # the detail view serves the reviewed values too (PR #3 review), not the model's original
    got = client.get(f"/api/documents/{doc_id}").json()["classification"]
    assert (got["sensitivity"], got["unsafe"]) == ("Public", False)


# ---------------------------------------------------------------- Phase 5: deploy guard rails
def test_document_ids_are_unguessable(client):
    doc_id = upload(client, "memo.pdf").json()["document_id"]
    assert len(doc_id) == 32 and int(doc_id, 16) >= 0
    assert client.get(f"/api/documents/{doc_id}").json()["document"]["id"] == doc_id


def test_per_ip_upload_limit(client, monkeypatch):
    monkeypatch.setattr(settings, "UPLOADS_PER_IP_PER_HOUR", 2)
    assert [upload(client, f"a{i}.pdf").status_code for i in range(3)] == [200, 200, 429]


def test_global_daily_cap(client, monkeypatch):
    monkeypatch.setattr(settings, "UPLOADS_PER_DAY", 2)
    assert [upload(client, f"a{i}.pdf").status_code for i in range(3)] == [200, 200, 429]


def test_client_ip_header_separates_visitors(client, monkeypatch):
    monkeypatch.setattr(settings, "UPLOADS_PER_IP_PER_HOUR", 1)
    monkeypatch.setattr(settings, "CLIENT_IP_HEADER", "true-client-ip")
    def up(ip):
        return client.post("/api/documents/upload", files={"file": ("a.pdf", b"%PDF-1.4", "application/pdf")},
                           headers={"true-client-ip": ip, "x-forwarded-for": ip}).status_code
    assert [up("1.1.1.1"), up("2.2.2.2"), up("1.1.1.1")] == [200, 200, 429]
    # a client-supplied leading X-Forwarded-For entry cannot buy a fresh allowance: the last entry counts
    monkeypatch.setattr(settings, "CLIENT_IP_HEADER", "x-forwarded-for")
    assert [up("6.6.6.%d, 3.3.3.3" % i) for i in range(2)] == [200, 429]


def test_size_cap(client, monkeypatch):
    monkeypatch.setattr(settings, "MAX_FILE_SIZE_MB", 1)
    assert upload(client, "big.pdf", b"x" * (1024 * 1024 + 1)).status_code == 413
    assert upload(client, "ok.pdf", b"x" * 1024).status_code == 200


def test_storage_cap(client, monkeypatch):
    from backend.database import SessionLocal
    from backend.models import Document
    db = SessionLocal()
    used = sum(d.file_size for d in db.query(Document).all())
    db.close()
    mb = 1024 * 1024
    cap = -(-used // mb) + 1  # whole MB above what is stored
    monkeypatch.setattr(settings, "MAX_STORED_MB", cap)
    assert upload(client, "a.pdf", b"x" * (cap * mb - used - 1000)).status_code == 200  # fills the store to 1000 B short
    assert upload(client, "b.pdf", b"x" * 2000).status_code == 507


def test_page_cap(client, monkeypatch):
    import io
    from pypdf import PdfWriter
    def pdf(n):
        w, buf = PdfWriter(), io.BytesIO()
        for _ in range(n):
            w.add_blank_page(100, 100)
        w.write(buf)
        return buf.getvalue()
    monkeypatch.setattr(settings, "MAX_PDF_PAGES", 3)
    assert upload(client, "long.pdf", pdf(4)).status_code == 400
    assert upload(client, "short.pdf", pdf(3)).status_code == 200


def test_filename_is_cleaned(client):
    from backend.guard import clean_filename
    assert clean_filename("../../etc/pass wd.pdf") == "pass wd.pdf"
    assert clean_filename("a<b>&c.pdf") == "a_b__c.pdf"
    assert clean_filename("") == "document" and len(clean_filename("x" * 500)) == 100
    long_pdf = clean_filename("x" * 500 + ".pdf")  # truncation must not eat the extension (the UI needs it)
    assert long_pdf.endswith(".pdf") and len(long_pdf) == 100
    shown = client.get("/api/documents").json()["documents"]
    assert all("<" not in d["filename"] for d in shown)


def test_each_upload_is_classified_once(client):
    doc_id = upload(client, "memo.pdf").json()["document_id"]
    assert client.post(f"/api/documents/{doc_id}/classify").status_code == 200
    assert client.post(f"/api/documents/{doc_id}/classify").status_code == 409
    assert len(client.classify_calls) == 1


def test_approve_marks_document_reviewed(client):
    doc_id = upload(client, "memo.pdf").json()["document_id"]
    client.post(f"/api/documents/{doc_id}/classify")
    row = lambda: next(d for d in client.get("/api/documents").json()["documents"] if d["id"] == doc_id)
    assert (row()["status"], row()["requires_review"], row()["reviewed"]) == ("pending_review", True, False)
    r = client.post("/api/feedback", params={"document_id": doc_id, "feedback_type": "confirmation", "reviewer_name": "t"})
    assert r.status_code == 200, r.text
    assert (row()["status"], row()["requires_review"], row()["reviewed"]) == ("completed", False, True)
    assert row()["sensitivity"] == "Confidential"  # approving changes nothing else


def test_responses_are_gzipped(client):
    r = client.get("/openapi.json", headers={"accept-encoding": "gzip"})
    assert r.headers["content-encoding"] == "gzip"


def test_seed_loads_fixture_into_empty_database_only(monkeypatch, tmp_path):
    from backend import seed
    from backend.database import SessionLocal, init_db
    from backend.models import Document
    init_db()
    fixture = tmp_path / "seed.json"
    fixture.write_text(json.dumps([{
        "file": TC3.relative_to(ROOT).as_posix(),
        "document": {"filename": "TC3.pdf", "status": "pending_review", "requires_review": True, "page_count": 3,
                     "image_count": 0, "is_legible": True, "sensitivity": "Confidential", "unsafe": False, "confidence": 0.8},
        "classification": {"summary": "s", "reasoning": "r", "model": "m", "pii_detected": False, "content_safe": True},
        "citations": [{"page_number": 1, "evidence_type": "text", "evidence_text": "q", "description": "d", "verified": True}],
    }]), encoding="utf-8")
    monkeypatch.setattr(seed, "FIXTURE", fixture)
    db = SessionLocal()
    db.query(Document).delete()
    db.commit()
    assert seed.seed_if_empty(db) == 1
    assert seed.seed_if_empty(db) == 0  # already populated: a restart never duplicates or overwrites
    doc = db.query(Document).one()
    assert doc.original_filename == "TC3.pdf" and doc.primary_category.value == "Confidential"
    assert os.path.isfile(doc.file_path) and len(doc.public_id) == 32
    db.close()


def test_shipped_seed_fixture_is_consistent():
    fixture = ROOT / "backend" / "seed_data.json"
    if not fixture.exists():
        pytest.skip("no fixture exported yet")
    for item in json.loads(fixture.read_text(encoding="utf-8")):
        assert (ROOT / item["file"]).is_file()
        assert item["document"]["sensitivity"] in ("Public", "Confidential", "Highly Sensitive")
        assert item["classification"]["reasoning"] and item["citations"]


def test_pdf_pages_are_rendered_one_at_a_time(monkeypatch):
    # all pages at once (the old behaviour) got the process OOM-killed on a 512 MB instance
    from PIL import Image
    from backend.services import document_processor
    calls = []

    def fake(path, dpi, first_page, last_page):
        calls.append((first_page, last_page))
        return [Image.new("RGB", (10, 10))]
    monkeypatch.setattr(document_processor, "convert_from_path", fake)
    out = DocumentProcessor().process_document(str(TC3))
    assert calls == [(i, i) for i in range(1, out["page_count"] + 1)] and out["image_count"] == out["page_count"]


def test_database_from_before_phase_5_gets_public_ids(tmp_path):
    from sqlalchemy import create_engine, text
    from backend.database.db import _add_public_id
    eng = create_engine(f"sqlite:///{(tmp_path / 'old.db').as_posix()}")
    with eng.begin() as c:
        c.execute(text("CREATE TABLE documents (id INTEGER PRIMARY KEY, filename VARCHAR(255))"))
        c.execute(text("INSERT INTO documents (filename) VALUES ('a.pdf'), ('b.pdf')"))
    _add_public_id(eng)
    _add_public_id(eng)  # second start: nothing to do
    with eng.begin() as c:
        ids = [r[0] for r in c.execute(text("SELECT public_id FROM documents"))]
    assert len(ids) == 2 and len(set(ids)) == 2 and all(len(i) == 32 for i in ids)
