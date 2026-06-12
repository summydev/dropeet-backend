from pydantic import BaseModel, ConfigDict
from datetime import datetime

# ==========================================
# 1. Token Output Schema
# ==========================================
class TokenResponse(BaseModel):
    """The payload returned to the frontend upon successful Google login."""
    status: str
    message: str
    access_token: str
    token_type: str

# ==========================================
# 2. User Profile Output Schema
# ==========================================
class UserResponse(BaseModel):
    """The safe user data exposed to the frontend (strips out OAuth secrets)."""
    id: int
    email: str
    created_at: datetime

    # Tells Pydantic to read directly from the SQLAlchemy User model
    model_config = ConfigDict(from_attributes=True)