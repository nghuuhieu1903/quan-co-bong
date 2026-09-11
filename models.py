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
    # A dish the shop is serving today. These sort to the top of the food tab;
    # snacks and everything else follow.
    is_daily = db.Column(db.Boolean, nullable=False, default=False)
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
    # Optional: "remind me around this time" for a daily-dish order, set by
    # the customer at checkout. Not a delivery promise - it drives a staff
    # reminder, not a guarantee to the customer.
    reminder_at = db.Column(db.DateTime, nullable=True)
    reminder_notified = db.Column(db.Boolean, nullable=False, default=False)
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
    # serviced apartments here are let by the month; hourly is the exception
    price_unit = db.Column(db.String(50), default='tháng')
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

class SiteSetting(db.Model):
    """Editable site text, as key/value rows.

    A key/value table rather than a column per field: the SEO page grows a
    new setting now and then, and each one would otherwise need a migration.
    Nothing here is required - seo.py falls back to the built-in defaults for
    any key that has never been saved, so an empty table behaves exactly like
    the hard-coded version did.
    """
    key = db.Column(db.String(64), primary_key=True)
    value = db.Column(db.Text)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow,
                           onupdate=datetime.utcnow)

    def __init__(self, **kwargs):
        super().__init__(**kwargs)


class MediaFile(db.Model):
    """An uploaded image, stored in the database rather than on disk.

    The obvious place for these is static/, but that directory is created by
    git and therefore owned by whoever deploys, while the app runs as someone
    else - so uploading failed with "permission denied" and the only fix was a
    shell command. The database is the one place the app is guaranteed to be
    able to write, it needs no server-side setup, a `git pull` cannot
    overwrite what is in it, and a database backup now includes the shop's
    logo. Rows are a few hundred KB at most.
    """
    key = db.Column(db.String(64), primary_key=True)
    content_type = db.Column(db.String(64), nullable=False, default='image/png')
    # MEDIUMBLOB: a plain BLOB caps at 64KB, which a 512px icon can exceed
    data = db.Column(db.LargeBinary(length=16_777_215), nullable=False)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow,
                           onupdate=datetime.utcnow)

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

