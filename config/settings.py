
import os
from pydantic_settings import BaseSettings, SettingsConfigDict
from pydantic import Field

class Settings(BaseSettings):
    # App Configurations
    APP_NAME: str = "Dropeet API"
    ENVIRONMENT: str = Field(default="development", description="development, staging, or production")
    
    # Database Configuration
    DATABASE_URL: str = Field(..., description="PostgreSQL connection URL string")
    
    # Google OAuth Configuration
    GOOGLE_CLIENT_SECRETS_FILE: str = Field(default="client_secret.json")
    GOOGLE_REDIRECT_URI: str = Field(..., description="The exact OAuth callback URL registered in Google Console")
    # --- NEW JWT SETTINGS ---
    JWT_SECRET_KEY: str = Field(...)
    JWT_ALGORITHM: str = "HS256"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 60 * 24 * 7 # 7 days
    # Tell Pydantic to read from a .env file automatically
    model_config = SettingsConfigDict(
        env_file=".env", 
        env_file_encoding="utf-8",
        extra="ignore" # Ignores extra variables in the .env file that aren't defined here
    )

# Instantiate the settings object to be imported across the app
settings = Settings()