import os
import json
import httpx
from fastapi import FastAPI, BackgroundTasks, HTTPException
from pydantic import BaseModel, Field
from typing import Optional
from bs4 import BeautifulSoup
from playwright.async_api import async_playwright
from google import genai
from google.genai import types

# ==========================================
# 1. API PAYLOAD & DATA SCHEMA
# ==========================================
class LinkRequest(BaseModel):
    url: str

class OpportunityData(BaseModel):
    title: str = Field(description="The title of the job, internship, scholarship, or opportunity")
    organization: str = Field(description="The company, institution, or organization offering it")
    deadline: Optional[str] = Field(description="The application deadline in YYYY-MM-DD format. Return None if not explicitly found.")
    summary: str = Field(description="A brief 2-sentence summary of the opportunity, including eligibility or key requirements.")

# ==========================================
# 2. FASTAPI APP SETUP
# ==========================================
app = FastAPI(title="Opportunity Tracker API", version="1.0")

# In-memory database for the pilot (replace with SQLite/PostgreSQL later)
database = []

# ==========================================
# 3. SCRAPING & AI EXTRACTION LOGIC
# ==========================================
async def scrape_and_extract(url: str):
    print(f"🤖 Scraping webpage with Playwright: {url}")
    
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
            print(f"❌ Scraping phase issue: {e}")
            if not cleaned_text:
                return None
        finally:
            await browser.close()

    print("🧠 Passing raw data to Gemini...")
    client = genai.Client()
    contents = [f"Extract the core opportunity details from this data:\n\n{cleaned_text}"]
    
    if image_bytes:
        contents.append(types.Part.from_bytes(data=image_bytes, mime_type=image_mime))
    
    # ---------------------------------------------------------
    # MULTI-TIER FALLBACK LOOP
    # ---------------------------------------------------------
    preferred_models = ["gemini-2.5-flash-lite", "gemini-1.5-flash"]
    
    for model_name in preferred_models:
        try:
            print(f"🔄 Attempting extraction with {model_name}...")
            response = client.models.generate_content(
                model=model_name,
                contents=contents,
                config=types.GenerateContentConfig(
                    response_mime_type="application/json",
                    response_schema=OpportunityData,
                    temperature=0.1 
                ),
            )
            return response.text
            
        except Exception as e:
            if "503" in str(e) or "UNAVAILABLE" in str(e):
                print(f"⚠️ {model_name} is busy. Falling back...")
                continue
            else:
                print(f"❌ Critical AI error: {e}")
                return None
    return None

# ==========================================
# 4. BACKGROUND WORKER
# ==========================================
async def process_link_in_background(url: str):
    extracted_json_string = await scrape_and_extract(url)
    
    if extracted_json_string:
        try:
            data = json.loads(extracted_json_string)
            data["source_url"] = url # Attach the original link to the data
            
            # 1. Save to database
            database.append(data)
            print(f"✅ Saved to DB: {data.get('title')} (Deadline: {data.get('deadline')})")
            
            # 2. TRIGGER GOOGLE CALENDAR (Stub for next step)
            if data.get('deadline'):
                print("📅 Preparing to push to Google Calendar...")
                # sync_to_google_calendar(data)
                
        except Exception as e:
            print(f"❌ Failed to parse JSON data: {e}")
    else:
        print(f"❌ Pipeline failed for: {url}")

# ==========================================
# 5. ENDPOINTS
# ==========================================
@app.post("/api/v1/opportunities")
async def add_opportunity(request: LinkRequest, background_tasks: BackgroundTasks):
    if not request.url.startswith("http"):
        raise HTTPException(status_code=400, detail="Invalid URL provided.")

    background_tasks.add_task(process_link_in_background, request.url)
    return {"status": "success", "message": "Processing in the background."}

@app.get("/api/v1/opportunities")
async def get_opportunities():
    return {"status": "success", "data": database}