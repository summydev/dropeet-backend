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
    
    # JWT Settings
    JWT_SECRET_KEY: str = Field(...)
    JWT_ALGORITHM: str = "HS256"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 60 * 24 * 7 # 7 days

    # --- PIPELINE & AI SETTINGS (New) ---
    DEEPSEEK_API_KEY: str = Field(..., description="Required for the LLM extraction fallback")
    
    # Proxies (Optional, so we use default=None)
    RESIDENTIAL_PROXY_HOST: str | None = Field(default=None)
    RESIDENTIAL_PROXY_USER: str | None = Field(default=None)
    RESIDENTIAL_PROXY_PASS: str | None = Field(default=None)

    # Tell Pydantic to read from a .env file automatically
    model_config = SettingsConfigDict(
        env_file=".env", 
        env_file_encoding="utf-8",
        extra="ignore" # Ignores extra variables in the .env file that aren't defined here
    )

# Instantiate the settings object to be imported across the app
settings = Settings()