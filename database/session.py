from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker, declarative_base
from typing import Generator
from config.settings import settings

# Create the SQLAlchemy engine using the validated URL from your settings/env
engine = create_engine(
    settings.DATABASE_URL,
    pool_pre_ping=True,  # Automatically tests connections before using them
    pool_size=10,        # Good baseline for 100-1000 users
    max_overflow=20,
    connect_args={"sslmode": "require"} # <-- Required for Supabase/Cloud PostgreSQL connections
)

# SessionLocal will be used to create individual database sessions for each request
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

# Base class for your models to inherit from
Base = declarative_base()

def get_db() -> Generator:
    """
    Dependency generator that creates a new database session for a request
    and closes it when the request is finished.
    """
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()