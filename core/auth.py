# Internal project and standard library imports for authentication, database access, and logging.
# Integrates with: config/settings.py for valid IDs and core/database.py for persistent record checking.
from config.settings import VALID_ORDER_IDS
from core.database import SessionLocal
from core.models import Order
from utils.logger import setup_logger
from utils.exceptions import AuthenticationError, ValidationError
from utils.validators import validate_order_id

# Initialize the authentication-specific logger.
# Integrates with: utils/logger.py for tracking login attempts and database errors.
logger = setup_logger(__name__)


class AuthManager:
    @staticmethod
    def is_valid_order(order_id: str) -> bool:
        """
        Validate order ID against database and static list.
        
        Args:
            order_id: Raw order ID string
            
        Returns:
            True if valid, False otherwise
        """
        if not order_id:
            return False
        
        try:
            normalized_id = validate_order_id(order_id)
            logger.debug(f"Validating order ID: {normalized_id}")
            
            # Check static IDs for backward compatibility
            if normalized_id in [uid.upper() for uid in VALID_ORDER_IDS]:
                logger.info(f"Order ID validated (static): {normalized_id}")
                return True
            
            # Check database
            try:
                with SessionLocal() as db:
                    order = db.query(Order).filter(Order.order_id == normalized_id).first()
                    if order:
                        logger.info(f"Order ID validated (database): {normalized_id}")
                        return True
                    else:
                        logger.warning(f"Order ID not found: {normalized_id}")
                        return False
            except Exception as e:
                logger.error(f"Database error during auth: {e}", exc_info=True)
                return False
                
        except ValidationError as e:
            logger.warning(f"Invalid order ID format: {e.message}")
            return False