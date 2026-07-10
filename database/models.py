import enum
from datetime import datetime, timezone
from sqlalchemy import Column, Integer, String, DateTime, ForeignKey, Text, Enum,JSON
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func
from database.session import Base

class OpportunityStatus(enum.Enum):
    PENDING = "pending"
    ACTIONED = "actioned"
    DISCARDED = "discarded"

class User(Base):
    __tablename__ = "users"
    
    id = Column(Integer, primary_key=True, index=True)
    email = Column(String, unique=True, index=True, nullable=False)
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))
    
    # Relationships
    opportunities = relationship("Opportunity", back_populates="owner", cascade="all, delete-orphan")
    google_credentials = relationship("GoogleCredential", back_populates="user", uselist=False, cascade="all, delete-orphan")


class GoogleCredential(Base):
    __tablename__ = "google_credentials"
    
    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), unique=True, nullable=False)
    
    # OAuth 2.0 Tokens
    access_token = Column(String, nullable=False)
    refresh_token = Column(String, nullable=False)
    token_uri = Column(String, nullable=False)
    client_id = Column(String, nullable=False)
    client_secret = Column(String, nullable=False)
    scopes = Column(String, nullable=False)
    
    updated_at = Column(
        DateTime, 
        default=lambda: datetime.now(timezone.utc), 
        onupdate=lambda: datetime.now(timezone.utc)
    )

    # Relationships
    user = relationship("User", back_populates="google_credentials")


class Opportunity(Base):
    __tablename__ = "opportunities"
    
    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    
    title = Column(String, nullable=False)
    organization = Column(String, nullable=True)
    deadline = Column(DateTime, nullable=True)
    summary = Column(Text, nullable=True)
    source_url = Column(String, nullable=False)
    
    status = Column(Enum(OpportunityStatus), default=OpportunityStatus.PENDING)
    calendar_event_id = Column(String, nullable=True)
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))

    # Relationships
    owner = relationship("User", back_populates="opportunities")

class Report(Base):
    __tablename__ = "reports"

    id = Column(Integer, primary_key=True, index=True)
    # Link it to the user who submitted the report
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    # Store the reason and optional message
    reason = Column(String, nullable=False)
    message = Column(Text, nullable=True)
    # Store the entire exact payload of the card that failed
    card_details = Column(JSON, nullable=False)
    
    created_at = Column(DateTime(timezone=True), server_default=func.now())