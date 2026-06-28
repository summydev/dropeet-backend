from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from config.settings import settings

from api.v1.opportunities import router as opportunities_router
from api.v1.auth import router as auth_router

# --- 1. ADD YOUR DATABASE IMPORTS HERE ---
# Note: Ensure 'engine' is correctly imported from wherever you defined it 
# (usually database.session or database.database)
from database.session import Base, engine 
import database.models  # This ensures SQLAlchemy sees your tables before creating them

# --- 2. ADD THIS LINE TO CREATE THE TABLES ---
Base.metadata.create_all(bind=engine)

app = FastAPI(
    title=settings.APP_NAME, 
    version="1.1",
    description="Dropeet backend API for extracting and tracking opportunities."
)

# --- 3. FIX YOUR CORS TO ALLOW LIVE SERVER ---
# CORS Configuration
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],      # Allows all domains (perfect for Bearer token APIs)
    allow_credentials=False,  # We use tokens instead of cookies, so this must be False
    allow_methods=["*"],
    allow_headers=["*"],
)

# Register your modular routers
app.include_router(opportunities_router, prefix="/api/v1")
app.include_router(auth_router, prefix="/api/v1")

@app.get("/")
def root():
    return {"message": "Welcome to the Dropeet API"}

@app.get("/health")
def health_check():
    return {"status": "healthy", "environment": settings.ENVIRONMENT}