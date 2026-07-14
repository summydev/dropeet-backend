from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from database.session import get_db
from database.models import Report
from schemas.report import ReportCreate, ReportResponse

# Import your auth dependency (adjust the import path based on where you keep it)
from api.deps import get_current_user 

router = APIRouter()

@router.post("/", response_model=ReportResponse, status_code=200)
def submit_report(
    report_in: ReportCreate, 
    db: Session = Depends(get_db), 
    current_user = Depends(get_current_user)
):
    """
    Accepts an AI accuracy report from the user and saves the context for review.
    """
    try:
        new_report = Report(
            user_id=current_user.id,
            reason=report_in.reason,
            message=report_in.message,
            card_details=report_in.card_details
        )
        db.add(new_report)
        db.commit()
        
        # TODO for later: You can easily add a requests.post() call right here 
        # to send `report_in.model_dump()` to a Slack or Discord webhook!

        return ReportResponse(status="success", message="Report successfully logged.")
        
    except Exception as e:
        db.rollback()
        raise HTTPException(status_code=500, detail="Failed to log report")