from pydantic import BaseModel, Field
from typing import Optional, Any, Dict

class ReportCreate(BaseModel):
    """The JSON payload expected from the frontend."""
    reason: str = Field(..., description="The category of the issue (e.g., 'wrong deadline')")
    message: Optional[str] = Field(None, description="Optional context provided by the user")
    card_details: Dict[str, Any] = Field(..., description="The complete JSON object of the opportunity card")

class ReportResponse(BaseModel):
    """The success response sent back to the frontend."""
    status: str
    message: str