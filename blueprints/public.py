"""Storefront: home, catalogue, room listings, cart and checkout."""

import logging

import base64
import io
import json
import os
import re
import secrets
import time
from datetime import datetime, timedelta

import openpyxl
import qrcode
from flask import (Blueprint, current_app, flash, jsonify, redirect,
                   render_template, request, send_file, session, url_for)
from openpyxl.styles import Alignment, Border, Font, PatternFill, Side
from sqlalchemy import func, text
from werkzeug.security import check_password_hash, generate_password_hash

from automation import automation_controller, gTTS, laptop_speaker, pyautogui, pyttsx3
from decorators import (admin_required, admin_required_api,
                        admin_required_api_success, manager_required,
                        super_admin_required)
from extensions import db
from helpers import (SUPER_ADMIN_RECOVERY_EMAIL, safe_print as print,
                     save_uploaded_file, save_uploaded_files, send_email)
from models import (Admin, Customer, DailyMenuItem, DailyMenuOrder,
                    Notification, Order, OrderItem, Product, ProductImage,
                    Room, RoomBooking, RoomImage, create_notification)

logger = logging.getLogger(__name__)

bp = Blueprint('public', __name__)


@bp.route('/change_lang/<lang>')
def change_lang(lang):
    if lang in ('vi', 'en'):
        session['lang'] = lang
    return redirect(request.referrer or url_for('public.index'))


@bp.route('/')
def index():
    return redirect(url_for('public.customer_home'))

@bp.route('/customer')
def customer_home():
    products = Product.query.all()  # Hiển thị tất cả sản phẩm kể cả hết hàng
    daily_items = DailyMenuItem.query.filter_by(available=True).order_by(DailyMenuItem.created_at.desc()).all()
    return render_template('index.html', products=products, daily_items=daily_items)

@bp.route('/products')
def products():
    # Get filter parameters
    search_query = request.args.get('search', '').strip()
    category_filter = request.args.get('category', '').strip()
    item_type = request.args.get('type', 'drink').strip()
    if item_type not in ('drink', 'food'):
        item_type = 'drink'

    # Start with base query, scoped to the requested item type
    query = Product.query.filter(Product.item_type == item_type)

    # Apply search filter
    if search_query:
        query = query.filter(Product.name.contains(search_query))

    # Apply category filter
    if category_filter:
        query = query.filter(Product.category == category_filter)

    # Get filtered products
    products = query.all()

    # Get all unique categories from database (within this item type)
    categories = db.session.query(Product.category).filter(Product.item_type == item_type).distinct().all()
    categories = [cat[0] for cat in categories if cat[0]]  # Remove None values

    # Get total products count (within this item type)
    total_products = Product.query.filter(Product.item_type == item_type).count()

    return render_template('products.html', products=products, categories=categories, total_products=total_products, item_type=item_type)

@bp.route('/rooms')
def rooms():
    rooms = Room.query.filter_by(available=True).all()
    return render_template('rooms.html', rooms=rooms)

@bp.route('/room/<int:room_id>')
def room_detail(room_id):
    room = Room.query.get_or_404(room_id)
    return render_template('room_detail.html', room=room)

@bp.route('/book_room/<int:room_id>', methods=['POST'])
def book_room(room_id):
    room = Room.query.get_or_404(room_id)
    
    if not room.available:
        flash('Phòng này hiện không còn trống!', 'error')
        return redirect(url_for('public.room_detail', room_id=room_id))
    
    # Get form data
    customer_name = request.form.get('customer_name')
    customer_phone = request.form.get('customer_phone')
    booking_date_str = request.form.get('booking_date')
    start_time_str = request.form.get('start_time')
    notes = request.form.get('notes')
    
    # Validate required fields
    if not all([customer_name, customer_phone, booking_date_str, start_time_str]):
        flash('Vui lòng điền đầy đủ thông tin bắt buộc!', 'error')
        return redirect(url_for('public.room_detail', room_id=room_id))
    
    try:
        # Parse date and time
        from datetime import datetime, date, time, timedelta
        booking_date = datetime.strptime(booking_date_str, '%Y-%m-%d').date()
        try:
            start_time = datetime.strptime(start_time_str, '%H:%M:%S').time()
        except ValueError:
            start_time = datetime.strptime(start_time_str, '%H:%M').time()
        # Fixed 1 hour booking duration
        start_datetime = datetime.combine(booking_date, start_time)
        end_datetime = start_datetime + timedelta(hours=1)
        end_time = end_datetime.time()
        
        # Fixed 1 hour booking
        total_hours = 1.0
        total_price = total_hours * room.price_per_hour

        # Reject overlapping bookings for the same room/date
        existing_bookings = RoomBooking.query.filter(
            RoomBooking.room_id == room.id,
            RoomBooking.booking_date == booking_date,
            RoomBooking.status != 'cancelled'
        ).all()
        for existing in existing_bookings:
            if existing.start_time < end_time and existing.end_time > start_time:
                flash('Khung giờ này đã có người đặt. Vui lòng chọn thời gian khác!', 'error')
                return redirect(url_for('public.room_detail', room_id=room_id))

        # Create booking
        booking = RoomBooking(
            room_id=room.id,
            customer_name=customer_name,
            customer_phone=customer_phone,
            booking_date=booking_date,
            start_time=start_time,
            end_time=end_time,
            total_hours=total_hours,
            total_price=total_price,
            notes=notes
        )
        
        db.session.add(booking)
        
        # Define end_time_str for notification
        end_time_str = end_time.strftime('%H:%M')
        # Create notification for admin
        notification_message = f"🏠 ĐẶT PHÒNG MỚI!\nKhách hàng: {customer_name}\nSĐT: {customer_phone}\nPhòng: {room.name}\nNgày: {booking_date_str}\nThời gian: {start_time_str} - {end_time_str}\nTổng: {total_price:,.0f} VNĐ"
        create_notification('room_booking', notification_message)
        
        db.session.commit()
        
        flash('Đặt phòng thành công! Chúng tôi sẽ liên hệ với bạn sớm.', 'success')
        # Redirect based on user role
        if 'admin_logged_in' in session:
            return redirect(url_for('admin.admin_room_bookings'))
        else:
            return redirect(url_for('public.rooms'))
        
    except Exception as e:
        db.session.rollback()
        logger.exception("Booking error")
        flash('Có lỗi xảy ra khi đặt phòng. Vui lòng thử lại!', 'error')
        return redirect(url_for('public.room_detail', room_id=room_id))

@bp.route('/product/<int:product_id>')
def product_detail_route(product_id):
    product = Product.query.get_or_404(product_id)
    return render_template('product_detail.html', product=product)

@bp.route('/cart')
def cart():
    cart_items = session.get('cart', [])
    products = []
    total = 0

    
    for item in cart_items:
        product = Product.query.get(item['product_id'])
        if product:
            products.append({
                'product': product,
                'quantity': item['quantity'],
                'subtotal': product.price * item['quantity']
            })
            total += product.price * item['quantity']
    
    final_total = total
    
    return render_template('cart.html', cart_items=products, products=products, subtotal=total, total=final_total)

@bp.route('/add_to_cart/<int:product_id>', methods=['POST'])
def add_to_cart(product_id):
    product = Product.query.get_or_404(product_id)
    next_url = request.form.get('next') or request.referrer
    
    if product.stock <= 0:
        flash('Sản phẩm đã hết hàng', 'error')
        return redirect(next_url or url_for('public.customer_home'))
    
    # Get quantity from form, default to 1 if not provided
    quantity = int(request.form.get('quantity', 1))
    
    # Validate quantity
    if quantity < 1 or quantity > product.stock:
        flash('Số lượng không hợp lệ', 'error')
        return redirect(next_url or url_for('public.customer_home'))
    
    cart = session.get('cart', [])
    
    # Check if product already in cart
    for item in cart:
        if item['product_id'] == product_id:
            # Update quantity, but don't exceed stock
            new_quantity = item['quantity'] + quantity
            if new_quantity <= product.stock:
                item['quantity'] = new_quantity
            else:
                item['quantity'] = product.stock
                flash(f'Số lượng đã cập nhật tối đa ({product.stock})', 'warning')
            break
    else:
        cart.append({'product_id': product_id, 'quantity': quantity})
    
    session['cart'] = cart
    flash(f'{quantity} {"sản phẩm" if quantity == 1 else "sản phẩm"} đã thêm vào giỏ hàng', 'success')
    return redirect(next_url or url_for('public.customer_home'))

@bp.route('/update_cart/<int:product_id>', methods=['POST'])
def update_cart(product_id):
    cart = session.get('cart', [])
    action = request.form.get('action')
    try:
        quantity = int(request.form.get('quantity', 1))
    except ValueError:
        quantity = 1

    product = Product.query.get(product_id)
    max_stock = product.stock if product else quantity

    # Find the item in cart
    for item in cart:
        if item['product_id'] == product_id:
            if action == 'increase':
                item['quantity'] += 1
            elif action == 'decrease' and item['quantity'] > 1:
                item['quantity'] -= 1
            else:
                item['quantity'] = quantity
            # Clamp to a valid range
            item['quantity'] = max(1, min(item['quantity'], max_stock)) if max_stock > 0 else 1
            break

    session['cart'] = cart
    return redirect(url_for('public.cart'))

@bp.route('/remove_from_cart/<int:product_id>', methods=['POST', 'GET'])
def remove_from_cart(product_id):
    cart = session.get('cart', [])
    cart = [item for item in cart if item['product_id'] != product_id]
    session['cart'] = cart
    return redirect(url_for('public.cart'))

@bp.route('/checkout', methods=['GET', 'POST'])
def checkout():
    cart_items = session.get('cart', [])
    if not cart_items:
        flash('Giỏ hàng của bạn đang trống', 'error')
        return redirect(url_for('public.customer_home'))
    
    # Handle POST from cart form
    if request.method == 'POST':
        # Get customer info from cart form
        customer_name = request.form.get('name', '').strip()
        customer_phone = request.form.get('phone', '').strip()
        
        # Store in session for checkout page
        session['customer_name'] = customer_name if customer_name else "Guest Customer"
        session['customer_phone'] = customer_phone if customer_phone else "Not provided"
        
        # Redirect to checkout page
        products = []
        total = 0
        
        for item in cart_items:
            product = Product.query.get(item['product_id'])
            if product:
                products.append({
                    'product': product,
                    'quantity': item['quantity'],
                    'subtotal': product.price * item['quantity']
                })
                total += product.price * item['quantity']
        
        final_total = total 
        return render_template('checkout.html', cart_items=products, subtotal=total, total=final_total)
    
    # Original GET logic
    products = []
    total = 0

    
    for item in cart_items:
        product = Product.query.get(item['product_id'])
        if product:
            products.append({
                'product': product,
                'quantity': item['quantity'],
                'subtotal': product.price * item['quantity']
            })
            total += product.price * item['quantity']
    
    final_total = total 
    return render_template('checkout.html', cart_items=products, subtotal=total,  total=final_total)

@bp.route('/process_order', methods=['POST'])
def process_order():
    cart_items = session.get('cart', [])
    if not cart_items:
        flash('Giỏ hàng của bạn đang trống', 'error')
        return redirect(url_for('public.customer_home'))
    
    # Get form data
    customer_name = request.form.get('name', '').strip() or "Guest Customer"
    customer_phone = request.form.get('phone', '').strip() or "Not provided"
    payment_method = request.form.get('payment_method', 'cash')
    notes = request.form.get('notes', '').strip()

    phone_digits = re.sub(r"\D", "", customer_phone or "")
    if phone_digits:
        if len(phone_digits) < 9 or len(phone_digits) > 11:
            flash('Số điện thoại không hợp lệ (chỉ gồm 9-11 chữ số).', 'error')
            return redirect(url_for('public.checkout'))
        customer_phone = phone_digits

    # Verify stock is still available for every item before committing anything
    total = 0
    for item in cart_items:
        product = Product.query.get(item['product_id'])
        if not product:
            continue
        if item['quantity'] > product.stock:
            flash(f'Sản phẩm "{product.name}" không đủ hàng (còn {product.stock}). Vui lòng cập nhật giỏ hàng.', 'error')
            return redirect(url_for('public.cart'))
        total += product.price * item['quantity']

    final_total = total
    
    # Create order
    order = Order(
        customer_name=customer_name,
        customer_phone=customer_phone,
        total_amount=final_total,
        status='pending',
        payment_method=payment_method,
        notes=notes
    )
    db.session.add(order)
    db.session.flush()  # Get order ID
    
    # Add order items
    for item in cart_items:
        product = Product.query.get(item['product_id'])
        if product:
            order_item = OrderItem(
                order_id=order.id,
                product_id=product.id,
                quantity=item['quantity'],
                price=product.price
            )
            db.session.add(order_item)
            
            # Update stock
            product.stock -= item['quantity']
    
    db.session.commit()
    
    # Announce new order
    try:
        items_data = [{'product_id': item['product_id'], 'quantity': item['quantity']} for item in cart_items]
        laptop_speaker.announce_order(items_data, customer_name, notes=notes)
    except Exception as e:
        logger.exception("Error playing sound")
        
    # Clear cart
    session['cart'] = []

    create_notification('new_order', f"Đơn hàng mới #{order.id} - {customer_name} - {final_total:,.0f} VNĐ")
    
    # Create notification log
    try:
        log_entry = f"""
=====================================
🔔 ĐƠN HÀNG MỚI - {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}
=====================================
Mã đơn: #{order.id}
Khách hàng: {customer_name}
Số điện thoại: {customer_phone}
Phương thức thanh toán: {payment_method}
Tổng tiền: {final_total:,.0f} VNĐ
Sản phẩm: {len(cart_items)} loại
Ghi chú: {notes}
Trạng thái: {order.status}
=====================================
VUI LÒNG KIỂM TRA HỆ THỐNG ĐỂ XỬ LÝ ĐƠN HÀNG!
=====================================

"""
        
        with open('notification_log.txt', 'a', encoding='utf-8') as f:
            f.write(log_entry)
        
        print("✅ Notification log created: notification_log.txt")
        
    except Exception as e:
        logger.exception("Error creating notification log")
    
    flash('Đặt hàng thành công! Cảm ơn bạn đã mua hàng tại Coffee Vibes.', 'success')
    return redirect(url_for('public.order_confirmation', order_id=order.id))

@bp.route('/order_confirmation/<int:order_id>')
def order_confirmation(order_id):
    order = Order.query.get_or_404(order_id)
    # Get order items for display
    order_items = OrderItem.query.filter_by(order_id=order.id).all()
    
    # Calculate subtotal and total
    subtotal = order.total_amount  # Since we removed shipping fee, total_amount = subtotal
    total = order.total_amount
    
    return render_template('order_confirmation.html', order=order, order_items=order_items, subtotal=subtotal, total=total)
