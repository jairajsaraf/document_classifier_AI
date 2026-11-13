"""
Document models for storing uploaded documents and metadata
"""
from datetime import datetime
from enum import Enum
from typing import Optional
from sqlalchemy import Column, Integer, String, DateTime, Float, Boolean, Text, Enum as SQLEnum
from sqlalchemy.ext.declarative import declarative_base

Base = declarative_base()


class DocumentStatus(str, Enum):
    """Document processing status"""
    UPLOADED = "uploaded"
    PREPROCESSING = "preprocessing"
    CLASSIFYING = "classifying"
    COMPLETED = "completed"
    FAILED = "failed"
    PENDING_REVIEW = "pending_review"


class ClassificationCategory(str, Enum):
    """Classification categories"""
    PUBLIC = "Public"
    CONFIDENTIAL = "Confidential"
    HIGHLY_SENSITIVE = "Highly Sensitive"


class Document(Base):
    """Document database model"""
    __tablename__ = "documents"

    id = Column(Integer, primary_key=True, index=True)
    filename = Column(String(255), nullable=False)
    original_filename = Column(String(255), nullable=False)
    file_path = Column(String(500), nullable=False)
    file_size = Column(Integer, nullable=False)  # in bytes
    mime_type = Column(String(100), nullable=False)

    # Document metadata
    page_count = Column(Integer, default=0)
    image_count = Column(Integer, default=0)
    has_text = Column(Boolean, default=False)
    is_legible = Column(Boolean, default=True)
    legibility_score = Column(Float, nullable=True)

    # Processing status
    status = Column(SQLEnum(DocumentStatus), default=DocumentStatus.UPLOADED)
    processing_started_at = Column(DateTime, nullable=True)
    processing_completed_at = Column(DateTime, nullable=True)
    error_message = Column(Text, nullable=True)

    # Classification results
    primary_category = Column(SQLEnum(ClassificationCategory), nullable=True)  # sensitivity level
    unsafe = Column(Boolean, nullable=True)
    secondary_categories = Column(String(500), nullable=True)  # JSON array
    confidence_score = Column(Float, nullable=True)
    requires_review = Column(Boolean, default=False)

    # Timestamps
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    # User tracking (optional)
    uploaded_by = Column(String(100), nullable=True)
    reviewed_by = Column(String(100), nullable=True)
    reviewed_at = Column(DateTime, nullable=True)

    def __repr__(self):
        return f"<Document(id={self.id}, filename='{self.filename}', status='{self.status}')>"
