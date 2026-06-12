from typing import List
from fastapi import APIRouter, Depends, HTTPException, BackgroundTasks
from sqlalchemy.orm import Session

from schemas.opportunity import LinkRequest, OpportunityResponse
from database.models import Opportunity, User
from services.tasks import process_link_task
from api.deps import get_db, get_current_user

router = APIRouter(prefix="/opportunities", tags=["Opportunities"])

@router.post("", response_model=dict)
async def add_opportunity(
    request: LinkRequest, 
    background_tasks: BackgroundTasks, 
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user) # Security checkpoint
):
    if not request.url.startswith("http"):
        raise HTTPException(status_code=400, detail="Invalid URL provided.")

    # Handoff to background worker with the authenticated user's ID
    background_tasks.add_task(process_link_task, request.url, current_user.id)
    
    return {"status": "success", "message": "Link ingested and queued for extraction."}

@router.get("", response_model=List[OpportunityResponse])
async def get_opportunities(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user) # Security checkpoint
):
    """Fetches all saved opportunities ONLY for the currently logged-in user."""
    
    records = db.query(Opportunity).filter(Opportunity.user_id == current_user.id).all()
    return records