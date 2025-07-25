"""
Message models for the FastAPI application
"""
from pydantic import BaseModel, Field
from typing import Optional, Dict, Any, Union

class ErrorResponse(BaseModel):
    """Standard error response model"""
    success: bool = Field(False, description="Indicates if the operation was successful")
    error: str = Field(..., description="Error message describing what went wrong")
    error_code: Optional[str] = Field(None, description="Optional error code for programmatic handling")
    details: Optional[Dict[str, Any]] = Field(None, description="Optional additional error details")
    
    model_config = {
        "protected_namespaces": (),
        "json_schema_extra": {
            "example": {
                "success": False,
                "error": "Message not found",
                "error_code": "MESSAGE_NOT_FOUND",
                "details": {"message_id": "f47ac10b-58cc-4372-a567-0e02b2c3d479"}
            }
        }
    }

class SuccessResponse(BaseModel):
    """Standard success response model"""
    success: bool = Field(True, description="Indicates if the operation was successful")
    message: str = Field(..., description="Success message")
    data: Optional[Dict[str, Any]] = Field(None, description="Optional response data")
    
    model_config = {
        "protected_namespaces": (),
        "json_schema_extra": {
            "example": {
                "success": True,
                "message": "Status updated successfully",
                "data": {"message_id": "f47ac10b-58cc-4372-a567-0e02b2c3d479"}
            }
        }
    }

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

class TranslationResult(BaseModel):
    """Translation result data"""
    translated_text: str = Field(..., description="The translated text")
    model_used: Optional[str] = Field(None, description="The model that was used for translation")
    completed_at: Optional[str] = Field(None, description="Timestamp when translation was completed")
    
    model_config = {
        "protected_namespaces": (),
        "json_schema_extra": {
            "example": {
                "translated_text": "སྐད་ཡིག་འགྱུར་བ་བྱས་པ།",
                "model_used": "claude-3-haiku-20240307",
                "completed_at": "2024-01-15T10:30:00Z"
            }
        }
    }

class Message(BaseModel):
    content: str = Field(..., description="Text content to be translated", min_length=1)
    model_name: str = Field(..., description="Name of the translation model to use (e.g., 'gpt-4', 'claude-3-haiku-20240307', 'gemini-pro')")
    api_key: str = Field(..., description="API key for the translation model", min_length=1)
    priority: Optional[int] = Field(0, description="Priority level (0-10, higher numbers = higher priority)", ge=0, le=10)
    metadata: Optional[Dict[str, Any]] = Field(None, description="Optional metadata for the translation job")
    webhook: Optional[str] = Field(None, description="Optional webhook URL for status updates")
    use_segmentation: Optional[str] = Field("botok", description="Segmentation method to use. Options: 'botok' for Tibetan segmentation, 'sentence' for sentence-based, 'newline' for newline-based, or None for no segmentation")
    
    model_config = {
        "protected_namespaces": (),
        "json_schema_extra": {
            "example": {
                "api_key": "sk-1234567890abcdef",
                "content": "Hello world! This text needs to be translated.",
                "metadata": {
                    "domain": "general",
                    "source_language": "english",
                    "target_language": "tibetan"
                },
                "model_name": "claude-3-haiku-20240307",
                "priority": 5,
                "use_segmentation": "botok",
                "webhook": "https://example.com/webhook"
            }
        }
    }

class MessageResponse(BaseModel):
    success: bool = Field(True, description="Indicates if the operation was successful")
    id: str = Field(..., description="Unique identifier for the message")
    status: TranslationStatus = Field(..., description="Current status of the translation")
    position: Optional[int] = Field(None, description="Position in the queue (if pending)")
    
    model_config = {
        "protected_namespaces": (),
        "json_schema_extra": {
            "example": {
                "success": True,
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

class MessageStatusResponse(BaseModel):
    """Response model for message status queries"""
    success: bool = Field(True, description="Indicates if the operation was successful")
    id: str = Field(..., description="Message ID")
    status: TranslationStatus = Field(..., description="Current translation status")
    result: Optional[TranslationResult] = Field(None, description="Translation result (only present when status is 'completed')")
    created_at: Optional[float] = Field(None, description="Timestamp when message was created")
    
    model_config = {
        "protected_namespaces": (),
        "json_schema_extra": {
            "example": {
                "success": True,
                "id": "f47ac10b-58cc-4372-a567-0e02b2c3d479",
                "status": {
                    "progress": 100.0,
                    "status_type": "completed",
                    "message": "Translation completed successfully"
                },
                "result": {
                    "translated_text": "སྐད་ཡིག་འགྱུར་བ་བྱས་པ།",
                    "model_used": "claude-3-haiku-20240307",
                    "completed_at": "2024-01-15T10:30:00Z"
                },
                "created_at": 1705312200.0
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
    progress: float = Field(..., description="Progress percentage (0-100)", ge=0, le=100)
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
