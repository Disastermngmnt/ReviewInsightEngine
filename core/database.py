# SQLAlchemy components for engine creation, session management, and base class definition.
# Integrates with: The application's persistence layer to handle SQL database connections.
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker, declarative_base
import os

# Default database location (SQLite file).
# Integrates with: core/models.py for schema definition and core/auth.py for query execution.
DATABASE_URL = "sqlite:///./app.db"

# Create the SQLAlchemy engine. 
# check_same_thread=False is required for SQLite compatibility with multi-threaded FastAPI.
engine = create_engine(
    DATABASE_URL, connect_args={"check_same_thread": False}
)

# Factories for generating individual database sessions.
# Integrates with: main.py dependencies (get_db) to provide session context per request.
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

# Declarative base class that all database models must inherit from.
Base = declarative_base()

# Dependency function to provide a database session to FastAPI endpoints.
# Integrates with: main.py routes to ensure sessions are automatically opened and closed.
def get_db():
    db = SessionLocal()
    try:
        # Yield the session to the calling function.
        yield db
    finally:
        # Guarantee closure of the session to prevent connection leaks.
        db.close()
