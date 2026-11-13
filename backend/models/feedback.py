"""
Feedback models for Human-in-the-Loop (HITL) system
"""
from datetime import datetime
from enum import Enum
from sqlalchemy import Column, Integer, String, DateTime, Text, ForeignKey, Boolean, Enum as SQLEnum
from .document import Base


class FeedbackType(str, Enum):
    """Types of feedback"""
    CORRECTION = "correction"
    CONFIRMATION = "confirmation"
    ADDITIONAL_CONTEXT = "additional_context"
    PROMPT_IMPROVEMENT = "prompt_improvement"


class Feedback(Base):
    """User feedback for improving classification accuracy"""
    __tablename__ = "feedback"

    id = Column(Integer, primary_key=True, index=True)
    document_id = Column(Integer, ForeignKey("documents.id"), nullable=False)
    classification_id = Column(Integer, ForeignKey("classifications.id"), nullable=True)

    # Feedback details
    feedback_type = Column(SQLEnum(FeedbackType), nullable=False)
    original_category = Column(String(50), nullable=True)
    corrected_category = Column(String(50), nullable=True)
    original_unsafe = Column(Boolean, nullable=True)
    corrected_unsafe = Column(Boolean, nullable=True)

    # User input
    reviewer_name = Column(String(100), nullable=False)
    comments = Column(Text, nullable=True)
    confidence_rating = Column(Integer, nullable=True)  # 1-5 scale

    # Impact tracking
    is_applied = Column(Boolean, default=False)
    applied_at = Column(DateTime, nullable=True)
    improvement_notes = Column(Text, nullable=True)

    # Timestamps
    created_at = Column(DateTime, default=datetime.utcnow)

    def __repr__(self):
        return f"<Feedback(id={self.id}, type='{self.feedback_type}', document_id={self.document_id})>"
