from pydantic import BaseModel, Field, ConfigDict
from typing import Optional, List, Dict
from datetime import datetime
from database.models import OpportunityStatus

# ==========================================
# 1. API Input Schemas
# ==========================================
class LinkRequest(BaseModel):
    url: str = Field(..., description="The URL of the opportunity to scrape")
    # auto_sync removed: users should NEVER auto-sync untrusted AI data. Force manual review.

class OpportunityUpdateRequest(BaseModel):
    title: str
    organization: Optional[str] = None
    deadline: Optional[datetime] = None
    timezone: Optional[str] = None
    summary: Optional[str] = None
    application_status: Optional[str] = None
    required_documents: Optional[List[str]] = None

# ==========================================
# 2. AI Extraction Schemas (UNTRUSTED)
# ==========================================
class CandidateOpportunity(BaseModel):
    """The strict schema the LLM must return. Treated as untrusted input."""
    title: str = Field(description="The title of the opportunity")
    organization: Optional[str] = Field(description="The company or institution")
    extracted_deadline: Optional[str] = Field(description="The exact text of the deadline found (e.g., 'October 4, 10:00 AM')")
    extracted_timezone: Optional[str] = Field(description="The timezone mentioned, if any")
    location: Optional[str] = Field(description="Physical location or 'Virtual/Online'")
    summary: str = Field(description="A brief 2-sentence summary of the opportunity")
    required_documents: List[str] = Field(default_factory=list)
    confidence_score: float = Field(description="A float between 0.0 and 1.0 representing extraction confidence")
    evidence: Dict[str, str] = Field(
        description="A mapping of fields to the exact text snippets from the page that prove them. E.g., {'deadline': 'Applications close Friday at 5pm'}"
    )

class CandidateExtractionList(BaseModel):
    """The uniform container format passed to the LLM."""
    opportunities: List[CandidateOpportunity]

# ==========================================
# 3. Deterministic Internal Schemas (TRUSTED)
# ==========================================
class ValidatedOpportunity(BaseModel):
    """The deterministic schema created by your backend after parsing the CandidateOpportunity."""
    title: str
    organization: Optional[str]
    source_url: str
    deadline: Optional[datetime]
    timezone: str
    location: Optional[str]
    summary: Optional[str]
    required_documents: List[str]
    idempotency_key: str
    confidence: float
    evidence: Dict[str, str]
    is_ambiguous: bool = False # Flag if the backend validator couldn't confidently parse the LLM's 'extracted_deadline'

# ==========================================
# 4. API Output Schemas
# ==========================================
class OpportunityResponse(BaseModel):
    """The formatted data returned to the frontend."""
    id: int
    title: str
    organization: Optional[str]
    deadline: Optional[datetime]
    timezone: Optional[str]
    location: Optional[str]
    summary: Optional[str]
    source_url: str
    status: OpportunityStatus
    application_status: str
    required_documents: List[str]
    calendar_event_id: Optional[str]
    confidence: Optional[float]
    evidence: Optional[Dict[str, str]]
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)