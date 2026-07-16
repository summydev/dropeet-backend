import logging
from datetime import timedelta, datetime, timezone
from google.oauth2.credentials import Credentials
from googleapiclient.discovery import build
from sqlalchemy.orm import Session

from database.models import Opportunity, GoogleCredential

logger = logging.getLogger(__name__)

def get_smart_reminders(deadline: datetime) -> list:
    """
    Dynamically calculates up to 5 Google Calendar reminders based on how far away the deadline is.
    """
    # Ensure deadline is timezone aware for accurate math
    if deadline.tzinfo is None:
        deadline = deadline.replace(tzinfo=timezone.utc)
        
    now = datetime.now(timezone.utc)
    time_left = deadline - now
    days_left = time_left.days
    hours_left = time_left.total_seconds() / 3600

    overrides = []
    
    # 1. We ALWAYS want a 1-hour popup alert if there is at least an hour left
    if hours_left > 1:
        overrides.append({'method': 'popup', 'minutes': 60})

    # 2. Distribute the remaining 4 email slots based on urgency
    if days_left >= 30:
        overrides.extend([
            {'method': 'email', 'minutes': 28 * 24 * 60}, # 4 weeks
            {'method': 'email', 'minutes': 14 * 24 * 60}, # 2 weeks
            {'method': 'email', 'minutes': 7 * 24 * 60},  # 1 week
            {'method': 'email', 'minutes': 24 * 60},      # 1 day
        ])
    elif days_left >= 7:
        overrides.extend([
            {'method': 'email', 'minutes': 7 * 24 * 60},  # 1 week
            {'method': 'email', 'minutes': 3 * 24 * 60},  # 3 days
            {'method': 'email', 'minutes': 2 * 24 * 60},  # 2 days
            {'method': 'email', 'minutes': 24 * 60},      # 1 day
        ])
    elif hours_left >= 48:
        overrides.extend([
            {'method': 'email', 'minutes': 48 * 60},      # 48 hours
            {'method': 'email', 'minutes': 24 * 60},      # 24 hours
            {'method': 'email', 'minutes': 12 * 60},      # 12 hours
            {'method': 'email', 'minutes': 6 * 60},       # 6 hours
        ])
    else:
        # Less than 48 hours! Fire them off closely.
        if hours_left > 24: overrides.append({'method': 'email', 'minutes': 24 * 60})
        if hours_left > 12: overrides.append({'method': 'email', 'minutes': 12 * 60})
        if hours_left > 6:  overrides.append({'method': 'email', 'minutes': 6 * 60})
        if hours_left > 3:  overrides.append({'method': 'email', 'minutes': 3 * 60})

    # Google strictly limits this array to 5 items maximum.
    return overrides[:5]


def sync_to_google_calendar(opportunity: Opportunity, db: Session):
    """Silently pushes (or updates) an opportunity deadline on the user's Google Calendar."""
    
    if not opportunity.deadline:
        logger.info(f"No deadline for Opp {opportunity.id}. Skipping calendar sync.")
        return

    # 1. Fetch the user's saved Google credentials from the database
    db_cred = db.query(GoogleCredential).filter(GoogleCredential.user_id == opportunity.user_id).first()
    
    if not db_cred or not db_cred.refresh_token:
        logger.warning(f"User {opportunity.user_id} has not connected Google Calendar.")
        return

    # 2. Rebuild the Google Credentials object
    creds = Credentials(
        token=db_cred.access_token,
        refresh_token=db_cred.refresh_token,
        token_uri=db_cred.token_uri,
        client_id=db_cred.client_id,
        client_secret=db_cred.client_secret,
        scopes=db_cred.scopes.split(",")
    )

    try:
        # 3. Connect to the Calendar API
        service = build('calendar', 'v3', credentials=creds)
        
        # 4. Generate the smart reminders array!
        smart_reminders = get_smart_reminders(opportunity.deadline)
        
        # 5. Format the Event
        end_time = opportunity.deadline + timedelta(hours=1)
        event_body = {
            'summary': f"⏰ Dropeet: {opportunity.title}",
            'location': opportunity.source_url,
            'description': f"Organization: {opportunity.organization}\n\nSummary:\n{opportunity.summary}\n\nOriginal Link: {opportunity.source_url}",
            'start': {
                'dateTime': opportunity.deadline.isoformat(),
                'timeZone': 'UTC',
            },
            'end': {
                'dateTime': end_time.isoformat(),
                'timeZone': 'UTC',
            },
            'reminders': {
                'useDefault': False,
                'overrides': smart_reminders, # Injecting our smart calculation here!
            },
        }

        # 6. Insert OR Update the event
        if opportunity.calendar_event_id:
            try:
                service.events().update(
                    calendarId='primary', 
                    eventId=opportunity.calendar_event_id, 
                    body=event_body
                ).execute()
                logger.info(f"📅 Successfully UPDATED Opp {opportunity.id} on Google Calendar!")
                return 
            except Exception as update_err:
                logger.warning(f"Could not update event {opportunity.calendar_event_id}. Creating a new one. Error: {update_err}")

        # 7. Create a brand new event
        created_event = service.events().insert(calendarId='primary', body=event_body).execute()
        
        # 8. Save the Google Event ID back to your database
        opportunity.calendar_event_id = created_event.get('id')
        db.commit()
        
        logger.info(f"📅 Successfully INSERTED Opp {opportunity.id} to Google Calendar!")
        
    except Exception as e:
        logger.error(f"❌ Failed to sync to Google Calendar: {e}")