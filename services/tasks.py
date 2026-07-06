import logging
import asyncio
from datetime import datetime, timezone
from database.session import SessionLocal
from database.models import Opportunity, OpportunityStatus

# Import both standard scraping and Bright Data routers
from services.scraper import scrape_webpage, fetch_from_brightdata

# Note: Corrected import pointing to your actual file name
from services.ai_pipeline import extract_opportunity_details_deepseek

from services.google_calendar import sync_to_google_calendar

logger = logging.getLogger(__name__)

# Single task concurrency bouncer
scraping_semaphore = asyncio.Semaphore(1)

async def process_link_task(url: str, user_id: int, auto_sync: bool):
    """
    The main background worker pipeline: Domain Check Router -> Scrape -> DeepSeek Extract -> Save DB -> Contextual Auto-Sync.
    """
    
    async with scraping_semaphore:
        logger.info(f"🚦 Worker picked up link from queue: {url}")

        # 1. Domain Check Router: Intercept heavy social networks
        cleaned_text = ""
        if "linkedin.com" in url or "instagram.com" in url:
            cleaned_text = await fetch_from_brightdata(url)
        else:
            cleaned_text, _, _ = await scrape_webpage(url)

        if not cleaned_text:
            logger.error(f"Pipeline aborted: Scraping engine returned zero payload content for {url}")
            return

        # 2. Extract Data using DeepSeek (Text-Only structure processing)
        extracted_data = extract_opportunity_details_deepseek(cleaned_text)
        if not extracted_data:
            logger.error(f"Pipeline aborted: DeepSeek extraction failed for {url}")
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
                source_url=url,
                status=OpportunityStatus.PENDING
            )
            db.add(new_opp)
            db.commit()
            db.refresh(new_opp)
            logger.info(f"✅ Saved Draft to DB: {new_opp.title}")
            
            # 4. Perform background sync ONLY if user checked the consent toggle
            if auto_sync and new_opp.deadline:
                try:
                    logger.info(f"🔄 Auto-sync requested. Syncing {new_opp.title} to Google Calendar...")
                    sync_to_google_calendar(new_opp, db)
                    new_opp.status = OpportunityStatus.ACTIONED
                    db.commit()
                    logger.info(f"📆 Background calendar sync complete for: {new_opp.title}")
                except Exception as cal_err:
                    logger.error(f"❌ Background Calendar Sync Failure: {cal_err}")
                    # Keep status as PENDING so they can review and click sync manually on the dashboard
                
        except Exception as e:
            logger.error(f"❌ Worker Database Failure: {e}")
        finally:
            db.close()