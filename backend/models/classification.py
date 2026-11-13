"""
Classification models for storing classification results and evidence
"""
from datetime import datetime
from sqlalchemy import Column, Integer, String, DateTime, Float, Text, ForeignKey, JSON, Boolean
from sqlalchemy.orm import relationship
from .document import Base


class Classification(Base):
    """Classification results model"""
    __tablename__ = "classifications"

    id = Column(Integer, primary_key=True, index=True)
    document_id = Column(Integer, ForeignKey("documents.id"), nullable=False)

    # Classification details
    category = Column(String(50), nullable=False)  # sensitivity level
    unsafe = Column(Boolean, nullable=True)
    confidence_score = Column(Float, nullable=False)
    reasoning = Column(Text, nullable=False)
    summary = Column(Text, nullable=False)

    # Model information
    model_used = Column(String(100), nullable=False)
    model_version = Column(String(50), nullable=True)

    # Safety checks
    content_safety_passed = Column(Text, default=True)
    safety_flags = Column(JSON, nullable=True)  # JSON array of safety issues

    # PII Detection
    pii_detected = Column(Text, default=False)
    pii_types = Column(JSON, nullable=True)  # JSON array of PII types found

    # Dual verification (if enabled)
    is_verified = Column(Text, default=False)
    verification_model = Column(String(100), nullable=True)
    verification_agreement = Column(Float, nullable=True)

    # Timestamps
    created_at = Column(DateTime, default=datetime.utcnow)

    def __repr__(self):
        return f"<Classification(id={self.id}, document_id={self.document_id}, category='{self.category}')>"


class CitationEvidence(Base):
    """Citation evidence for classification decisions"""
    __tablename__ = "citation_evidence"

    id = Column(Integer, primary_key=True, index=True)
    classification_id = Column(Integer, ForeignKey("classifications.id"), nullable=False)

    # Citation details
    page_number = Column(Integer, nullable=True)
    image_number = Column(Integer, nullable=True)
    region = Column(JSON, nullable=True)  # Bounding box coordinates

    # Evidence content
    evidence_type = Column(String(50), nullable=False)  # text, image, metadata
    evidence_text = Column(Text, nullable=True)
    evidence_description = Column(Text, nullable=False)

    # Relevance
    relevance_score = Column(Float, nullable=False)
    supporting_category = Column(String(50), nullable=False)

    # Timestamps
    created_at = Column(DateTime, default=datetime.utcnow)

    def __repr__(self):
        return f"<CitationEvidence(id={self.id}, page={self.page_number}, type='{self.evidence_type}')>"
