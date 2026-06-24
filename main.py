from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from config.settings import settings

from api.v1.opportunities import router as opportunities_router
from api.v1.auth import router as auth_router # <-- UNCOMMENTED

app = FastAPI(
    title=settings.APP_NAME, 
    version="1.1",
    description="Dropeet backend API for extracting and tracking opportunities."
)

# CORS Configuration
app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:3000",           # Allows your frontend developer to test locally
        "https://your-frontend-domain.com" # Replace with your live frontend URL later!
    ], 
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Register your modular routers
app.include_router(opportunities_router, prefix="/api/v1")
app.include_router(auth_router, prefix="/api/v1") # <-- UNCOMMENTED

@app.get("/")
def root():
    return {"message": "Welcome to the Dropeet API"}

@app.get("/health")
def health_check():
    return {"status": "healthy", "environment": settings.ENVIRONMENT}