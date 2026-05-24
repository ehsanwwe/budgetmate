import bcrypt
from sqlalchemy.orm import Session
from app.models.admin import AdminUser
from app.models.category import Category
from app.core.config import settings


def _hash_password(password: str) -> str:
    return bcrypt.hashpw(password.encode(), bcrypt.gensalt()).decode()


def _verify_password(plain: str, hashed: str) -> bool:
    return bcrypt.checkpw(plain.encode(), hashed.encode())

DEFAULT_CATEGORIES = [
    {"name": "غذا و خوراک", "icon": "🍽️", "color": "#FF6B6B"},
    {"name": "حمل و نقل", "icon": "🚗", "color": "#4ECDC4"},
    {"name": "قبوض و شارژ", "icon": "💡", "color": "#FFE66D"},
    {"name": "خرید", "icon": "🛍️", "color": "#A8E6CF"},
    {"name": "سرگرمی", "icon": "🎮", "color": "#FF8B94"},
    {"name": "سلامت و درمان", "icon": "🏥", "color": "#88D8B0"},
    {"name": "پس‌انداز", "icon": "💰", "color": "#FFEAA7"},
    {"name": "آموزش", "icon": "📚", "color": "#DDA0DD"},
    {"name": "مسکن", "icon": "🏠", "color": "#98D8C8"},
    {"name": "سایر", "icon": "📦", "color": "#B0BEC5"},
]


def seed_db(db: Session):
    # Seed admin
    existing_admin = db.query(AdminUser).filter(AdminUser.username == settings.ADMIN_USERNAME).first()
    if not existing_admin:
        hashed = _hash_password(settings.ADMIN_PASSWORD)
        admin = AdminUser(username=settings.ADMIN_USERNAME, hashed_password=hashed)
        db.add(admin)
        db.commit()

    # Seed default categories
    for cat_data in DEFAULT_CATEGORIES:
        existing = db.query(Category).filter(
            Category.name == cat_data["name"],
            Category.is_default == True,
        ).first()
        if not existing:
            cat = Category(
                name=cat_data["name"],
                icon=cat_data["icon"],
                color=cat_data["color"],
                is_default=True,
                user_id=None,
            )
            db.add(cat)
    db.commit()
