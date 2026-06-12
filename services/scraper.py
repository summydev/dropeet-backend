import httpx
import logging
from bs4 import BeautifulSoup
from playwright.async_api import async_playwright
from typing import Tuple, Optional

logger = logging.getLogger(__name__)

async def scrape_webpage(url: str) -> Tuple[str, Optional[bytes], Optional[str]]:
    """
    Scrapes a URL using Playwright, extracting text and any relevant OG images/flyers.
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
            # Bypass social media trackers by waiting for DOM instead of network idle
            await page.goto(url, wait_until="domcontentloaded", timeout=20000)
            await page.wait_for_timeout(4000) 
            
            html = await page.content()
            soup = BeautifulSoup(html, "html.parser")
            cleaned_text = soup.get_text(separator="\n", strip=True)
            
            # Look for flyer graphics
            img_element = await page.query_selector("meta[property='og:image']")
            if img_element:
                img_url = await img_element.get_attribute("content")
                if img_url and img_url.startswith("http"):
                    async with httpx.AsyncClient() as http_client:
                        img_response = await http_client.get(img_url, timeout=10.0)
                        if img_response.status_code == 200:
                            image_bytes = img_response.content
                            image_mime = "image/jpeg" if "jpg" in img_url or "jpeg" in img_url else "image/png"
            
            # Secondary flyer fallback
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