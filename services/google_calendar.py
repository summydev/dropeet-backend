import logging
from datetime import timedelta
from google.oauth2.credentials import Credentials
from googleapiclient.discovery import build
from sqlalchemy.orm import Session

from database.models import Opportunity, GoogleCredential

logger = logging.getLogger(__name__)

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
    # If the access_token is expired, Google's library automatically uses the refresh_token to get a new one!
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
        
        # 4. Format the Event (Defaulting to a 1-hour block)
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
                'overrides': [
                    {'method': 'email', 'minutes': 24 * 60}, # Email 1 day before
                    {'method': 'popup', 'minutes': 60},      # Notification 1 hour before
                ],
            },
        }

        # 5. Insert OR Update the event
        if opportunity.calendar_event_id:
            try:
                # Attempt to update the existing event
                service.events().update(
                    calendarId='primary', 
                    eventId=opportunity.calendar_event_id, 
                    body=event_body
                ).execute()
                logger.info(f"📅 Successfully UPDATED Opp {opportunity.id} on Google Calendar!")
                return  # Exit early, we don't need to save the ID again
            except Exception as update_err:
                logger.warning(f"Could not update event {opportunity.calendar_event_id} (user may have manually deleted it). Creating a new one. Error: {update_err}")
                # If the update fails (like a 404 Not Found), fall through to the insert logic below

        # 6. Create a brand new event
        created_event = service.events().insert(calendarId='primary', body=event_body).execute()
        
        # 7. Save the Google Event ID back to your database
        opportunity.calendar_event_id = created_event.get('id')
        db.commit()
        
        logger.info(f"📅 Successfully INSERTED Opp {opportunity.id} to Google Calendar!")
        
    except Exception as e:
        logger.error(f"❌ Failed to sync to Google Calendar: {e}")