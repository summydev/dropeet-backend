from pydantic import BaseModel, Field, ConfigDict
from typing import Optional, List
from datetime import datetime
from database.models import OpportunityStatus

# ==========================================
# 1. API Input Schemas
# ==========================================
class LinkRequest(BaseModel):
    """Payload received from the frontend when a user drops a link."""
    url: str = Field(..., description="The URL of the opportunity to scrape")
    auto_sync: bool = Field(default=False, description="Whether to automatically push to Google Calendar after extraction")

class OpportunityUpdateRequest(BaseModel):
    """Payload received when a user edits an opportunity and wants to sync it."""
    title: str
    organization: Optional[str] = None
    deadline: Optional[datetime] = None
    summary: Optional[str] = None

# ==========================================
# 2. AI Extraction Schemas
# ==========================================
class OpportunityData(BaseModel):
    """The strict inner schema for a single extracted opportunity configuration."""
    title: str = Field(description="The title of the job, internship, scholarship, or opportunity")
    organization: str = Field(description="The company, institution, or organization offering it")
    deadline: Optional[str] = Field(description="The application deadline in YYYY-MM-DD format. Return None if not explicitly found.")
    summary: str = Field(description="A brief 2-sentence summary of the opportunity, including eligibility or key requirements.")

class OpportunityList(BaseModel):
    """The mandatory uniform container format that DeepSeek will ALWAYS match against."""
    opportunities: List[OpportunityData] = Field(description="List of extracted opportunity configurations discovered in the content payload.")

# ==========================================
# 3. API Output Schemas
# ==========================================
class OpportunityResponse(BaseModel):
    """The formatted data returned to the frontend when fetching saved items."""
    id: int
    title: str
    organization: Optional[str]
    deadline: Optional[datetime]
    summary: Optional[str]
    source_url: str
    status: OpportunityStatus
    calendar_event_id: Optional[str]
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)