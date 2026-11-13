"""
Configuration Management for Regulatory Document Classifier
"""
import os
from typing import List
from pydantic_settings import BaseSettings
from pydantic import Field


class Settings(BaseSettings):
    """Application settings and configuration"""

    # Application
    APP_NAME: str = "Regulatory Document Classifier"
    APP_VERSION: str = "1.0.0"
    ENVIRONMENT: str = Field(default="development", env="ENVIRONMENT")
    DEBUG: bool = Field(default=True, env="DEBUG")
    LOG_LEVEL: str = Field(default="INFO", env="LOG_LEVEL")

    # API Keys
    ANTHROPIC_API_KEY: str = Field(default="", env="ANTHROPIC_API_KEY")
    OPENAI_API_KEY: str = Field(default="", env="OPENAI_API_KEY")

    # API Configuration
    API_HOST: str = Field(default="0.0.0.0", env="API_HOST")
    API_PORT: int = Field(default=8000, env="API_PORT")
    ALLOWED_ORIGINS: List[str] = Field(
        default=["http://localhost:3000", "http://localhost:8000"],
        env="ALLOWED_ORIGINS"
    )

    # Database
    DATABASE_URL: str = Field(
        default="sqlite:///./regulatory_classifier.db",
        env="DATABASE_URL"
    )

    # Redis
    REDIS_URL: str = Field(default="redis://localhost:6379/0", env="REDIS_URL")

    # LLM Configuration
    PRIMARY_LLM_MODEL: str = Field(
        default="claude-haiku-5-5",
        env="PRIMARY_LLM_MODEL"
    )
    SECONDARY_LLM_MODEL: str = Field(
        default="gpt-3.5-turbo",
        env="SECONDARY_LLM_MODEL"
    )
    USE_DUAL_VERIFICATION: bool = Field(default=True, env="USE_DUAL_VERIFICATION")
    CONFIDENCE_THRESHOLD: float = Field(default=0.85, env="CONFIDENCE_THRESHOLD")
    MAX_TOKENS: int = Field(default=4096, env="MAX_TOKENS")
    TEMPERATURE: float = Field(default=0.1, env="TEMPERATURE")

    # Document Processing
    MAX_FILE_SIZE_MB: int = Field(default=50, env="MAX_FILE_SIZE_MB")
    ALLOWED_EXTENSIONS: List[str] = Field(
        default=["pdf", "png", "jpg", "jpeg", "tiff", "doc", "docx"],
        env="ALLOWED_EXTENSIONS"
    )
    UPLOAD_DIR: str = Field(default="uploads", env="UPLOAD_DIR")
    TEMP_DIR: str = Field(default="temp", env="TEMP_DIR")

    # Content Safety
    ENABLE_CONTENT_SAFETY: bool = Field(default=True, env="ENABLE_CONTENT_SAFETY")
    SAFETY_THRESHOLD: float = Field(default=0.7, env="SAFETY_THRESHOLD")

    # HITL Configuration
    ENABLE_HITL: bool = Field(default=True, env="ENABLE_HITL")
    LOW_CONFIDENCE_THRESHOLD: float = Field(
        default=0.7,
        env="LOW_CONFIDENCE_THRESHOLD"
    )

    # Classification Categories
    CLASSIFICATION_CATEGORIES: List[str] = Field(
        default=[
            "Public",
            "Confidential",
            "Highly Sensitive",
            "Unsafe"
        ]
    )

    class Config:
        env_file = ".env"
        case_sensitive = True


# Global settings instance
settings = Settings()


# Ensure directories exist
os.makedirs(settings.UPLOAD_DIR, exist_ok=True)
os.makedirs(settings.TEMP_DIR, exist_ok=True)
os.makedirs("logs", exist_ok=True)
