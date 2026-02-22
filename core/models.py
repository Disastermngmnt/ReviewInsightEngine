from sqlalchemy import Column, Integer, String, DateTime, Text
from datetime import datetime
from .database import Base


# Database model for tracking global API or feature usage counts.
# Integrates with: main.py (/api/usage) to display total analysis volume on the pricing card.
class UsageStats(Base):
    """Track API usage statistics."""
    __tablename__ = "usage_stats"

    id = Column(Integer, primary_key=True, index=True)
    # The starting 'legacy' count or incrementing total usages.
    count = Column(Integer, default=1000)  
    last_updated = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)


# Database model for persistent authentication records (Order IDs).
# Integrates with: core/auth.py for validating user access beyond the static whitelist.
class Order(Base):
    """Store valid order IDs for authentication."""
    __tablename__ = "orders"
    
    id = Column(Integer, primary_key=True, index=True)
    # Unique identifier matching the user's purchase sequence.
    order_id = Column(String(50), unique=True, index=True, nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow)


# Database model for archival storage of generated analysis reports.
# Integrates with: The 'History' feature (if enabled) and internal audits to track engine output.
class AnalysisHistory(Base):
    """Store analysis history for auditing."""
    __tablename__ = "analysis_history"
    
    id = Column(Integer, primary_key=True, index=True)
    # Foreign reference to the order_id that triggered the analysis.
    order_id = Column(Integer, nullable=False)
    # Full JSON representation of the final roadmap_result.
    roadmap_result = Column(Text, nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow)
