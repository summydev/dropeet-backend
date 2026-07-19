import logging
from typing import List
from fastapi import APIRouter, Depends, HTTPException, BackgroundTasks
from sqlalchemy.orm import Session

from schemas.opportunity import LinkRequest, OpportunityResponse, OpportunityUpdateRequest
from database.models import Opportunity, User, OpportunityStatus
from services.tasks import process_link_task
from services.google_calendar import sync_to_google_calendar
from api.deps import get_db, get_current_user

logger = logging.getLogger(__name__)

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
    """
    Allows users to edit an opportunity. 
    If a deadline is set, it performs a clean sync to their Google Calendar.
    """
    
    # 1. Find the opportunity and ensure this user actually owns it
    opp = db.query(Opportunity).filter(
        Opportunity.id == opportunity_id, 
        Opportunity.user_id == current_user.id
    ).first()
    
    if not opp:
        raise HTTPException(status_code=404, detail="Opportunity not found.")

    # 2. Check if the deadline is being changed
    deadline_changed = opp.deadline != request.deadline

    # 3. Apply the user's edits
    opp.title = request.title
    opp.organization = request.organization
    opp.deadline = request.deadline
    opp.summary = request.summary
    
    # 4. Push to Google Calendar with safety checks
    if opp.deadline:
        try:
            # Only sync if the status wasn't actioned yet, OR if they changed the deadline date
            if opp.status != OpportunityStatus.ACTIONED or deadline_changed:
                logger.info(f"🔄 Syncing updated details/deadline for: {opp.title}")
                
                # Hand it over to your Google Calendar service
                sync_to_google_calendar(opp, db)
                opp.status = OpportunityStatus.ACTIONED 
        except Exception as e:
            # Log the error but don't crash the update; let the user still save their text edits
            logger.error(f"❌ Failed to sync updated opportunity to Google Calendar: {e}")

    db.commit()
    db.refresh(opp)
    
    return opp
@router.put("/linkedin-cookies")
async def save_linkedin_cookies(
    cookies: dict,   # e.g. {"li_at": "AQEDAT..."}
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """Stores the user's LinkedIn session cookie for scraping."""
    current_user.linkedin_cookies = cookies
    db.commit()
    return {"status": "success"}
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