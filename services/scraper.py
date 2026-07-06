import os
import json
import logging
from bs4 import BeautifulSoup
import httpx
from playwright.async_api import async_playwright
from typing import Tuple, Optional

# Import the new Bright Data SDK
from brightdata import BrightDataClient

logger = logging.getLogger(__name__)

async def fetch_from_brightdata(url: str) -> str:
    """
    Uses the official Bright Data SDK to scrape LinkedIn/Instagram using their pre-built platform scrapers.
    """
    logger.info(f"🌐 Routing link through Bright Data SDK: {url}")
    
    # Pull the key from Render (ensure this matches your dashboard exactly)
    api_key = os.getenv("BRIGHTDATA_API_KEY")
    
    if not api_key:
        logger.error("❌ BRIGHTDATA_API_KEY is missing from environment variables.")
        return ""

    try:
        # Initialize the Async client
        async with BrightDataClient(token=api_key) as client:
            
            # Route to the correct pre-built scraper based on the URL
            if "linkedin.com/jobs" in url:
                logger.info("Using LinkedIn Jobs scraper...")
                response = await client.scrape.linkedin.jobs(url=url)
            elif "linkedin.com" in url:
                logger.info("Using LinkedIn Posts scraper...")
                response = await client.scrape.linkedin.posts(url=url)
            elif "instagram.com" in url:
                logger.info("Using Instagram Posts scraper...")
                response = await client.scrape.instagram.posts(url=url)
            else:
                logger.info("Using generic URL web unlocker...")
                response = await client.scrape_url(url)
            
            # The SDK returns a structured object where .data contains the payload
            if response and hasattr(response, 'data') and response.data:
                logger.info("✅ Bright Data successfully extracted content!")
                # Convert the raw extracted data (usually a dict or list) into a string 
                # so our DeepSeek AI pipeline can read and extract from it seamlessly!
                return json.dumps(response.data)
            else:
                logger.error(f"⚠️ Bright Data returned empty data for {url}")
                return ""
                
    except Exception as e:
        logger.error(f"❌ Bright Data SDK failed: {e}")
        return ""


async def scrape_webpage(url: str) -> Tuple[str, Optional[bytes], Optional[str]]:
    """
    Scrapes a standard URL using Playwright, extracting text and any relevant OG images/flyers.
    Returns: (cleaned_text, image_bytes, image_mime)
    """
    logger.info(f"🤖 Scraping webpage with Playwright: {url}")
    cleaned_text = ""
    image_bytes = None
    image_mime = None
    
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        context = await browser.new_context(
            user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
        )
        page = await context.new_page()
        
        try:
            await page.goto(url, wait_until="domcontentloaded", timeout=20000)
            await page.wait_for_timeout(4000) 
            
            html = await page.content()
            soup = BeautifulSoup(html, "html.parser")
            cleaned_text = soup.get_text(separator="\n", strip=True)
            
            img_element = await page.query_selector("meta[property='og:image']")
            if img_element:
                img_url = await img_element.get_attribute("content")
                if img_url and img_url.startswith("http"):
                    async with httpx.AsyncClient() as http_client:
                        img_response = await http_client.get(img_url, timeout=10.0)
                        if img_response.status_code == 200:
                            image_bytes = img_response.content
                            image_mime = "image/jpeg" if "jpg" in img_url or "jpeg" in img_url else "image/png"
            
            if not image_bytes:
                post_element = await page.query_selector("article, .feed-shared-update-v2__content, #main-content")
                if post_element:
                    image_bytes = await post_element.screenshot()
                    image_mime = "image/png"
                    
        except Exception as e:
            logger.error(f"❌ Scraping phase issue: {e}")
        finally:
            await browser.close()
            
    return cleaned_text, image_bytes, image_mime