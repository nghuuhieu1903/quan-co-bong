"""SQLAlchemy models and the notification helper."""

import logging

import json
from datetime import datetime

from flask import url_for

from extensions import db
from helpers import safe_print as print

logger = logging.getLogger(__name__)


class Product(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), nullable=False)
    description = db.Column(db.Text, nullable=False)
    price = db.Column(db.Float, nullable=False)
    stock = db.Column(db.Integer, nullable=False)
    image = db.Column(db.String(200), default='pngtree.png')
    category = db.Column(db.String(50), nullable=False)
    item_type = db.Column(db.String(20), nullable=False, default='drink')  # 'drink' or 'food'
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    images = db.relationship('ProductImage', backref='product', lazy=True, cascade="all, delete-orphan")

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
    
    @property
    def image_url(self):
        """Get the full URL for the product image"""
        if self.image and self.image not in ('pngtree.png', 'default_placeholder.png'):
            return url_for('static', filename=f'images/{self.image}')
        return url_for('static', filename='images/default_placeholder.png')

class ProductImage(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    product_id = db.Column(db.Integer, db.ForeignKey('product.id'), nullable=False)
    image = db.Column(db.String(200), nullable=False)

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
    
    @property
    def image_url(self):
        """Get the full URL for this product image"""
        return url_for('static', filename=f'images/{self.image}')

class Order(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    customer_name = db.Column(db.String(100), nullable=False)
    customer_phone = db.Column(db.String(20), nullable=False)
    total_amount = db.Column(db.Float, nullable=False)
    status = db.Column(db.String(20), default='pending')
    payment_method = db.Column(db.String(20), default='cash')
    notes = db.Column(db.Text, nullable=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    items = db.relationship('OrderItem', backref='order', lazy=True)

    def __init__(self, **kwargs):
        super().__init__(**kwargs)

class OrderItem(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    order_id = db.Column(db.Integer, db.ForeignKey('order.id'), nullable=False)
    product_id = db.Column(db.Integer, db.ForeignKey('product.id'), nullable=False)
    quantity = db.Column(db.Integer, nullable=False)
    price = db.Column(db.Float, nullable=False)
    product = db.relationship('Product', backref='order_items')

    def __init__(self, **kwargs):
        super().__init__(**kwargs)

class Admin(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(50), unique=True, nullable=False)
    password = db.Column(db.String(255), nullable=False)
    role = db.Column(db.String(20), default='admin', nullable=False)  # 'super_admin' or 'admin'
    reset_code_hash = db.Column(db.String(255))
    reset_code_expiry = db.Column(db.DateTime)
    reset_code_attempts = db.Column(db.Integer, nullable=False, default=0)

    def __init__(self, **kwargs):
        super().__init__(**kwargs)

class Customer(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(50), unique=True, nullable=False)
    password = db.Column(db.String(255), nullable=False)
    full_name = db.Column(db.String(100), nullable=False)
    phone = db.Column(db.String(20), nullable=False)
    role = db.Column(db.String(20), default='customer', nullable=False)  # 'customer' or 'manager'
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    def __init__(self, **kwargs):
        super().__init__(**kwargs)

class Notification(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    type = db.Column(db.String(50), nullable=False)
    message = db.Column(db.Text, nullable=False)
    is_read = db.Column(db.Boolean, default=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    def __init__(self, **kwargs):
        super().__init__(**kwargs)

class Room(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), nullable=False)
    description = db.Column(db.Text, nullable=False)
    price_per_hour = db.Column(db.Float, nullable=False)
    price_unit = db.Column(db.String(50), default='giờ')
    capacity = db.Column(db.Integer, nullable=False)
    image = db.Column(db.String(200), default='pngtree.png')
    amenities = db.Column(db.Text)  # JSON string of amenities
    available = db.Column(db.Boolean, default=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    electricity_cost = db.Column(db.String(100), default='3.6k/kWh')
    water_cost = db.Column(db.String(100), default='100.000 VNĐ/người')
    service_cost = db.Column(db.String(100), default='100.000 VNĐ/người')
    basic_costs = db.Column(db.Text)

    images = db.relationship('RoomImage', backref='room', lazy=True, cascade="all, delete-orphan")

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
    
    @property
    def image_url(self):
        """Get the full URL for the room image"""
        if self.image and self.image not in ('pngtree.png', 'default_placeholder.png'):
            return url_for('static', filename=f'images/{self.image}')
        return url_for('static', filename='images/default_placeholder.png')
    
    @property
    def amenities_list(self):
        """Get amenities as list"""
        if self.amenities:
            try:
                return json.loads(self.amenities)
            except ValueError:
                logger.warning('Room %s has unreadable amenities JSON', self.id)
        return []

    @property
    def basic_costs_list(self):
        """Get basic costs as list of dicts"""
        if self.basic_costs:
            try:
                return json.loads(self.basic_costs)
            except ValueError:
                logger.warning('Room %s has unreadable basic_costs JSON', self.id)
        return []

class RoomImage(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    room_id = db.Column(db.Integer, db.ForeignKey('room.id'), nullable=False)
    image = db.Column(db.String(200), nullable=False)

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
    
    @property
    def image_url(self):
        """Get the full URL for this room image"""
        return url_for('static', filename=f'images/{self.image}')

class RoomBooking(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    room_id = db.Column(db.Integer, db.ForeignKey('room.id'), nullable=False)
    customer_name = db.Column(db.String(100), nullable=False)
    customer_phone = db.Column(db.String(20), nullable=False)
    booking_date = db.Column(db.Date, nullable=False)
    start_time = db.Column(db.Time, nullable=False)
    end_time = db.Column(db.Time, nullable=False)
    total_hours = db.Column(db.Float, nullable=False)
    total_price = db.Column(db.Float, nullable=False)
    status = db.Column(db.String(20), default='pending')  # pending, confirmed, cancelled
    notes = db.Column(db.Text)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    
    room = db.relationship('Room', backref='bookings')

    def __init__(self, **kwargs):
        super().__init__(**kwargs)

class DailyMenuItem(db.Model):
    """A dish a manager posts as available today. Ordered directly (like a room),
    not through the shopping cart."""
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(150), nullable=False)
    description = db.Column(db.Text)
    price = db.Column(db.Float, nullable=False)
    image = db.Column(db.String(200), default='pngtree.png')
    available = db.Column(db.Boolean, default=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    created_by_id = db.Column(db.Integer, db.ForeignKey('customer.id'))

    created_by = db.relationship('Customer')

    def __init__(self, **kwargs):
        super().__init__(**kwargs)

    @property
    def image_url(self):
        if self.image and self.image not in ('pngtree.png', 'default_placeholder.png'):
            return url_for('static', filename=f'images/{self.image}')
        return url_for('static', filename='images/default_placeholder.png')

class DailyMenuOrder(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    item_id = db.Column(db.Integer, db.ForeignKey('daily_menu_item.id'), nullable=False)
    customer_name = db.Column(db.String(100), nullable=False)
    customer_phone = db.Column(db.String(20), nullable=False)
    quantity = db.Column(db.Integer, default=1)
    notes = db.Column(db.Text)
    status = db.Column(db.String(20), default='pending')  # pending, completed, cancelled
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    item = db.relationship('DailyMenuItem', backref='orders')

    def __init__(self, **kwargs):
        super().__init__(**kwargs)

def create_notification(notification_type, message):
    try:
        notification = Notification(type=notification_type, message=message)
        db.session.add(notification)
        db.session.commit()
        return notification
    except Exception as e:
        try:
            db.session.rollback()
        except Exception:
            pass
        logger.exception("Error creating notification")
        return None

