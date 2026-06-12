import logging
from datetime import datetime, timezone
from database.session import SessionLocal
from database.models import Opportunity
from services.scraper import scrape_webpage
from services.ai_pipeline import extract_opportunity_details
# Assuming your calendar logic is in services/google_calendar.py
from services.google_calendar import sync_to_google_calendar 

logger = logging.getLogger(__name__)

async def process_link_task(url: str, user_id: int):
    """
    The main background worker pipeline: Scrape -> AI Extract -> Save DB -> Calendar Sync.
    """
    # 1. Scrape the URL
    cleaned_text, image_bytes, image_mime = await scrape_webpage(url)
    if not cleaned_text:
        logger.error(f"Pipeline aborted: Scraping failed for {url}")
        return

    # 2. Extract Data via Gemini
    extracted_data = extract_opportunity_details(cleaned_text, image_bytes, image_mime)
    if not extracted_data:
        logger.error(f"Pipeline aborted: AI extraction failed for {url}")
        return

    # 3. Save to Database
    db = SessionLocal()
    try:
        parsed_deadline = None
        if extracted_data.get("deadline"):
            try:
                parsed_deadline = datetime.strptime(extracted_data["deadline"], "%Y-%m-%d").replace(tzinfo=timezone.utc)
            except ValueError:
                logger.warning(f"Could not parse deadline string: {extracted_data.get('deadline')}")

        new_opp = Opportunity(
            user_id=user_id,
            title=extracted_data.get("title", "Unknown Opportunity"),
            organization=extracted_data.get("organization"),
            deadline=parsed_deadline,
            summary=extracted_data.get("summary"),
            source_url=url
        )
        db.add(new_opp)
        db.commit()
        db.refresh(new_opp)
        logger.info(f"✅ Saved to DB: {new_opp.title}")
        
        # 4. Trigger Calendar Sync
        if new_opp.deadline:
            sync_to_google_calendar(new_opp, db)
            
    except Exception as e:
        logger.error(f"❌ Worker Database Failure: {e}")
    finally:
        db.close()