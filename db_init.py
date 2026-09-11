"""Schema migrations and first-run seed data.

There is no Alembic here: ensure_column() issues an idempotent ALTER TABLE so
a column added to a model also appears on an existing database. init_database()
is called once by the app factory, so it runs under local development and under
Gunicorn alike.
"""

import logging

import json

from sqlalchemy import text
from werkzeug.security import generate_password_hash

from extensions import db
from helpers import safe_print as print
from models import Admin, Customer, Product, Room

logger = logging.getLogger(__name__)


def ensure_column(table_name, column_name, add_column_sql):
    """Add a column to a MySQL table if it doesn't already exist (idempotent, safe to call on every startup)."""
    try:
        exists = db.session.execute(text(
            "SELECT COUNT(*) FROM INFORMATION_SCHEMA.COLUMNS "
            "WHERE TABLE_SCHEMA = DATABASE() AND TABLE_NAME = :table_name AND COLUMN_NAME = :column_name"
        ), {'table_name': table_name, 'column_name': column_name}).scalar()

        if not exists:
            print(f"Adding {column_name} column to {table_name} table...")
            db.session.execute(text(add_column_sql))
            db.session.commit()
            print(f"{column_name} column added successfully")
    except Exception as e:
        db.session.rollback()
        logger.exception(f"{table_name}.{column_name} migration check failed")

def populate_default_basic_costs():
    try:
        rooms = Room.query.all()
        modified = False
        for r in rooms:
            if not r.basic_costs:
                costs = [
                    {"name": "Điện", "value": getattr(r, 'electricity_cost', None) or '3.6k/kWh', "icon": "bolt"},
                    {"name": "Nước", "value": getattr(r, 'water_cost', None) or '100.000 VNĐ/người', "icon": "droplet"},
                    {"name": "Dịch vụ", "value": getattr(r, 'service_cost', None) or '100.000 VNĐ/người', "icon": "file-invoice"}
                ]
                r.basic_costs = json.dumps(costs)
                modified = True
        if modified:
            db.session.commit()
            print("Populated default basic costs for existing rooms successfully")
    except Exception as e:
        logger.exception("Room basic costs data population skipped")



def init_database():
    """Create tables, apply column migrations, and seed a default admin,
    products and rooms the first time the app runs against an empty schema."""
    try:
        db.create_all()
        ensure_column('product', 'image', "ALTER TABLE product ADD COLUMN image VARCHAR(200) DEFAULT 'placeholder.jpg'")
        ensure_column('product', 'item_type', "ALTER TABLE product ADD COLUMN item_type VARCHAR(20) NOT NULL DEFAULT 'drink'")
        ensure_column('product', 'is_daily', "ALTER TABLE product ADD COLUMN is_daily TINYINT(1) NOT NULL DEFAULT 0")
        ensure_column('room', 'basic_costs', "ALTER TABLE room ADD COLUMN basic_costs TEXT")
        ensure_column('room', 'price_unit', "ALTER TABLE room ADD COLUMN price_unit VARCHAR(50) DEFAULT 'giờ'")
        ensure_column('admin', 'role', "ALTER TABLE admin ADD COLUMN role VARCHAR(20) NOT NULL DEFAULT 'admin'")
        ensure_column('customer', 'role', "ALTER TABLE customer ADD COLUMN role VARCHAR(20) NOT NULL DEFAULT 'customer'")
        ensure_column('admin', 'reset_code_hash', "ALTER TABLE admin ADD COLUMN reset_code_hash VARCHAR(255)")
        ensure_column('admin', 'reset_code_expiry', "ALTER TABLE admin ADD COLUMN reset_code_expiry DATETIME")
        ensure_column('admin', 'reset_code_attempts', "ALTER TABLE admin ADD COLUMN reset_code_attempts INT NOT NULL DEFAULT 0")
        populate_default_basic_costs()

        # Create default admin if not exists
        admin = Admin.query.filter_by(username='admin').first()
        if not admin:
            admin = Admin(username='admin', password=generate_password_hash('admin123'), role='super_admin')
            db.session.add(admin)

            # Add some sample products
            products = [
                Product(name='Espresso', description='Cà phê đậm đậm nguyên chất từ hạt Arabica', price=45000, stock=50, category='coffee'),
                Product(name='Cappuccino', description='Cà phê với bọt sữa kem mịn', price=55000, stock=40, category='coffee'),
                Product(name='Latte', description='Cà phê sữa với lớp latte art đẹp mắt', price=60000, stock=35, category='coffee'),
                Product(name='Mocha', description='Cà phê kết hợp với chocolate đắng ngọt', price=65000, stock=30, category='coffee'),
                Product(name='Americano', description='Cà phê pha loãng với vị nguyên bản', price=50000, stock=45, category='coffee'),
                Product(name='Macchiato', description='Cà phê với chút sữa kem trên cùng', price=58000, stock=25, category='coffee'),
                Product(name='Flat White', description='Cà phê sữa với bọt mỏng', price=52000, stock=38, category='coffee'),
                Product(name='Cold Brew', description='Cà phê lạnh ngâm 24 giờ', price=48000, stock=42, category='coffee')
            ]

            for product in products:
                db.session.add(product)

            # Add sample rooms
            rooms = [
                Room(
                    name='Phòng VIP 1',
                    description='Phòng sang trọng với view đẹp, đầy đủ tiện nghi cao cấp, phù hợp cho họp nhóm hoặc nghỉ dưỡng.',
                    price_per_hour=150000,
                    capacity=4,
                    amenities=json.dumps(['WiFi', 'Điều hòa', 'TV 65 inch', 'Bàn làm việc', 'Ghế sofa', 'Máy pha cà phê', 'Mini bar']),
                    available=True
                ),
                Room(
                    name='Phòng Standard 2',
                    description='Phòng tiêu chuẩn với không gian ấm cúng, trang bị đầy đủ các tiện nghi cần thiết.',
                    price_per_hour=80000,
                    capacity=2,
                    amenities=json.dumps(['WiFi', 'Điều hòa', 'TV 43 inch', 'Bàn làm việc', 'Ghế văn phòng']),
                    available=True
                ),
                Room(
                    name='Phòng Family 3',
                    description='Phòng gia đình rộng rãi, có khu vực vui chơi nhỏ, phù hợp cho gia đình có trẻ em.',
                    price_per_hour=120000,
                    capacity=6,
                    amenities=json.dumps(['WiFi', 'Điều hòa', 'TV 55 inch', 'Bàn ăn', 'Ghế sofa', 'Khu vực vui chơi', 'Tủ lạnh']),
                    available=True
                ),
                Room(
                    name='Phòng Working 4',
                    description='Phòng làm việc chuyên nghiệp với thiết kế hiện đại, yên tĩnh, phù hợp cho làm việc nhóm.',
                    price_per_hour=100000,
                    capacity=3,
                    amenities=json.dumps(['WiFi', 'Điều hòa', 'Máy chiếu', 'Bàn họp', 'Ghế làm việc', 'Bảng trắng']),
                    available=True
                ),
                Room(
                    name='Phòng Relax 5',
                    description='Phòng thư giãn với không gian yên tĩnh, có thể nghe nhạc, đọc sách, thư giãn.',
                    price_per_hour=60000,
                    capacity=2,
                    amenities=json.dumps(['WiFi', 'Điều hòa', 'Loa nhạc', 'Ghế thư giãn', 'Sách', 'Trà']),
                    available=True
                )
            ]

            for room in rooms:
                db.session.add(room)
            db.session.commit()

        # One-time migration: re-hash any legacy plaintext passwords, and make
        # sure the founding 'admin' account is always super_admin (it may
        # have been created before the role column existed).
        legacy_dirty = False
        if admin.password.count('$') != 2:
            admin.password = generate_password_hash(admin.password)
            legacy_dirty = True
        if admin.role != 'super_admin':
            admin.role = 'super_admin'
            legacy_dirty = True
        for customer in Customer.query.all():
            if customer.password and customer.password.count('$') != 2:
                customer.password = generate_password_hash(customer.password)
                legacy_dirty = True
        if legacy_dirty:
            db.session.commit()
    except Exception as e:
        logger.exception("Error during database initialization")
