import httpx
from fastapi import APIRouter, Depends, Request, HTTPException
from fastapi.responses import RedirectResponse
from sqlalchemy.orm import Session
from google_auth_oauthlib.flow import Flow

from config.settings import settings
from database.models import GoogleCredential, User
from api.deps import get_db, create_access_token

router = APIRouter(prefix="/auth/google", tags=["Authentication"])

SCOPES = ['https://www.googleapis.com/auth/calendar.events']

@router.get("/login")
async def login_via_google():
    """Step 1: Redirects the user to Google's consent screen."""
    flow = Flow.from_client_secrets_file(
        settings.GOOGLE_CLIENT_SECRETS_FILE, scopes=SCOPES
    )
    flow.redirect_uri = settings.GOOGLE_REDIRECT_URI
    
    authorization_url, state = flow.authorization_url(
        access_type='offline',
        prompt='consent',
        include_granted_scopes='true'
    )
    return RedirectResponse(authorization_url)

@router.get("/callback")
async def google_auth_callback(request: Request, db: Session = Depends(get_db)):
    """Step 2: Google sends the user back here to swap the code for tokens."""
    state = request.query_params.get("state")
    code = request.query_params.get("code")
    
    flow = Flow.from_client_secrets_file(
        settings.GOOGLE_CLIENT_SECRETS_FILE, scopes=SCOPES, state=state
    )
    flow.redirect_uri = settings.GOOGLE_REDIRECT_URI
    
    flow.fetch_token(authorization_response=str(request.url))
    credentials = flow.credentials
    
    # Fetch User Profile from Google
    async with httpx.AsyncClient() as client:
        response = await client.get(
            "https://www.googleapis.com/oauth2/v2/userinfo",
            headers={"Authorization": f"Bearer {credentials.token}"}
        )
        user_info = response.json()
        
    email = user_info.get("email")
    if not email:
        raise HTTPException(status_code=400, detail="Google account has no email attached.")

    # Find or Create User
    user = db.query(User).filter(User.email == email).first()
    if not user:
        user = User(email=email)
        db.add(user)
        db.commit()
        db.refresh(user)

    # Upsert Google Credentials
    db_cred = db.query(GoogleCredential).filter(GoogleCredential.user_id == user.id).first()
    if not db_cred:
        db_cred = GoogleCredential(user_id=user.id)
        db.add(db_cred)
        
    db_cred.access_token = credentials.token
    if credentials.refresh_token:
        db_cred.refresh_token = credentials.refresh_token
    db_cred.token_uri = credentials.token_uri
    db_cred.client_id = credentials.client_id
    db_cred.client_secret = credentials.client_secret
    db_cred.scopes = ",".join(credentials.scopes)
    
    db.commit()
    
    # Generate JWT for the Frontend
    access_token = create_access_token(data={"sub": str(user.id)})
    
    # Redirect back to the frontend application!
    # Update this URL to wherever your frontend developer is hosting the app later
    frontend_dashboard_url = "http://localhost:3000/dashboard" 
    
    return RedirectResponse(url=f"{frontend_dashboard_url}?token={access_token}")