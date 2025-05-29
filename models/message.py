"""
Message models for the FastAPI application
"""
from pydantic import BaseModel, Field
from typing import Optional, Dict, Any

class TranslationStatus(BaseModel):
    progress: float = Field(0.0, description="Progress percentage (0-100)")
    status_type: str = Field("pending", description="Status type: pending, started, completed, failed")
    message: Optional[str] = Field(None, description="Optional status message or error details")
    
    model_config = {
        "protected_namespaces": (),
        "json_schema_extra": {
            "example": {
                "progress": 75.0,
                "status_type": "started",
                "message": "Translation 75% complete"
            }
        }
    }

class Message(BaseModel):
    content: str = Field(..., description="Text content to be translated")
    model_name: str = Field(..., description="Name of the translation model to use")
    api_key: str = Field(..., description="API key for the translation model")
    priority: Optional[int] = Field(0, description="Priority level (higher numbers = higher priority)")
    metadata: Optional[Dict[str, Any]] = Field(None, description="Optional metadata for the translation job")
    webhook: Optional[str] = Field(None, description="Optional webhook URL for status updates")
    use_segmentation: Optional[str] = Field("botok", description="Segmentation method to use. Options: 'botok' for Tibetan segmentation, 'sentence' for sentence-based, 'newline' for newline-based, or None for no segmentation")
    model_config = {
        "protected_namespaces": (),
        "json_schema_extra": {
            "example": {
  "api_key": "your api key",
  "content": "Hello world! This text needs to be translated.",
  "metadata": {
    "domain": "general",
    "source_language": "english",
    "target_language": "tibetan"
  },
  "model_name": "claude-3-haiku-20240307",
  "priority": 5,
"use_segmentation":"botok",
  "webhook": ""
}
        }
    }

class MessageResponse(BaseModel):
    id: str = Field(..., description="Unique identifier for the message")
    status: TranslationStatus = Field(..., description="Current status of the translation")
    position: Optional[int] = Field(None, description="Position in the queue (if pending)")
    
    model_config = {
        "protected_namespaces": (),
        "json_schema_extra": {
            "example": {
                "id": "f47ac10b-58cc-4372-a567-0e02b2c3d479",
                "status": {
                    "progress": 0.0,
                    "status_type": "pending",
                    "message": "Queued for translation"
                },
                "position": None
            }
        }
    }

class MessageStatus(BaseModel):
    id: str = Field(..., description="Message ID to check status for")
    
    model_config = {
        "protected_namespaces": (),
        "json_schema_extra": {
            "example": {
                "id": "f47ac10b-58cc-4372-a567-0e02b2c3d479"
            }
        }
    }

class StatusUpdate(BaseModel):
    progress: float = Field(..., description="Progress percentage (0-100)")
    status_type: str = Field(..., description="Status type: pending, started, completed, failed")
    message: Optional[str] = Field(None, description="Optional status message or error details")
    
    model_config = {
        "protected_namespaces": (),
        "json_schema_extra": {
            "example": {
                "progress": 50.0,
                "status_type": "started",
                "message": "Translation 50% complete"
            }
        }
    }
