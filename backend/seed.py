"""Seed the queue with real classification results so a fresh (or just-woken) instance is never empty.

Load:    seed_if_empty(db) runs on boot, copies each PDF into UPLOAD_DIR and inserts the stored results.
Refresh: python -m backend.seed export http://localhost:8000 out.json file.pdf [file.pdf ...]
         classifies the files once through a running instance and writes the fixture (costs API calls).
Fixture: backend/seed_data.json, produced by the export command, never hand-edited.
"""
import json
import os
import shutil
import sys
import uuid
from datetime import datetime
from pathlib import Path

from backend.config import settings
from backend.models import CitationEvidence, Classification, ClassificationCategory, Document, DocumentStatus

ROOT = Path(__file__).resolve().parent.parent
FIXTURE = Path(__file__).resolve().parent / "seed_data.json"


def seed_if_empty(db) -> int:
    """Insert the fixture into an empty database; returns the number of documents added."""
    if not FIXTURE.exists() or db.query(Document).count():
        return 0
    items = json.loads(FIXTURE.read_text(encoding="utf-8"))
    for item in items:
        src = ROOT / item["file"]
        dest = os.path.join(settings.UPLOAD_DIR, f"{uuid.uuid4().hex}.pdf")
        shutil.copyfile(src, dest)
        d, c = item["document"], item["classification"]
        now = datetime.utcnow()
        doc = Document(
            filename=os.path.basename(dest), original_filename=d["filename"], file_path=dest,
            file_size=os.path.getsize(dest), mime_type="application/pdf", status=DocumentStatus(d["status"]),
            page_count=d["page_count"], image_count=d["image_count"], is_legible=d["is_legible"], has_text=True,
            primary_category=ClassificationCategory(d["sensitivity"]), unsafe=d["unsafe"],
            confidence_score=d["confidence"], requires_review=d["requires_review"],
            processing_started_at=now, processing_completed_at=now,
        )
        db.add(doc)
        db.flush()
        cls = Classification(
            document_id=doc.id, category=d["sensitivity"], unsafe=d["unsafe"], confidence_score=d["confidence"],
            reasoning=c["reasoning"] or "", summary=c["summary"] or "", model_used=c["model"],
            content_safety_passed=c["content_safe"], safety_flags=[], pii_detected=c["pii_detected"], pii_types=[],
        )
        db.add(cls)
        db.flush()
        for ev in item["citations"]:
            db.add(CitationEvidence(
                classification_id=cls.id, page_number=ev["page_number"], evidence_type=ev["evidence_type"],
                evidence_text=ev["evidence_text"], evidence_description=ev["description"],
                supporting_category=d["sensitivity"], verified=ev["verified"], relevance_score=0.8,
            ))
        db.commit()
    return len(items)


def export(base: str, out: str, files: list) -> None:
    import httpx  # already pinned in requirements.txt

    with httpx.Client(base_url=base, timeout=180) as http:
        model = http.get("/api").json()["model"]
        items = []
        for f in files:
            name = os.path.basename(f)
            with open(f, "rb") as fh:
                up = http.post("/api/documents/upload", files={"file": (name, fh, "application/pdf")})
            up.raise_for_status()
            doc_id = up.json()["document_id"]
            http.post(f"/api/documents/{doc_id}/classify").raise_for_status()
            detail = http.get(f"/api/documents/{doc_id}").json()
            row = next(r for r in http.get("/api/documents", params={"limit": 1000}).json()["documents"] if r["id"] == doc_id)
            doc, cls = detail["document"], detail["classification"]
            items.append({
                "file": os.path.relpath(f, ROOT).replace("\\", "/"),
                "document": {
                    "filename": name, "status": row["status"], "requires_review": row["requires_review"],
                    "page_count": doc["page_count"], "image_count": doc["image_count"], "is_legible": doc["is_legible"],
                    "sensitivity": cls["sensitivity"], "unsafe": cls["unsafe"], "confidence": cls["confidence"],
                },
                "classification": {"summary": cls["summary"], "reasoning": cls["reasoning"], "model": model,
                                   "pii_detected": cls["pii_detected"], "content_safe": cls["content_safe"]},
                "citations": [{k: c[k] for k in ("page_number", "evidence_type", "evidence_text", "description", "verified")}
                              for c in detail["citations"]],
            })
            print(f"{name}: {cls['sensitivity']}, unsafe={cls['unsafe']}, {len(items[-1]['citations'])} citations")
    Path(out).write_text(json.dumps(items, indent=1, ensure_ascii=False) + "\n", encoding="utf-8")


if __name__ == "__main__":
    if len(sys.argv) < 5 or sys.argv[1] != "export":
        sys.exit(__doc__)
    export(sys.argv[2], sys.argv[3], sys.argv[4:])
