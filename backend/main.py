"""
Main FastAPI Application
Regulatory Document Classifier API
"""
from fastapi import FastAPI, File, UploadFile, HTTPException, Depends, Request
from fastapi.concurrency import run_in_threadpool
from fastapi.middleware.cors import CORSMiddleware
from fastapi.middleware.gzip import GZipMiddleware
from fastapi.responses import JSONResponse, FileResponse
from fastapi.staticfiles import StaticFiles
from sqlalchemy import func
from sqlalchemy.orm import Session
from typing import List, Optional
import uvicorn
import os
import mimetypes
import uuid
from datetime import datetime
from loguru import logger
from pathlib import Path

from backend.config import settings
from backend.database import init_db, get_db
from backend import guard
from backend.seed import seed_if_empty
from backend.services.classifier import DocumentClassifier
from backend.models import (
    Document,
    DocumentStatus,
    ClassificationCategory,
    Classification,
    CitationEvidence,
    Feedback,
    FeedbackType,
    AuditLog
)

# Initialize FastAPI app
app = FastAPI(
    title=settings.APP_NAME,
    version=settings.APP_VERSION,
    description="AI-Powered Regulatory Document Classifier API"
)

# CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.ALLOWED_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# gzip: the PDF.js worker is 1.27 MB raw, about 375 KB compressed (docs/UI_BUILD.md)
app.add_middleware(GZipMiddleware, minimum_size=1000)

# Initialize database
@app.on_event("startup")
async def startup_event():
    """Initialize database and services on startup"""
    logger.info(f"Starting {settings.APP_NAME} v{settings.APP_VERSION}")
    init_db()
    logger.info("Database initialized")
    if settings.SEED_ON_BOOT:
        from backend.database import SessionLocal
        with SessionLocal() as db:
            logger.info(f"Seeded {seed_if_empty(db)} documents")

def find_document(db: Session, public_id: str) -> Document:
    doc = db.query(Document).filter(Document.public_id == public_id).first()
    if not doc:
        raise HTTPException(status_code=404, detail="Document not found")
    return doc


# API Status endpoint
@app.get("/api")
async def api_root():
    """API root endpoint"""
    return {
        "name": settings.APP_NAME,
        "version": settings.APP_VERSION,
        "status": "running",
        "model": settings.PRIMARY_LLM_MODEL
    }

@app.get("/health")
async def health_check():
    """Health check endpoint"""
    return {
        "status": "healthy",
        "timestamp": datetime.utcnow().isoformat()
    }

# Document Upload and Classification
@app.post("/api/documents/upload")
async def upload_document(
    request: Request,
    file: UploadFile = File(...),
    db: Session = Depends(get_db)
):
    """
    Upload a document. Classify it with POST /api/documents/{id}/classify.
    """
    try:
        guard.check_upload_quota(request)

        # Validate file size (read one byte past the cap so an oversized upload is never held whole)
        max_size = settings.MAX_FILE_SIZE_MB * 1024 * 1024
        content = await file.read(max_size + 1)
        file_size = len(content)
        if file_size > max_size:
            raise HTTPException(
                status_code=413,
                detail=f"File size exceeds maximum allowed size of {settings.MAX_FILE_SIZE_MB}MB"
            )

        # Validate file extension
        file_ext = os.path.splitext(file.filename or "")[1].lower().replace('.', '')
        if file_ext not in settings.ALLOWED_EXTENSIONS:
            raise HTTPException(
                status_code=400,
                detail=f"File type '{file_ext}' not allowed. Allowed types: {settings.ALLOWED_EXTENSIONS}"
            )

        stored = db.query(func.coalesce(func.sum(Document.file_size), 0)).scalar()
        if stored + file_size > settings.MAX_STORED_MB * 1024 * 1024:
            raise HTTPException(status_code=507, detail="The demo's upload storage is full; it is cleared when the instance sleeps.")

        if file_ext == "pdf":
            pages = guard.pdf_page_count(content)
            if pages is not None and pages > settings.MAX_PDF_PAGES:
                raise HTTPException(status_code=400, detail=f"PDF has {pages} pages; this demo accepts at most {settings.MAX_PDF_PAGES}.")

        # Generated name: the client filename is stored as data only, never used in the path
        safe_filename = f"{uuid.uuid4().hex}.{file_ext}"
        file_path = os.path.join(settings.UPLOAD_DIR, safe_filename)

        # Save file
        with open(file_path, "wb") as f:
            f.write(content)

        # Create document record
        doc = Document(
            filename=safe_filename,
            original_filename=guard.clean_filename(file.filename),
            file_path=file_path,
            file_size=file_size,
            mime_type=file.content_type or "application/octet-stream",
            status=DocumentStatus.UPLOADED
        )
        db.add(doc)
        db.commit()
        db.refresh(doc)

        # Log audit
        audit = AuditLog(
            action="document_upload",
            entity_type="document",
            entity_id=doc.id,
            description=f"Document uploaded: {doc.original_filename}",
            success=True
        )
        db.add(audit)
        db.commit()

        logger.info(f"Document uploaded: {doc.original_filename} (ID: {doc.id})")

        return {
            "document_id": doc.public_id,
            "filename": doc.original_filename,
            "status": doc.status.value,
            "message": f"Document uploaded. Classify with POST /api/documents/{doc.public_id}/classify."
        }

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Upload failed: {e}")
        raise HTTPException(status_code=500, detail=f"Upload failed: {str(e)}")

@app.post("/api/documents/{document_id}/classify")
async def classify_document_endpoint(
    document_id: str,
    db: Session = Depends(get_db)
):
    """
    Trigger classification for an uploaded document

    This is for manual/interactive classification mode. Each upload is classified once:
    the upload quota is what bounds spend, so a second call is refused.
    """
    try:
        doc = find_document(db, document_id)
        if doc.status != DocumentStatus.UPLOADED:
            raise HTTPException(status_code=409, detail="This document has already been classified.")

        # Update status
        doc.status = DocumentStatus.CLASSIFYING
        doc.processing_started_at = datetime.utcnow()
        db.commit()

        # Run classification
        classifier = DocumentClassifier()
        # in a worker thread: it takes seconds, and the event loop must keep answering health checks
        result = await run_in_threadpool(classifier.classify_document, doc.file_path)

        # Update document with results
        if result["status"] == "completed":
            doc.status = DocumentStatus.COMPLETED
            doc.primary_category = ClassificationCategory(result["sensitivity"])
            doc.unsafe = result["unsafe"]
            doc.confidence_score = result["confidence"]
            doc.page_count = result["document_metadata"]["page_count"]
            doc.image_count = result["document_metadata"]["image_count"]
            doc.has_text = result["document_metadata"]["has_text"]
            doc.is_legible = result["document_metadata"]["is_legible"]
            doc.legibility_score = result["document_metadata"]["legibility_score"]

            # Check if requires review
            if result["hitl_decision"]["requires_hitl"]:
                doc.requires_review = True
                doc.status = DocumentStatus.PENDING_REVIEW

        else:
            doc.status = DocumentStatus.FAILED
            doc.error_message = result.get("error", "Unknown error")

        doc.processing_completed_at = datetime.utcnow()
        db.commit()

        # Save classification results
        if result["status"] == "completed":
            classification = Classification(
                document_id=doc.id,
                category=result["sensitivity"],
                unsafe=result["unsafe"],
                confidence_score=result["confidence"],
                reasoning=result["reasoning"],
                summary=result["summary"],
                model_used=result.get("model_used", settings.PRIMARY_LLM_MODEL),
                content_safety_passed=result["safety_results"]["is_safe"],
                safety_flags=result["safety_results"].get("safety_flags", []),
                pii_detected=result["pii_results"]["pii_detected"],
                pii_types=result["pii_results"].get("pii_types", [])
            )
            db.add(classification)
            db.commit()
            db.refresh(classification)

            # Save citations
            for citation in result.get("citations", []):
                evidence = CitationEvidence(
                    classification_id=classification.id,
                    page_number=citation.get("page_number"),
                    evidence_type=citation.get("evidence_type", "text"),
                    evidence_text=citation.get("evidence_text"),
                    evidence_description=citation.get("relevance", ""),
                    relevance_score=citation.get("relevance_score", 0.8),
                    supporting_category=result["sensitivity"],
                    verified=citation.get("verified")
                )
                db.add(evidence)

            db.commit()

        # Log audit
        audit = AuditLog(
            action="document_classification",
            entity_type="document",
            entity_id=doc.id,
            description=f"Document classified as: {result.get('sensitivity', 'failed')}, unsafe={result.get('unsafe')}",
            success=result["status"] == "completed"
        )
        db.add(audit)
        db.commit()

        if result["status"] != "completed":
            raise RuntimeError(result.get("error", "Unknown error"))  # categorised by the handler below

        return {
            "document_id": doc.public_id,
            "status": doc.status.value,
            "sensitivity": result["sensitivity"],
            "unsafe": result["unsafe"],
            "confidence": result.get("confidence"),
            "summary": result.get("summary"),
            "requires_review": doc.requires_review,
            "document_metadata": result.get("document_metadata", {}),
            "pii_detected": result["pii_results"]["pii_detected"],
            "content_safe": result["safety_results"]["is_safe"]
        }

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Classification failed: {e}")

        # Categorize the error for better user feedback
        error_type = "unknown_error"
        error_detail = str(e)
        user_message = "Classification failed"

        if "401" in str(e) or "authentication" in str(e).lower():
            error_type = "authentication_error"
            user_message = "Invalid API Key"
            error_detail = "The Anthropic API key is invalid or expired. Please update your API key in the .env file."
        elif "429" in str(e) or "rate_limit" in str(e).lower():
            error_type = "rate_limit_error"
            user_message = "API Rate Limit Exceeded"
            error_detail = "Too many requests. Please wait a moment and try again."
        elif "402" in str(e) or "insufficient" in str(e).lower() or "quota" in str(e).lower():
            error_type = "quota_error"
            user_message = "API Credits Exhausted"
            error_detail = "Your Anthropic API credits have been exhausted. Please add credits to your account."
        elif "timeout" in str(e).lower() or "timed out" in str(e).lower():
            error_type = "timeout_error"
            user_message = "Request Timeout"
            error_detail = "The classification request took too long. Please try again."
        elif "connection" in str(e).lower() or "network" in str(e).lower():
            error_type = "network_error"
            user_message = "Network Error"
            error_detail = "Unable to connect to the API. Please check your internet connection."
        elif "pii_results" in str(e):
            error_type = "processing_error"
            user_message = "Classification Processing Error"
            error_detail = "The document was processed but classification results are incomplete. This may be due to API issues."

        # Update document status
        if 'doc' in locals():
            doc.status = DocumentStatus.FAILED
            doc.error_message = f"{error_type}: {error_detail}"
            db.commit()

        raise HTTPException(
            status_code=500,
            detail={
                "error": user_message,
                "error_type": error_type,
                "error_detail": error_detail,
                "technical_error": str(e)
            }
        )

@app.get("/api/documents/{document_id}")
async def get_document(document_id: str, db: Session = Depends(get_db)):
    """Get document details and classification results"""
    doc = find_document(db, document_id)

    # Get classification
    classification = db.query(Classification).filter(
        Classification.document_id == doc.id
    ).first()

    # Get citations
    citations = []
    if classification:
        citations = db.query(CitationEvidence).filter(
            CitationEvidence.classification_id == classification.id
        ).all()

    return {
        "document": {
            "id": doc.public_id,
            "filename": doc.original_filename,
            "status": doc.status.value,
            "page_count": doc.page_count,
            "image_count": doc.image_count,
            "is_legible": doc.is_legible,
            "created_at": doc.created_at.isoformat()
        },
        "classification": {
            # effective (reviewed) values; the model's original stays in classifications + feedback.original_*
            "sensitivity": doc.primary_category.value if doc.primary_category else classification.category,
            "unsafe": doc.unsafe,
            "confidence": classification.confidence_score if classification else None,
            "summary": classification.summary if classification else None,
            "reasoning": classification.reasoning if classification else None,
            "pii_detected": classification.pii_detected if classification else False,
            "content_safe": classification.content_safety_passed if classification else True
        } if classification else None,
        "citations": [
            {
                "page_number": c.page_number,
                "evidence_type": c.evidence_type,
                "evidence_text": c.evidence_text,
                "description": c.evidence_description,
                "verified": c.verified
            }
            for c in citations
        ]
    }

@app.get("/api/documents/{document_id}/file")
async def get_document_file(document_id: str, db: Session = Depends(get_db)):
    """The stored upload, shown inline in the document view"""
    doc = db.query(Document).filter(Document.public_id == document_id).first()
    if not doc or not os.path.isfile(doc.file_path):
        raise HTTPException(status_code=404, detail="File not found")
    # type from the validated extension, never the client's claimed content type (no HTML on this origin)
    media_type = mimetypes.guess_type(doc.filename)[0] or "application/octet-stream"
    return FileResponse(doc.file_path, media_type=media_type, headers={"X-Content-Type-Options": "nosniff"})

@app.get("/api/documents")
async def list_documents(
    skip: int = 0,
    limit: int = 100,
    status: Optional[str] = None,
    db: Session = Depends(get_db)
):
    """List all documents with optional filtering"""
    query = db.query(Document)

    if status:
        query = query.filter(Document.status == status)

    documents = query.order_by(Document.id).offset(skip).limit(limit).all()  # stable order so pages don't overlap

    return {
        "documents": [
            {
                "id": doc.public_id,
                "filename": doc.original_filename,
                "status": doc.status.value,
                "reviewed": doc.reviewed_at is not None,
                "sensitivity": doc.primary_category.value if doc.primary_category else None,
                "unsafe": doc.unsafe,
                "confidence": doc.confidence_score,
                "requires_review": doc.requires_review,
                "created_at": doc.created_at.isoformat()
            }
            for doc in documents
        ],
        "total": query.count()
    }

# Feedback endpoints
@app.post("/api/feedback")
async def submit_feedback(
    document_id: str,
    feedback_type: str,
    reviewer_name: str,
    corrected_category: Optional[str] = None,
    corrected_unsafe: Optional[bool] = None,
    comments: Optional[str] = None,
    db: Session = Depends(get_db)
):
    """Submit HITL feedback"""
    try:
        # Validate document exists
        doc = find_document(db, document_id)

        # Get classification
        classification = db.query(Classification).filter(
            Classification.document_id == doc.id
        ).first()

        # Create feedback
        feedback = Feedback(
            document_id=doc.id,
            classification_id=classification.id if classification else None,
            feedback_type=FeedbackType[feedback_type.upper()],
            original_category=classification.category if classification else None,
            corrected_category=corrected_category,
            original_unsafe=classification.unsafe if classification else None,
            corrected_unsafe=corrected_unsafe,
            reviewer_name=reviewer_name,
            comments=comments
        )
        db.add(feedback)

        # Update document if corrected
        if corrected_unsafe is not None:
            doc.unsafe = corrected_unsafe
        if corrected_category:
            doc.primary_category = ClassificationCategory[corrected_category.upper().replace(" ", "_")]
        # an approval ("confirmation") closes the review just like a correction does
        if corrected_category or corrected_unsafe is not None or feedback.feedback_type == FeedbackType.CONFIRMATION:
            doc.reviewed_by = reviewer_name
            doc.reviewed_at = datetime.utcnow()
            doc.requires_review = False
            if doc.status == DocumentStatus.PENDING_REVIEW:
                doc.status = DocumentStatus.COMPLETED

        db.commit()

        # Log audit
        audit = AuditLog(
            action="feedback_submitted",
            entity_type="feedback",
            entity_id=feedback.id,
            description=f"Feedback submitted by {reviewer_name} for document {doc.id}",
            success=True
        )
        db.add(audit)
        db.commit()

        logger.info(f"Feedback submitted for document {doc.id} by {reviewer_name}")

        return {
            "feedback_id": feedback.id,
            "message": "Feedback submitted successfully"
        }

    except Exception as e:
        logger.error(f"Feedback submission failed: {e}")
        raise HTTPException(status_code=500, detail=f"Feedback submission failed: {str(e)}")

# Built UI (`next build` static export). Mounted last so every route above wins.
ui_dir = Path(__file__).parent.parent / "frontend" / "out"
if ui_dir.exists():
    app.mount("/", StaticFiles(directory=str(ui_dir), html=True), name="ui")

if __name__ == "__main__":
    uvicorn.run(
        "backend.main:app",
        host=settings.API_HOST,
        port=settings.API_PORT,
        reload=settings.DEBUG
    )
