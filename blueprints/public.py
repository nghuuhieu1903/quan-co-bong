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
from flask import (Blueprint, abort, current_app, flash, jsonify, redirect,
                   render_template, request, send_file, session, url_for)
from openpyxl.styles import Alignment, Border, Font, PatternFill, Side
from sqlalchemy import func, text
from werkzeug.security import check_password_hash, generate_password_hash

from decorators import (admin_required, admin_required_api,
                        admin_required_api_success, manager_required,
                        super_admin_required)
from extensions import db
from helpers import (SUPER_ADMIN_RECOVERY_EMAIL, parse_vnd, safe_print as print,
                     save_uploaded_file, save_uploaded_files, send_email)
import payments
from models import (Admin, Customer, Notification, Order, OrderItem,
                    Product, ProductImage,
                    Room, RoomImage, create_notification)

logger = logging.getLogger(__name__)

bp = Blueprint('public', __name__)


def prefill_contact():
    """Name/phone to pre-fill the order form with, so a returning customer
    never has to retype what the shop already has.

    A logged-in customer's own saved profile wins - it is the one place the
    name/phone can actually be kept up to date (edited once, used on every
    order after). A guest with no account falls back to whatever they typed
    on their last order this session, same as before this existed.
    """
    if session.get('customer_logged_in') and session.get('customer_id'):
        customer = db.session.get(Customer, session['customer_id'])
        if customer:
            return customer.full_name, customer.phone
    name = session.get('customer_name') or ''
    phone = session.get('customer_phone') or ''
    if phone == 'Not provided':
        phone = ''
    return name, phone


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
    # Hiển thị tất cả sản phẩm kể cả hết hàng, trừ sản phẩm đã ẩn/ngừng bán
    products = Product.query.filter(Product.is_active.is_(True)).all()
    return render_template('index.html', products=products)

@bp.route('/products')
def products():
    # Get filter parameters
    search_query = request.args.get('search', '').strip()
    category_filter = request.args.get('category', '').strip()
    item_type = request.args.get('type', 'drink').strip()
    if item_type not in ('drink', 'food'):
        item_type = 'drink'

    # "Đồ ăn" used to be one tab mixing daily lunch dishes with snacks - now
    # split into two ordering tabs, keyed off the same is_daily flag the
    # admin already sets per product. Only meaningful for food; a leftover
    # ?food_kind= on a drink link is simply ignored.
    food_kind = request.args.get('food_kind', '').strip()
    if item_type == 'food' and food_kind not in ('daily', 'snack'):
        food_kind = 'daily'   # old links to ?type=food land on Cơm trưa

    # Start with base query, scoped to the requested item type. A hidden
    # (is_active=False) product stays fully intact for its past orders but
    # drops off the customer-facing catalogue.
    query = Product.query.filter(Product.item_type == item_type,
                                 Product.is_active.is_(True))
    if item_type == 'food':
        query = query.filter(Product.is_daily.is_(food_kind == 'daily'))

    # Apply search filter
    if search_query:
        query = query.filter(Product.name.contains(search_query))

    # Apply category filter
    if category_filter:
        query = query.filter(Product.category == category_filter)

    # Price bracket, sent as "low-high" with either end allowed to be blank
    price_range = request.args.get('price_range', '').strip()
    if price_range and '-' in price_range:
        low, _, high = price_range.partition('-')
        try:
            if low:
                query = query.filter(Product.price >= float(low))
            if high:
                # exclusive, so a 50.000 item lands in "50.000 - 100.000"
                # only, not in both brackets
                query = query.filter(Product.price < float(high))
        except ValueError:
            pass          # a hand-edited URL sorts itself out as "no filter"

    # Sort. The chips above the grid and the drawer's select post the same
    # four values; anything else falls back to the catalogue's own order.
    sort = request.args.get('sort', '').strip()
    if sort == 'price_low':
        query = query.order_by(Product.price.asc())
    elif sort == 'price_high':
        query = query.order_by(Product.price.desc())
    elif sort == 'name':
        query = query.order_by(Product.name.asc())
    elif sort == 'name_desc':
        query = query.order_by(Product.name.desc())
    elif sort == 'best_selling':
        # how many of each item have actually been sold. Cancelled orders do
        # not count, and an item nobody has ordered yet sums to 0 rather than
        # dropping out of the list.
        sold = (db.session.query(OrderItem.product_id.label('pid'),
                                 func.sum(OrderItem.quantity).label('qty'))
                .join(Order, Order.id == OrderItem.order_id)
                .filter(Order.status != 'cancelled')
                .group_by(OrderItem.product_id)
                .subquery())
        query = (query.outerjoin(sold, sold.c.pid == Product.id)
                      .order_by(func.coalesce(sold.c.qty, 0).desc(),
                                Product.name.asc()))
    elif sort == 'newest':
        query = query.order_by(Product.created_at.desc(), Product.id.desc())
    else:
        # No sort chosen: today's dishes lead, snacks and the rest follow.
        query = query.order_by(Product.is_daily.desc(), Product.id.asc())

    # Get filtered products
    products = query.all()

    # Get all unique categories from database (within this item type + food_kind)
    category_query = db.session.query(Product.category).filter(Product.item_type == item_type)
    if item_type == 'food':
        category_query = category_query.filter(Product.is_daily.is_(food_kind == 'daily'))
    categories = category_query.distinct().all()
    categories = [cat[0] for cat in categories if cat[0]]  # Remove None values

    # Get total products count (within this item type + food_kind)
    total_query = Product.query.filter(Product.item_type == item_type,
                                       Product.is_active.is_(True))
    if item_type == 'food':
        total_query = total_query.filter(Product.is_daily.is_(food_kind == 'daily'))
    total_products = total_query.count()

    return render_template('products.html', products=products, categories=categories,
                           total_products=total_products, item_type=item_type, food_kind=food_kind)

@bp.route('/rooms')
def rooms():
    rooms = Room.query.filter_by(available=True).all()
    return render_template('rooms.html', rooms=rooms)

@bp.route('/room/<int:room_id>')
def room_detail(room_id):
    room = Room.query.get_or_404(room_id)
    return render_template('room_detail.html', room=room)


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

    has_daily_item = any(p['product'].is_daily for p in products)
    prefill_name, prefill_phone = prefill_contact()
    return render_template('cart.html', cart_items=products, products=products, subtotal=total,
                           total=final_total, has_daily_item=has_daily_item,
                           prefill_name=prefill_name, prefill_phone=prefill_phone,
                           customer_logged_in=bool(session.get('customer_logged_in')))

def wants_json():
    """True when the caller asked for JSON rather than a redirect.

    The cart forms still work with JavaScript off - they post and the browser
    follows the redirect as before. The script sets this header instead, so
    the same view serves both without a second endpoint to keep in step.
    """
    return request.headers.get('X-Requested-With') == 'fetch'


def cart_count():
    return len(session.get('cart', []))


@bp.route('/add_to_cart/<int:product_id>', methods=['POST'])
def add_to_cart(product_id):
    product = Product.query.get_or_404(product_id)
    next_url = request.form.get('next') or request.referrer

    if not product.is_active:
        if wants_json():
            return jsonify(ok=False, message='Sản phẩm đã ngừng bán',
                           count=cart_count()), 409
        flash('Sản phẩm đã ngừng bán', 'error')
        return redirect(next_url or url_for('public.customer_home'))

    if product.stock <= 0:
        if wants_json():
            return jsonify(ok=False, message='Sản phẩm đã hết hàng',
                           count=cart_count()), 409
        flash('Sản phẩm đã hết hàng', 'error')
        return redirect(next_url or url_for('public.customer_home'))
    
    # Get quantity from form, default to 1 if not provided
    quantity = int(request.form.get('quantity', 1))
    
    # Validate quantity
    if quantity < 1 or quantity > product.stock:
        if wants_json():
            return jsonify(ok=False,
                           message=f'Chỉ còn {product.stock} sản phẩm',
                           count=cart_count()), 409
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
    message = f'Đã thêm {quantity} {product.name} vào giỏ'
    if wants_json():
        return jsonify(ok=True, message=message, count=cart_count())
    flash(message, 'success')
    return redirect(next_url or url_for('public.customer_home'))

def cart_state():
    """Everything the cart page needs to redraw itself after a change."""
    items, total = [], 0
    for entry in session.get('cart', []):
        product = db.session.get(Product, entry['product_id'])
        if not product:
            continue
        line = product.price * entry['quantity']
        total += line
        items.append({
            'product_id': product.id,
            'quantity': entry['quantity'],
            'stock': product.stock,
            'line_total': line,
        })
    return {'items': items, 'total': total, 'count': len(items)}


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
    if wants_json():
        return jsonify(ok=True, **cart_state())
    return redirect(url_for('public.cart'))

@bp.route('/remove_from_cart/<int:product_id>', methods=['POST', 'GET'])
def remove_from_cart(product_id):
    cart = session.get('cart', [])
    cart = [item for item in cart if item['product_id'] != product_id]
    session['cart'] = cart
    if wants_json():
        return jsonify(ok=True, **cart_state())
    return redirect(url_for('public.cart'))

@bp.route('/remove_selected_from_cart', methods=['POST'])
def remove_selected_from_cart():
    """Drop several items in one go, from the cart's tick boxes."""
    wanted = set()
    for raw in request.form.getlist('product_ids'):
        try:
            wanted.add(int(raw))
        except (TypeError, ValueError):
            continue

    cart = [item for item in session.get('cart', [])
            if item['product_id'] not in wanted]
    session['cart'] = cart

    if wants_json():
        return jsonify(ok=True, **cart_state())
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
        
        # Store in session for checkout page. Leaving the name blank here used
        # to pre-fill the checkout form's name box with the placeholder text
        # "Guest Customer" - which reads as a real name, passes a "did they
        # type something" check, and tells the shop nothing about who the
        # order is for. Store nothing rather than a fake name.
        if customer_name:
            session['customer_name'] = customer_name
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
        has_daily_item = any(p['product'].is_daily for p in products)
        prefill_name, prefill_phone = prefill_contact()
        return render_template('checkout.html', cart_items=products, subtotal=total, total=final_total,
                               bank_enabled=payments.is_configured(), has_daily_item=has_daily_item,
                               prefill_name=prefill_name, prefill_phone=prefill_phone,
                               customer_logged_in=bool(session.get('customer_logged_in')))

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
    has_daily_item = any(p['product'].is_daily for p in products)
    prefill_name, prefill_phone = prefill_contact()
    return render_template('checkout.html', cart_items=products, subtotal=total,
                           total=final_total, bank_enabled=payments.is_configured(),
                           has_daily_item=has_daily_item,
                           prefill_name=prefill_name, prefill_phone=prefill_phone,
                           customer_logged_in=bool(session.get('customer_logged_in')))

@bp.route('/process_order', methods=['POST'])
def process_order():
    cart_items = session.get('cart', [])
    if not cart_items:
        flash('Giỏ hàng của bạn đang trống', 'error')
        return redirect(url_for('public.customer_home'))
    
    # Get form data
    customer_name = request.form.get('name', '').strip()
    if not customer_name:
        # No delivery here, so a name is the only way to know who a
        # ready order belongs to - the shop needs it, not just wants it.
        flash('Vui lòng nhập tên để chúng tôi biết giao món cho ai.', 'error')
        return redirect(url_for('public.checkout'))
    customer_phone = request.form.get('phone', '').strip() or "Not provided"
    # Customers pay by transfer: the confirmation page shows a QR with the
    # amount and reference filled in. Cash is still a thing at the counter,
    # which goes through the POS screen, not this route.
    payment_method = 'bank'
    notes = request.form.get('notes', '').strip()

    phone_digits = re.sub(r"\D", "", customer_phone or "")
    if phone_digits:
        if len(phone_digits) < 9 or len(phone_digits) > 11:
            flash('Số điện thoại không hợp lệ (chỉ gồm 9-11 chữ số).', 'error')
            return redirect(url_for('public.checkout'))
        customer_phone = phone_digits

    # Optional: "remind me around this time" for a daily-dish order. Blank is
    # fine - it is never required. A malformed or past value is dropped
    # rather than rejected outright, since this is a nice-to-have, not
    # something worth blocking checkout over.
    reminder_at = None
    reminder_raw = request.form.get('reminder_at', '').strip()
    if reminder_raw:
        try:
            candidate = datetime.strptime(reminder_raw, '%Y-%m-%dT%H:%M')
        except ValueError:
            candidate = None
        if candidate and candidate > datetime.now():
            reminder_at = candidate

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
        notes=notes,
        reminder_at=reminder_at
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
    
    # Clear cart
    session['cart'] = []
    # Forget who just ordered. The cart form hands the name and phone to the
    # checkout page through the session, and on a shared tablet at the counter
    # that would otherwise sit there pre-filled for whoever orders next.
    if not session.get('customer_logged_in'):
        session.pop('customer_name', None)
        session.pop('customer_phone', None)
    # Remember which orders this browser is allowed to look at. The order
    # table has no owner column and guests check out without an account, so
    # the session is what ties a confirmation page to the person who placed
    # it. Keep the list short - it only needs to cover recent orders.
    session['my_orders'] = (session.get('my_orders', []) + [order.id])[-20:]

    reminder_note = (f" - Hẹn nhận lúc {reminder_at.strftime('%H:%M %d/%m')}"
                    if reminder_at else "")
    create_notification('new_order',
        f"Đơn hàng mới #{order.id} - {customer_name} - {final_total:,.0f} VNĐ{reminder_note}")
    
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
    
    flash('Đặt hàng thành công! Cảm ơn bạn đã mua hàng tại Cô Bông Cát Lái.', 'success')
    return redirect(url_for('public.order_confirmation', order_id=order.id))

@bp.route('/order_confirmation/<int:order_id>')
def order_confirmation(order_id):
    order = Order.query.get_or_404(order_id)

    # Without this, order ids are sequential and unauthenticated, so anyone
    # could walk /order_confirmation/1,2,3... and read every customer's name
    # and phone number. Staff still need to open any order.
    if not (order_id in session.get('my_orders', [])
            or 'admin_logged_in' in session):
        abort(404)
    # Get order items for display
    order_items = OrderItem.query.filter_by(order_id=order.id).all()
    
    # Calculate subtotal and total
    subtotal = order.total_amount  # Since we removed shipping fee, total_amount = subtotal
    total = order.total_amount
    
    # Only build the transfer panel for orders that chose to pay by bank, and
    # only when an account is actually configured.
    payment = payments.payment_details(order)

    return render_template('order_confirmation.html', order=order,
                           order_items=order_items, subtotal=subtotal,
                           total=total, payment=payment,
                           order_code=payments.order_code(order.id))


# --- Manager: today's dishes ------------------------------------------------
# Manager is a Customer-account role (granted from the admin accounts page,
# not a full admin login) scoped to exactly one job: keep "Cơm trưa" current
# day to day without needing the full product editor. Only food products are
# ever touched here - drinks/snacks stay off this screen entirely.

@bp.route('/manager/daily-menu')
@manager_required
def manager_daily_menu():
    dishes = (Product.query.filter_by(item_type='food', is_active=True)
             .order_by(Product.is_daily.desc(), Product.name.asc()).all())
    return render_template('manager_daily_menu.html', dishes=dishes)

@bp.route('/manager/daily-menu/add', methods=['POST'])
@manager_required
def manager_daily_menu_add():
    name = request.form.get('name', '').strip()
    description = request.form.get('description', '').strip()
    price = parse_vnd(request.form.get('price'))
    if not name or price is None:
        flash('Vui lòng nhập tên và giá món ăn hợp lệ.', 'error')
        return redirect(url_for('public.manager_daily_menu'))

    image_file = request.files.get('image')
    if not image_file or not image_file.filename:
        flash('Vui lòng chụp hoặc chọn một ảnh cho món ăn.', 'error')
        return redirect(url_for('public.manager_daily_menu'))
    image_url = save_uploaded_file(image_file)
    if not image_url:
        flash('Ảnh không hợp lệ (chỉ nhận .jpg, .png, .webp).', 'error')
        return redirect(url_for('public.manager_daily_menu'))

    dish = Product(name=name, description=description or name, price=price,
                   stock=request.form.get('stock', type=int) or 20,
                   category='food', item_type='food', is_daily=True,
                   image=image_url)  # type: ignore[call-arg]
    db.session.add(dish)
    db.session.commit()
    flash(f'Đã đăng "{name}" vào món ăn hằng ngày.', 'success')
    return redirect(url_for('public.manager_daily_menu'))

@bp.route('/manager/daily-menu/<int:product_id>/toggle', methods=['POST'])
@manager_required
def manager_daily_menu_toggle(product_id):
    dish = Product.query.filter_by(id=product_id, item_type='food').first_or_404()
    dish.is_daily = not dish.is_daily
    db.session.commit()
    flash(f'"{dish.name}" đã {"lên" if dish.is_daily else "tắt khỏi"} món ăn hằng ngày.',
          'success')
    return redirect(url_for('public.manager_daily_menu'))
