"""
Main FastAPI Application
Regulatory Document Classifier API
"""
from fastapi import FastAPI, File, UploadFile, HTTPException, Depends
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse, HTMLResponse, FileResponse
from fastapi.staticfiles import StaticFiles
from sqlalchemy.orm import Session
from typing import List, Optional
import uvicorn
import os
import uuid
from datetime import datetime
from loguru import logger
from pathlib import Path

from backend.config import settings
from backend.database import init_db, get_db
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

# Mount static files for frontend
frontend_path = Path(__file__).parent.parent / "frontend" / "public"
if frontend_path.exists():
    app.mount("/static", StaticFiles(directory=str(frontend_path)), name="static")

# Initialize database
@app.on_event("startup")
async def startup_event():
    """Initialize database and services on startup"""
    logger.info(f"Starting {settings.APP_NAME} v{settings.APP_VERSION}")
    init_db()
    logger.info("Database initialized")

# Serve frontend UI
@app.get("/", response_class=HTMLResponse)
async def serve_frontend():
    """Serve the frontend UI"""
    frontend_file = Path(__file__).parent.parent / "frontend" / "public" / "index.html"
    if frontend_file.exists():
        return FileResponse(frontend_file)
    return {"message": "Frontend not found. Visit /docs for API documentation"}

# API Status endpoint
@app.get("/api")
async def api_root():
    """API root endpoint"""
    return {
        "name": settings.APP_NAME,
        "version": settings.APP_VERSION,
        "status": "running"
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
    file: UploadFile = File(...),
    db: Session = Depends(get_db)
):
    """
    Upload a document. Classify it with POST /api/documents/{id}/classify.
    """
    try:
        # Validate file size
        file_size = 0
        content = await file.read()
        file_size = len(content)

        max_size = settings.MAX_FILE_SIZE_MB * 1024 * 1024
        if file_size > max_size:
            raise HTTPException(
                status_code=400,
                detail=f"File size exceeds maximum allowed size of {settings.MAX_FILE_SIZE_MB}MB"
            )

        # Validate file extension
        file_ext = os.path.splitext(file.filename or "")[1].lower().replace('.', '')
        if file_ext not in settings.ALLOWED_EXTENSIONS:
            raise HTTPException(
                status_code=400,
                detail=f"File type '{file_ext}' not allowed. Allowed types: {settings.ALLOWED_EXTENSIONS}"
            )

        # Generated name: the client filename is stored as data only, never used in the path
        safe_filename = f"{uuid.uuid4().hex}.{file_ext}"
        file_path = os.path.join(settings.UPLOAD_DIR, safe_filename)

        # Save file
        with open(file_path, "wb") as f:
            f.write(content)

        # Create document record
        doc = Document(
            filename=safe_filename,
            original_filename=file.filename,
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
            description=f"Document uploaded: {file.filename}",
            success=True
        )
        db.add(audit)
        db.commit()

        logger.info(f"Document uploaded: {file.filename} (ID: {doc.id})")

        return {
            "document_id": doc.id,
            "filename": file.filename,
            "status": doc.status.value,
            "message": f"Document uploaded. Classify with POST /api/documents/{doc.id}/classify."
        }

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Upload failed: {e}")
        raise HTTPException(status_code=500, detail=f"Upload failed: {str(e)}")

@app.post("/api/documents/{document_id}/classify")
async def classify_document_endpoint(
    document_id: int,
    db: Session = Depends(get_db)
):
    """
    Trigger classification for an uploaded document

    This is for manual/interactive classification mode.
    """
    try:
        # Get document
        doc = db.query(Document).filter(Document.id == document_id).first()
        if not doc:
            raise HTTPException(status_code=404, detail="Document not found")

        # Update status
        doc.status = DocumentStatus.CLASSIFYING
        doc.processing_started_at = datetime.utcnow()
        db.commit()

        # Run classification
        classifier = DocumentClassifier()
        result = classifier.classify_document(doc.file_path)

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
                    supporting_category=result["sensitivity"]
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
            "document_id": doc.id,
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
async def get_document(document_id: int, db: Session = Depends(get_db)):
    """Get document details and classification results"""
    doc = db.query(Document).filter(Document.id == document_id).first()
    if not doc:
        raise HTTPException(status_code=404, detail="Document not found")

    # Get classification
    classification = db.query(Classification).filter(
        Classification.document_id == document_id
    ).first()

    # Get citations
    citations = []
    if classification:
        citations = db.query(CitationEvidence).filter(
            CitationEvidence.classification_id == classification.id
        ).all()

    return {
        "document": {
            "id": doc.id,
            "filename": doc.original_filename,
            "status": doc.status.value,
            "page_count": doc.page_count,
            "image_count": doc.image_count,
            "is_legible": doc.is_legible,
            "created_at": doc.created_at.isoformat()
        },
        "classification": {
            "sensitivity": classification.category if classification else None,
            "unsafe": classification.unsafe if classification else None,
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
                "description": c.evidence_description
            }
            for c in citations
        ]
    }

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

    documents = query.offset(skip).limit(limit).all()

    return {
        "documents": [
            {
                "id": doc.id,
                "filename": doc.original_filename,
                "status": doc.status.value,
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
    document_id: int,
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
        doc = db.query(Document).filter(Document.id == document_id).first()
        if not doc:
            raise HTTPException(status_code=404, detail="Document not found")

        # Get classification
        classification = db.query(Classification).filter(
            Classification.document_id == document_id
        ).first()

        # Create feedback
        feedback = Feedback(
            document_id=document_id,
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
        if corrected_category or corrected_unsafe is not None:
            if corrected_category:
                doc.primary_category = ClassificationCategory[corrected_category.upper().replace(" ", "_")]
            doc.reviewed_by = reviewer_name
            doc.reviewed_at = datetime.utcnow()
            doc.requires_review = False

        db.commit()

        # Log audit
        audit = AuditLog(
            action="feedback_submitted",
            entity_type="feedback",
            entity_id=feedback.id,
            description=f"Feedback submitted by {reviewer_name} for document {document_id}",
            success=True
        )
        db.add(audit)
        db.commit()

        logger.info(f"Feedback submitted for document {document_id} by {reviewer_name}")

        return {
            "feedback_id": feedback.id,
            "message": "Feedback submitted successfully"
        }

    except Exception as e:
        logger.error(f"Feedback submission failed: {e}")
        raise HTTPException(status_code=500, detail=f"Feedback submission failed: {str(e)}")

if __name__ == "__main__":
    uvicorn.run(
        "backend.main:app",
        host=settings.API_HOST,
        port=settings.API_PORT,
        reload=settings.DEBUG
    )
