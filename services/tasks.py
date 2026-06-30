import logging
import asyncio  # 1. IMPORT ASYNCIO HERE
from datetime import datetime, timezone
from database.session import SessionLocal
from database.models import Opportunity
from services.scraper import scrape_webpage
from services.ai_pipeline import extract_opportunity_details

logger = logging.getLogger(__name__)

# 2. DEFINE THE SEMAPHORE HERE at the module level.
# This acts as the bouncer, ensuring only 1 background task runs at a time.
scraping_semaphore = asyncio.Semaphore(1)

async def process_link_task(url: str, user_id: int):
    """
    The main background worker pipeline: Scrape -> AI Extract -> Save DB.
    (Calendar sync is now triggered manually by the user via the frontend).
    """
    
    # 3. WRAP THE ENTIRE PROCESSING LOGIC IN THE SEMAPHORE
    async with scraping_semaphore:
        logger.info(f"🚦 Worker picked up link from queue: {url}")

        # 1. Scrape the URL (This runs safely knowing no other browser instance is active)
        cleaned_text, image_bytes, image_mime = await scrape_webpage(url)
        if not cleaned_text:
            logger.error(f"Pipeline aborted: Scraping failed for {url}")
            return

        # 2. Extract Data via Gemini
        extracted_data = extract_opportunity_details(cleaned_text, image_bytes, image_mime)
        if not extracted_data:
            logger.error(f"Pipeline aborted: AI extraction failed for {url}")
            return

        # 3. Save to Database as a Draft
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
            logger.info(f"✅ Saved Draft to DB: {new_opp.title}")
            
            # NOTE: Auto-sync removed! The frontend will trigger the sync after user confirmation.
                
        except Exception as e:
            logger.error(f"❌ Worker Database Failure: {e}")
        finally:
            db.close()