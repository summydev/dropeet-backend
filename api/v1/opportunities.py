from typing import List
from fastapi import APIRouter, Depends, HTTPException, BackgroundTasks
from sqlalchemy.orm import Session

from schemas.opportunity import LinkRequest, OpportunityResponse, OpportunityUpdateRequest
from database.models import Opportunity, User, OpportunityStatus
from services.tasks import process_link_task
from services.google_calendar import sync_to_google_calendar
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

    # Handoff to background worker with the authenticated user's ID AND the auto_sync flag
    background_tasks.add_task(process_link_task, request.url, current_user.id, request.auto_sync)
    
    return {"status": "success", "message": "Link ingested and queued for extraction."}

@router.get("", response_model=List[OpportunityResponse])
async def get_opportunities(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user) # Security checkpoint
):
    """Fetches all saved opportunities ONLY for the currently logged-in user."""
    
    records = db.query(Opportunity).filter(Opportunity.user_id == current_user.id).all()
    return records

@router.put("/{opportunity_id}", response_model=OpportunityResponse)
async def update_and_sync_opportunity(
    opportunity_id: int,
    request: OpportunityUpdateRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """Allows users to edit an opportunity and explicitly sync it to their calendar."""
    
    # 1. Find the opportunity and ensure this user actually owns it
    opp = db.query(Opportunity).filter(
        Opportunity.id == opportunity_id, 
        Opportunity.user_id == current_user.id
    ).first()
    
    if not opp:
        raise HTTPException(status_code=404, detail="Opportunity not found.")

    # 2. Apply the user's edits
    opp.title = request.title
    opp.organization = request.organization
    opp.deadline = request.deadline
    opp.summary = request.summary
    
    # 3. Push to Google Calendar using your existing service
    if opp.deadline:
        sync_to_google_calendar(opp, db)
        # Update the status to show it's been handled!
        opp.status = OpportunityStatus.ACTIONED 
    
    db.commit()
    db.refresh(opp)
    
    return opp

@router.delete("/{opportunity_id}")
async def delete_opportunity(
    opportunity_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user) # Security checkpoint
):
    """Deletes a specific opportunity draft."""
    
    # 1. Find the opportunity and verify ownership
    opp = db.query(Opportunity).filter(
        Opportunity.id == opportunity_id,
        Opportunity.user_id == current_user.id
    ).first()

    # 2. Throw a 404 if it doesn't exist or doesn't belong to them
    if not opp:
        raise HTTPException(status_code=404, detail="Opportunity not found.")

    # 3. Delete from database and commit
    db.delete(opp)
    db.commit()

    return {"status": "success", "message": "Draft deleted successfully."}