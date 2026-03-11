from sqlalchemy import Column, Integer, String, Float, DateTime, Boolean, JSON
from datetime import datetime
from backend.database import Base

class User(Base):
    __tablename__ = "users"
    id = Column(Integer, primary_key=True, index=True)
    username = Column(String, unique=True, index=True)
    hashed_password = Column(String)
    is_active = Column(Boolean, default=True)

class Trade(Base):
    __tablename__ = "trades"
    id = Column(Integer, primary_key=True, index=True)
    ticker = Column(String, index=True)
    action = Column(String) # BUY, SELL
    price = Column(Float)
    quantity = Column(Float)
    timestamp = Column(DateTime, default=datetime.utcnow)
    pnl = Column(Float, nullable=True)
    status = Column(String, default="FILLED") # OPEN, FILLED, CANCELLED
    metadata_json = Column(JSON, nullable=True) # For strategy insights, etc.

class SystemSettings(Base):
    __tablename__ = "system_settings"
    id = Column(Integer, primary_key=True, index=True)
    key = Column(String, unique=True, index=True)
    value = Column(String)
    last_updated = Column(DateTime, default=datetime.utcnow)
