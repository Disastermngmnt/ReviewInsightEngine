from core.database import SessionLocal, Base, engine
from core.models import Order
from config.settings import VALID_ORDER_IDS

def init_db():
    print("Creating tables...")
    Base.metadata.create_all(bind=engine)
    
    print("Seeding database with valid Order IDs...")
    with SessionLocal() as db:
        for order_id in VALID_ORDER_IDS:
            normalized_id = order_id.strip().upper()
            existing = db.query(Order).filter(Order.order_id == normalized_id).first()
            if not existing:
                new_order = Order(order_id=normalized_id)
                db.add(new_order)
                print(f"Added {normalized_id}")
            else:
                print(f"Already exists: {normalized_id}")
        db.commit()
    print("Database initialization complete.")

if __name__ == "__main__":
    init_db()
