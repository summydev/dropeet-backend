import logging
import asyncio
from datetime import datetime, timezone
from database.session import SessionLocal
from database.models import Opportunity, OpportunityStatus

from services.scraper import scrape_webpage, fetch_from_brightdata
from services.ai_pipeline import extract_opportunity_details_deepseek
from services.google_calendar import sync_to_google_calendar

logger = logging.getLogger(__name__)

scraping_semaphore = asyncio.Semaphore(1)

async def process_link_task(url: str, user_id: int, auto_sync: bool):
    """
    The main background worker pipeline: Domain Check Router -> Scrape -> DeepSeek Extract -> Loop & Save DB Entries -> Contextual Auto-Sync.
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

        # 2. Extract Data using DeepSeek (Will ALWAYS return a list of items)
        extracted_opportunities = extract_opportunity_details_deepseek(cleaned_text)
        if not extracted_opportunities:
            logger.error(f"Pipeline aborted: DeepSeek extraction failed or returned zero array rows for {url}")
            return

        # 3. Open Session and Loop Save Database Records
        db = SessionLocal()
        try:
            logger.info(f"🗄️ Ingesting {len(extracted_opportunities)} parsed configuration items into DB context...")
            
            for opp_data in extracted_opportunities:
                parsed_deadline = None
                if opp_data.get("deadline"):
                    try:
                        parsed_deadline = datetime.strptime(opp_data["deadline"], "%Y-%m-%d").replace(tzinfo=timezone.utc)
                    except ValueError:
                        logger.warning(f"Could not parse deadline string: {opp_data.get('deadline')}")

                new_opp = Opportunity(
                    user_id=user_id,
                    title=opp_data.get("title", "Unknown Opportunity"),
                    organization=opp_data.get("organization"),
                    deadline=parsed_deadline,
                    summary=opp_data.get("summary"),
                    source_url=url,
                    status=OpportunityStatus.PENDING
                )
                db.add(new_opp)
                db.commit()
                db.refresh(new_opp)
                logger.info(f"✅ Saved Draft to DB: {new_opp.title}")
                
                # 4. Perform background sync per element ONLY if auto_sync toggle has permission
                if auto_sync and new_opp.deadline:
                    try:
                        logger.info(f"🔄 Auto-sync requested. Syncing {new_opp.title} to Google Calendar...")
                        sync_to_google_calendar(new_opp, db)
                        new_opp.status = OpportunityStatus.ACTIONED
                        db.commit()
                        logger.info(f"📆 Background calendar sync complete for: {new_opp.title}")
                    except Exception as cal_err:
                        logger.error(f"❌ Background Calendar Sync Failure for {new_opp.title}: {cal_err}")
                        # Leave transaction record state as PENDING for safe dashboard tracking fallbacks
                
        except Exception as e:
            logger.error(f"❌ Worker Database Failure during array injection sequence: {e}")
        finally:
            db.close()