"""Admin area: dashboard, catalogue and room management, orders, debts, QR codes, exports, automation and accounts."""

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
import payments
from extensions import db
from helpers import (SUPER_ADMIN_RECOVERY_EMAIL, safe_print as print,
                     save_uploaded_file, save_uploaded_files, send_email)
from models import (Admin, Customer, DailyMenuItem, DailyMenuOrder,
                    Notification, Order, OrderItem, Product, ProductImage,
                    Room, RoomBooking, RoomImage, create_notification)

logger = logging.getLogger(__name__)

bp = Blueprint('admin', __name__)


@bp.route('/admin/manage_products')
@admin_required
def manage_products():
    # Get search and filter parameters
    search = request.args.get('search', '')
    stock_filter = request.args.get('stock_filter', '')
    item_type_filter = request.args.get('item_type_filter', '')

    # Start with all products
    products = Product.query

    # Apply search filter
    if search:
        products = products.filter(Product.name.contains(search))

    # Apply stock filter
    if stock_filter == 'in_stock':
        products = products.filter(Product.stock > 0)
    elif stock_filter == 'out_of_stock':
        products = products.filter(Product.stock == 0)
    elif stock_filter == 'low_stock':
        products = products.filter(Product.stock > 0, Product.stock <= 10)

    # Apply item type filter (drink vs food)
    if item_type_filter in ('drink', 'food'):
        products = products.filter(Product.item_type == item_type_filter)

    # Get filtered products
    products = products.all()

    return render_template('manage_products.html', products=products)

@bp.route('/admin/daily_menu_orders')
@admin_required
def admin_daily_menu_orders():
    orders = DailyMenuOrder.query.order_by(DailyMenuOrder.created_at.desc()).all()
    return render_template('admin_daily_menu_orders.html', orders=orders)

@bp.route('/admin/daily_menu_order/<int:order_id>/update', methods=['POST'])
@admin_required
def admin_update_daily_menu_order(order_id):
    order = DailyMenuOrder.query.get_or_404(order_id)
    new_status = request.form.get('status')
    if new_status in ('pending', 'completed', 'cancelled'):
        order.status = new_status
        db.session.commit()
        flash('Đã cập nhật trạng thái đơn món ăn', 'success')
    return redirect(url_for('admin.admin_daily_menu_orders'))

@bp.route('/admin/dashboard')
@admin_required
def admin_dashboard():
    products = Product.query.all()
    orders = Order.query.order_by(Order.created_at.desc()).all()
    rooms = Room.query.all()
    room_bookings = RoomBooking.query.order_by(RoomBooking.created_at.desc()).all()
    notifications = Notification.query.order_by(Notification.created_at.desc()).limit(20).all()
    unread_notifications_count = Notification.query.filter_by(is_read=False).count()

    today = datetime.now().date()
    month_start = today.replace(day=1)

    completed_orders = [o for o in orders if o.status == 'completed']
    debt_orders = [o for o in orders if o.status not in ('completed', 'cancelled')]
    cancelled_orders = [o for o in orders if o.status == 'cancelled']
    today_completed = [o for o in completed_orders if o.created_at and o.created_at.date() == today]
    month_completed = [o for o in completed_orders if o.created_at and o.created_at.date() >= month_start]
    today_orders_count = len([o for o in orders if o.created_at and o.created_at.date() == today])

    top_products = db.session.query(
        Product.name, func.sum(OrderItem.quantity).label('total_qty')
    ).join(OrderItem, OrderItem.product_id == Product.id
    ).join(Order, Order.id == OrderItem.order_id
    ).filter(Order.status != 'cancelled'
    ).group_by(Product.id, Product.name
    ).order_by(func.sum(OrderItem.quantity).desc()
    ).limit(5).all()

    stats = {
        'total_revenue': sum(o.total_amount for o in completed_orders),
        'today_revenue': sum(o.total_amount for o in today_completed),
        'month_revenue': sum(o.total_amount for o in month_completed),
        'today_orders_count': today_orders_count,
        'completed_orders_count': len(completed_orders),
        'debt_orders_count': len(debt_orders),
        'total_debt': sum(o.total_amount for o in debt_orders),
        'cancelled_orders_count': len(cancelled_orders),
        'low_stock_count': len([p for p in products if 0 < p.stock <= 10]),
        'out_of_stock_count': len([p for p in products if p.stock == 0]),
        'available_rooms_count': len([r for r in rooms if r.available]),
        'pending_bookings_count': len([b for b in room_bookings if b.status == 'pending']),
        'top_products': top_products,
    }

    return render_template(
        'admin_dashboard.html',
        products=products,
        orders=orders,
        rooms=rooms,
        room_bookings=room_bookings,
        notifications=notifications,
        unread_notifications_count=unread_notifications_count,
        automation=automation_controller,
        laptop_speaker=laptop_speaker,
        stats=stats
    )

@bp.route('/admin/rooms')
@admin_required
def admin_rooms():
    rooms = Room.query.all()
    return render_template('admin_rooms.html', rooms=rooms)

@bp.route('/admin/room/add', methods=['GET', 'POST'])
@admin_required
def admin_add_room():
    if request.method == 'POST':
        name = request.form.get('name')
        description = request.form.get('description')
        price_per_hour = float(request.form.get('price_per_hour'))
        capacity = int(request.form.get('capacity'))
        amenities_raw = request.form.get('amenities', '')
        amenities_list = [item.strip() for item in amenities_raw.split(',') if item.strip()]
        amenities = json.dumps(amenities_list)
        available = request.form.get('available') == 'on'

        image_url = save_uploaded_file(request.files.get('image'))

        cost_names = request.form.getlist('cost_names[]')
        cost_values = request.form.getlist('cost_values[]')
        cost_icons = request.form.getlist('cost_icons[]')

        costs_list = []
        for n, v, ic in zip(cost_names, cost_values, cost_icons):
            if n.strip() and v.strip():
                costs_list.append({
                    'name': n.strip(),
                    'value': v.strip(),
                    'icon': ic.strip()
                })
        basic_costs = json.dumps(costs_list)

        price_unit = request.form.get('price_unit', 'giờ')
        room = Room(  # type: ignore
            name=name,
            description=description,
            price_per_hour=price_per_hour,
            price_unit=price_unit,
            capacity=capacity,
            amenities=amenities,
            available=available,
            image=image_url,
            basic_costs=basic_costs
        )

        db.session.add(room)
        db.session.flush()  # Get room.id

        for filename in save_uploaded_files(request.files.getlist('images')):
            db.session.add(RoomImage(room_id=room.id, image=filename))

        db.session.commit()

        flash('Phòng đã được thêm thành công!', 'success')
        return redirect(url_for('admin.admin_rooms'))
    
    return render_template('admin_add_room.html')

@bp.route('/admin/room/<int:room_id>/toggle')
@admin_required
def admin_toggle_room(room_id):
    room = Room.query.get_or_404(room_id)
    room.available = not room.available
    db.session.commit()
    
    status = "mở" if room.available else "đóng"
    flash(f'Phòng {room.name} đã được {status}!', 'success')
    return redirect(url_for('admin.admin_rooms'))

@bp.route('/admin/room/<int:room_id>/edit', methods=['GET', 'POST'])
@admin_required
def admin_edit_room(room_id):
    room = Room.query.get_or_404(room_id)
    
    if request.method == 'POST':
        room.image = save_uploaded_file(request.files.get('image')) or room.image

        for filename in save_uploaded_files(request.files.getlist('images')):
            db.session.add(RoomImage(room_id=room.id, image=filename))

        room.name = request.form.get('name')
        room.description = request.form.get('description')
        room.price_per_hour = float(request.form.get('price_per_hour'))
        room.price_unit = request.form.get('price_unit', 'giờ')
        room.capacity = int(request.form.get('capacity'))
        amenities_raw = request.form.get('amenities', '')
        amenities_list = [item.strip() for item in amenities_raw.split(',') if item.strip()]
        room.amenities = json.dumps(amenities_list)
        room.available = request.form.get('available') == 'on'
        cost_names = request.form.getlist('cost_names[]')
        cost_values = request.form.getlist('cost_values[]')
        cost_icons = request.form.getlist('cost_icons[]')

        costs_list = []
        for n, v, ic in zip(cost_names, cost_values, cost_icons):
            if n.strip() and v.strip():
                costs_list.append({
                    'name': n.strip(),
                    'value': v.strip(),
                    'icon': ic.strip()
                })
        room.basic_costs = json.dumps(costs_list)

        db.session.commit()

        flash('Phòng đã được cập nhật thành công!', 'success')
        return redirect(url_for('admin.admin_rooms'))
    
    return render_template('admin_edit_room.html', room=room)

@bp.route('/admin/room-image/<int:image_id>/delete', methods=['POST'])
@admin_required_api_success
def delete_room_image(image_id):
    img = RoomImage.query.get_or_404(image_id)
    try:
        # Delete file from disk
        image_path = os.path.join(app.root_path, 'static', 'images', img.image)
        if os.path.exists(image_path):
            os.remove(image_path)
    except Exception as e:
        logger.exception("Error deleting file from disk")
        
    db.session.delete(img)
    db.session.commit()
    return jsonify({'success': True})

@bp.route('/admin/room/<int:room_id>/delete', methods=['POST'])
@admin_required
def admin_delete_room(room_id):
    room = Room.query.get_or_404(room_id)
    db.session.delete(room)
    db.session.commit()
    
    flash('Phòng đã được xóa thành công!', 'success')
    return redirect(url_for('admin.admin_rooms'))

@bp.route('/admin/room_bookings')
@admin_required
def admin_room_bookings():
    bookings = RoomBooking.query.order_by(RoomBooking.created_at.desc()).all()
    return render_template('admin_room_bookings.html', bookings=bookings)

@bp.route('/admin/room_booking/<int:booking_id>/update', methods=['POST'])
@admin_required
def admin_update_room_booking(booking_id):
    booking = RoomBooking.query.get_or_404(booking_id)
    new_status = request.form.get('status')
    
    if new_status in ['pending', 'confirmed', 'cancelled']:
        booking.status = new_status
        db.session.commit()
        
        status_text = {
            'pending': 'Chờ xác nhận',
            'confirmed': 'Đã xác nhận', 
            'cancelled': 'Đã hủy'
        }[new_status]
        
        flash(f'Trạng thái đặt phòng đã được cập nhật: {status_text}', 'success')
    
    return redirect(url_for('admin.admin_room_bookings'))

@bp.route('/admin/product/add', methods=['GET', 'POST'])
@admin_required
def add_product():
    if request.method == 'POST':
        name = request.form.get('name')
        description = request.form.get('description')
        price = float(request.form.get('price'))
        stock = int(request.form.get('stock'))
        category = request.form.get('category')
        item_type = request.form.get('item_type', 'drink')
        if item_type not in ('drink', 'food'):
            item_type = 'drink'

        image_url = save_uploaded_file(request.files.get('image'))

        product = Product(name=name, description=description, price=price, stock=stock, category=category, item_type=item_type, image=image_url)  # type: ignore[call-arg]
        db.session.add(product)
        db.session.flush()  # Get product.id before committing

        for filename in save_uploaded_files(request.files.getlist('images')):
            db.session.add(ProductImage(product_id=product.id, image=filename))

        db.session.commit()
        flash('Sản phẩm đã thêm thành công', 'success')
        return redirect(url_for('admin.admin_dashboard'))
    
    return render_template('add_product.html')

@bp.route('/admin/product/<int:product_id>/edit', methods=['GET', 'POST'])
@admin_required
def edit_product(product_id):
    product = Product.query.get_or_404(product_id)
    
    if request.method == 'POST':
        product.image = save_uploaded_file(request.files.get('image')) or product.image

        for filename in save_uploaded_files(request.files.getlist('images')):
            db.session.add(ProductImage(product_id=product.id, image=filename))

        # Update product details
        product.name = request.form.get('name')
        product.description = request.form.get('description')
        product.price = float(request.form.get('price'))
        product.stock = int(request.form.get('stock'))
        product.category = request.form.get('category')
        item_type = request.form.get('item_type', 'drink')
        product.item_type = item_type if item_type in ('drink', 'food') else 'drink'

        db.session.commit()
        flash('Sản phẩm đã cập nhật thành công', 'success')
        return redirect(url_for('admin.manage_products'))
    
    return render_template('edit_product.html', product=product)

@bp.route('/admin/product/<int:product_id>/delete', methods=['POST'])
@admin_required
def delete_product(product_id):
    product = Product.query.get_or_404(product_id)
    
    # Delete cover image if exists
    if product.image:
        try:
            image_path = os.path.join('static', 'images', product.image)
            if os.path.exists(image_path):
                os.remove(image_path)
        except Exception as e:
            logger.exception("Error deleting cover image")
            
    # Delete all detail images from disk
    for img in product.images:
        try:
            image_path = os.path.join('static', 'images', img.image)
            if os.path.exists(image_path):
                os.remove(image_path)
        except Exception as e:
            logger.exception("Error deleting detail image")
    
    # Delete product from database
    db.session.delete(product)
    db.session.commit()
    
    flash(f'Sản phẩm "{product.name}" đã được xóa thành công!', 'success')
    return redirect(url_for('admin.manage_products'))

@bp.route('/admin/product-image/<int:image_id>/delete', methods=['POST'])
@admin_required_api_success
def delete_product_image(image_id):
    img = ProductImage.query.get_or_404(image_id)
    try:
        # Delete file from disk
        image_path = os.path.join('static', 'images', img.image)
        if os.path.exists(image_path):
            os.remove(image_path)
    except Exception as e:
        logger.exception("Error deleting file from disk")
        
    db.session.delete(img)
    db.session.commit()
    return jsonify({'success': True})

@bp.route('/admin/api/order/<int:order_id>')
@admin_required_api
def api_order_detail(order_id):
    """API endpoint to get order details for modal"""
    order = Order.query.get_or_404(order_id)
    
    # Get order items with product details
    items = []
    for item in order.items:
        product = Product.query.get(item.product_id)
        if product:
            items.append({
                'name': product.name,
                'quantity': item.quantity,
                'price': "{:,.0f}".format(item.price) + " VNĐ",
                'subtotal': "{:,.0f}".format(item.quantity * item.price) + " VNĐ"
            })
    
    # Format status badge
    status_badge = ""
    if order.status == 'pending':
        status_badge = '<span class="badge badge-warning">Chờ xử lý</span>'
    elif order.status == 'processing':
        status_badge = '<span class="badge badge-info">Đang xử lý</span>'
    elif order.status == 'completed':
        status_badge = '<span class="badge badge-success">Hoàn thành</span>'
    else:
        status_badge = '<span class="badge badge-danger">Hủy</span>'
    
    return jsonify({
        'id': order.id,
        'customer_name': order.customer_name,
        'customer_phone': order.customer_phone,
        'created_at': order.created_at.strftime('%d/%m/%Y %H:%M') if order.created_at else 'N/A',
        'status': order.status,
        'status_badge': status_badge,
        'total_amount': "{:,.0f}".format(order.total_amount) + " VNĐ",
        'notes': order.notes or '',
        'items': items
    })

@bp.route('/admin/api/new_orders')
@admin_required_api
def api_new_orders():
    """Poll endpoint: orders placed after `since` (order id), for browser-side sound alerts"""
    since = request.args.get('since', 0, type=int)
    new_orders = Order.query.filter(Order.id > since).order_by(Order.id.asc()).all()

    result = []
    for order in new_orders:
        items = []
        for item in order.items:
            product = Product.query.get(item.product_id)
            items.append({
                'name': product.name if product else 'Sản phẩm đã xóa',
                'quantity': item.quantity
            })
        result.append({
            'id': order.id,
            'customer_name': order.customer_name,
            'customer_phone': order.customer_phone,
            'items': items,
            'notes': order.notes or '',
            'total_amount': "{:,.0f}".format(order.total_amount) + " VNĐ"
        })

    latest_id = new_orders[-1].id if new_orders else since
    return jsonify({'orders': result, 'latest_id': latest_id})

@bp.route('/admin/order/<int:order_id>/update', methods=['POST'])
@admin_required
def update_order_status(order_id):
    order = Order.query.get_or_404(order_id)
    new_status = request.form.get('status')
    order.status = new_status
    db.session.commit()

    flash(f'Đơn #{order.id}: {"đã hoàn thành" if new_status == "completed" else "ghi nợ"}',
          'success')
    # Return to the page the change was made on. Only our own endpoints are
    # accepted, so this cannot be used to bounce an admin off-site.
    nxt = request.form.get('next')
    if nxt in ('orders', 'debts'):
        return redirect(url_for(f'admin.admin_{nxt}'))
    return redirect(url_for('admin.admin_dashboard'))

@bp.route('/admin/orders')
@admin_required
def admin_orders():
    """Orders on their own page, separate from the dashboard.

    The dashboard mixes orders with revenue, stock and room figures; this is
    just the list, with the one control that matters day to day - whether an
    order is still owed or settled.
    """
    status_filter = request.args.get('status', 'all')

    query = Order.query
    if status_filter == 'debt':
        query = query.filter(Order.status.notin_(['completed', 'cancelled']))
    elif status_filter in ('completed', 'cancelled'):
        query = query.filter(Order.status == status_filter)

    orders = query.order_by(Order.created_at.desc()).all()

    # counts for the filter chips, always over every order not just the
    # filtered set, so the numbers do not change as you click around
    all_orders = Order.query.all()
    counts = {
        'all': len(all_orders),
        'debt': len([o for o in all_orders
                     if o.status not in ('completed', 'cancelled')]),
        'completed': len([o for o in all_orders if o.status == 'completed']),
        'cancelled': len([o for o in all_orders if o.status == 'cancelled']),
    }
    total_debt = sum(o.total_amount for o in all_orders
                     if o.status not in ('completed', 'cancelled'))

    return render_template('admin_orders.html', orders=orders, counts=counts,
                           total_debt=total_debt, status_filter=status_filter)


@bp.route('/admin/order/<int:order_id>/receipt')
@admin_required
def order_receipt(order_id):
    """A receipt sized for thermal paper, for the POS terminal's printer.

    Printing goes through the browser: the page carries @page and print CSS
    for 80mm roll, so the device's own print service handles it and no driver
    or app has to be installed on the terminal.
    """
    order = Order.query.get_or_404(order_id)
    items = OrderItem.query.filter_by(order_id=order.id).all()
    return render_template('receipt.html', order=order, items=items,
                           payment=(payments.payment_details(order)
                                    if order.payment_method == 'bank' else None),
                           order_code=payments.order_code(order.id),
                           width=request.args.get('w', '80'))


@bp.route('/admin/pos')
@admin_required
def pos():
    """Counter screen for the POS terminal: tap items, take payment, print.

    Everything is on one screen because the terminal is held in one hand -
    there is no room for a multi-step flow.
    """
    products = Product.query.filter(Product.stock > 0).order_by(
        Product.item_type, Product.name).all()
    return render_template('pos.html', products=products,
                           bank_enabled=payments.is_configured())


@bp.route('/admin/pos/order', methods=['POST'])
@admin_required
def pos_create_order():
    """Create an order from the counter screen.

    Mirrors the customer checkout: stock is verified before anything is
    written, then decremented, so the two ways of ordering cannot oversell
    between them.
    """
    product_ids = request.form.getlist('product_id')
    quantities = request.form.getlist('quantity')
    payment_method = request.form.get('payment_method', 'cash')
    customer_name = (request.form.get('customer_name') or '').strip()
    notes = (request.form.get('notes') or '').strip()

    lines = []
    for pid, qty in zip(product_ids, quantities):
        try:
            pid, qty = int(pid), int(qty)
        except (TypeError, ValueError):
            continue
        if qty > 0:
            lines.append((pid, qty))

    if not lines:
        flash('Chưa chọn món nào', 'error')
        return redirect(url_for('admin.pos'))

    total = 0
    resolved = []
    for pid, qty in lines:
        product = db.session.get(Product, pid)
        if product is None:
            flash('Một sản phẩm không còn tồn tại, vui lòng chọn lại', 'error')
            return redirect(url_for('admin.pos'))
        if qty > product.stock:
            flash(f'"{product.name}" chỉ còn {product.stock}', 'error')
            return redirect(url_for('admin.pos'))
        resolved.append((product, qty))
        total += product.price * qty

    order = Order(
        customer_name=customer_name or 'Khách tại quán',
        customer_phone='Not provided',
        total_amount=total,
        payment_method=payment_method,
        # Paid at the counter in cash means it is settled immediately; a
        # transfer is only settled once the money actually arrives, so it
        # stays owed until someone marks it off.
        status='completed' if payment_method == 'cash' else 'pending',
        notes=notes or None,
    )
    db.session.add(order)
    db.session.flush()

    for product, qty in resolved:
        db.session.add(OrderItem(order_id=order.id, product_id=product.id,
                                 quantity=qty, price=product.price))
        product.stock -= qty

    create_notification('new_order',
                        f'Đơn tại quầy #{order.id} - {total:,.0f} VNĐ')
    db.session.commit()

    return redirect(url_for('admin.order_receipt', order_id=order.id, print=1))


@bp.route('/admin/seo', methods=['GET', 'POST'])
@super_admin_required
def admin_seo():
    """Edit the text search engines and social previews use.

    Everything here has a built-in default, so clearing a field restores the
    original wording rather than blanking the site.
    """
    import seo as seo_mod

    if request.method == 'POST':
        # "restore the generated image" is its own button, and must not also
        # save the text fields it happens to be submitted alongside
        if request.form.get('action') == 'reset_og':
            seo_mod.clear_og_image(current_app.root_path)
            seo_mod.save_settings({'og_image': ''})
            flash('Đã trở về ảnh chia sẻ mặc định', 'success')
            return redirect(url_for('admin.admin_seo'))

        values = request.form.to_dict()
        # the filename is set by the upload below, never typed in
        values.pop('og_image', None)

        upload = request.files.get('og_image_file')
        if upload and upload.filename:
            # An admin picking an odd file must never take the page down: any
            # failure here becomes a message, and the rest of the form still
            # saves. The traceback goes to the log so the cause is findable.
            try:
                ok, message = seo_mod.save_og_image(upload, current_app.root_path)
            except Exception as exc:
                logger.exception('Share image upload failed (%s)', upload.filename)
                ok, message = False, f'Không xử lý được ảnh: {type(exc).__name__}'
            flash(message, 'success' if ok else 'error')
            if ok:
                values['og_image'] = seo_mod.OG_UPLOAD_NAME

        changed = seo_mod.save_settings(values)
        flash(f'Đã lưu {changed} thay đổi' if changed else 'Không có gì thay đổi',
              'success' if changed else 'info')
        return redirect(url_for('admin.admin_seo'))

    return render_template('admin_seo.html',
                           cfg=seo_mod.settings(),
                           defaults=seo_mod.DEFAULTS,
                           site_url=seo_mod.site_url(),
                           og_file=seo_mod.og_image_file(),
                           og_is_custom=bool(seo_mod.settings().get('og_image')))


@bp.route('/admin/debts')
@super_admin_required
def admin_debts():
    debt_orders = Order.query.filter(
        Order.status.notin_(['completed', 'cancelled'])
    ).order_by(Order.created_at.desc()).all()
    total_debt = sum(order.total_amount for order in debt_orders)
    return render_template('admin_debts.html', debt_orders=debt_orders, total_debt=total_debt)

@bp.route('/admin/debt/<int:order_id>/pay', methods=['POST'])
@super_admin_required
def admin_debt_pay(order_id):
    order = Order.query.get_or_404(order_id)
    order.status = 'completed'
    db.session.commit()
    flash(f'Đã xác nhận {order.customer_name} trả hết nợ cho đơn #{order.id}', 'success')
    return redirect(url_for('admin.admin_debts'))

@bp.route('/admin/debts/bulk_pay', methods=['POST'])
@super_admin_required
def admin_debts_bulk_pay():
    order_ids = request.form.getlist('order_ids')
    if not order_ids:
        flash('Vui lòng chọn ít nhất một khoản nợ', 'error')
        return redirect(url_for('admin.admin_debts'))

    count = Order.query.filter(Order.id.in_(order_ids)).update(
        {'status': 'completed'}, synchronize_session=False
    )
    db.session.commit()
    flash(f'Đã xóa {count} khoản nợ đã chọn', 'success')
    return redirect(url_for('admin.admin_debts'))

@bp.route('/admin/generate_qr', methods=['GET', 'POST'])
@admin_required
def generate_qr():
    if request.method == 'POST':
        # Get form data
        url = request.form.get('url', 'http://localhost:5000')
        size = int(request.form.get('size', 15))
        bg_color = request.form.get('bg_color', '#ffffff')
        fg_color = request.form.get('fg_color', '#000000')
        border = int(request.form.get('border', 1))
        
        # Generate QR code with custom parameters
        qr = qrcode.QRCode(
            version=1,
            box_size=size,
            border=border
        )
        qr.add_data(url)
        qr.make(fit=True)
        
        # Create image with custom colors
        img = qr.make_image(fill_color=fg_color, back_color=bg_color)
    else:
        # Default QR code for GET request
        qr = qrcode.QRCode(version=1, box_size=10, border=5)
        # Use localhost instead of hardcoded IP
        qr.add_data(f'http://localhost:5000/customer')
        qr.make(fit=True)
        
        img = qr.make_image(fill_color="white", back_color="black")
    
    # Convert to base64 for display
    img_buffer = io.BytesIO()
    img.save(img_buffer)
    img_buffer.seek(0)
    img_base64 = base64.b64encode(img_buffer.getvalue()).decode()
    
    return render_template('qr_code.html', qr_code=img_base64)

@bp.route('/admin/generate_bank_qr', methods=['GET', 'POST'])
@admin_required
def generate_bank_qr():
    qr_url = None
    if request.method == 'POST':
        bank_id = request.form.get('bank_id', 'VCB')
        account_no = request.form.get('account_no', '')
        account_name = request.form.get('account_name', '')
        amount = request.form.get('amount', '')
        add_info = request.form.get('add_info', '')
        template = request.form.get('template', 'print')
        
        import urllib.parse
        encoded_account_name = urllib.parse.quote(account_name)
        encoded_add_info = urllib.parse.quote(add_info)
        
        qr_url = f"https://img.vietqr.io/image/{bank_id}-{account_no}-{template}.jpg"
        params = []
        if amount:
            params.append(f"amount={amount}")
        if add_info:
            params.append(f"addInfo={encoded_add_info}")
        if account_name:
            params.append(f"accountName={encoded_account_name}")
            
        if params:
            qr_url += "?" + "&".join(params)
            
    return render_template('bank_qr.html', qr_url=qr_url)

@bp.route('/admin/export_orders')
@super_admin_required
def export_orders():
    # Get today's date
    today = datetime.now().strftime('%Y-%m-%d')
    
    # Get orders for today
    today_start = datetime.now().replace(hour=0, minute=0, second=0, microsecond=0)
    today_end = datetime.now().replace(hour=23, minute=59, second=59, microsecond=999999)
    
    orders = Order.query.filter(
        Order.created_at >= today_start,
        Order.created_at <= today_end
    ).order_by(Order.created_at.desc()).all()
    
    # Create Excel workbook
    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = f"Orders_{today}"
    
    # Define styles
    header_font = Font(bold=True, color='FFFFFF')
    header_fill = PatternFill(start_color='4472C4', end_color='4472C4', fill_type='solid')
    border = Border(left=Side(style='thin'), right=Side(style='thin'), 
                   top=Side(style='thin'), bottom=Side(style='thin'))
    
    # Set column widths
    ws.column_dimensions['A'].width = 10
    ws.column_dimensions['B'].width = 20
    ws.column_dimensions['C'].width = 15
    ws.column_dimensions['D'].width = 15
    ws.column_dimensions['E'].width = 15
    ws.column_dimensions['F'].width = 15
    ws.column_dimensions['G'].width = 20
    
    # Create headers
    headers = ['Order ID', 'Customer Name', 'Phone', 'Total (VNĐ)', 'Payment Method', 'Status', 'Order Date']
    for col, header in enumerate(headers, 1):
        cell = ws.cell(row=1, column=col, value=header)
        cell.font = header_font
        cell.fill = header_fill
        cell.border = border
        cell.alignment = Alignment(horizontal='center')
    
    # Add data
    for row, order in enumerate(orders, 2):
        # Order ID
        ws.cell(row=row, column=1, value=f"#{order.id}").border = border
        
        # Customer Name
        ws.cell(row=row, column=2, value=order.customer_name).border = border
        
        # Phone
        ws.cell(row=row, column=3, value=order.customer_phone).border = border
        
        # Total Amount
        ws.cell(row=row, column=4, value=f"{order.total_amount:,.0f} VNĐ").border = border
        
        # Payment Method
        payment_display = {
            'cash': '💵 Cash',
            'bank_transfer': '🏦 Bank Transfer',
            'pending': '⏳ Pending'
        }.get(order.payment_method, order.payment_method)
        ws.cell(row=row, column=5, value=payment_display).border = border
        
        # Status
        status_display = {
            'pending': '⏳ Pending',
            'completed': '✅ Completed',
            'cancelled': '❌ Cancelled'
        }.get(order.status, order.status)
        ws.cell(row=row, column=6, value=status_display).border = border
        
        # Order Date
        ws.cell(row=row, column=7, value=order.created_at.strftime('%Y-%m-%d %H:%M:%S')).border = border
    
    # Add summary section
    summary_row = len(orders) + 3
    ws.cell(row=summary_row, column=1, value="Summary").font = Font(bold=True)
    ws.cell(row=summary_row + 1, column=1, value=f"Total Orders: {len(orders)}")
    ws.cell(row=summary_row + 2, column=1, value=f"Total Revenue: {sum(order.total_amount for order in orders):,.0f} VNĐ")
    
    # Save to memory
    excel_buffer = io.BytesIO()
    wb.save(excel_buffer)
    excel_buffer.seek(0)
    
    # Create filename
    filename = f"orders_{today}.xlsx"
    
    return send_file(
        excel_buffer,
        as_attachment=True,
        download_name=filename,
        mimetype='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet'
    )

# Automation Control Routes

@bp.route('/admin/automation_settings')
@super_admin_required
def automation_settings():
    screen_info = automation_controller.get_screen_info()
    return render_template('automation_settings.html',
                         automation=automation_controller,
                         laptop_speaker=laptop_speaker,
                         screen_info=screen_info)

@bp.route('/admin/automation_toggle', methods=['POST'])
@super_admin_required
def automation_toggle():
    automation_controller.enabled = not automation_controller.enabled
    status = "bật" if automation_controller.enabled else "tắt"
    flash(f'Tự động hóa đã được {status}.', 'success')
    
    return redirect(url_for('admin.automation_settings'))

@bp.route('/admin/emergency_stop', methods=['POST'])
@super_admin_required
def emergency_stop():
    automation_controller.emergency_stop()
    flash('Đã dừng khẩn cấp tất cả tự động hóa!', 'warning')
    
    return redirect(url_for('admin.automation_settings'))

@bp.route('/admin/speaker_test', methods=['POST'])
@super_admin_required
def speaker_test():
    try:
        success = laptop_speaker.test_speaker()
        if success:
            flash('Kiểm tra loa laptop thành công!', 'success')
        else:
            flash('Kiểm tra loa laptop thất bại. Vui lòng kiểm tra cài đặt.', 'error')
    except Exception as e:
        flash(f'Lỗi kiểm tra loa: {e}', 'error')
    
    return redirect(url_for('admin.automation_settings'))

@bp.route('/admin/test_notification', methods=['POST'])
@super_admin_required
def test_notification():
    automation_controller.show_order_notification(999, "Khách test", 100000)
    flash('Đã gửi thông báo kiểm tra!', 'success')
    
    return redirect(url_for('admin.automation_settings'))

# Laptop Speaker Control Routes

@bp.route('/admin/speaker_toggle', methods=['POST'])
@super_admin_required
def speaker_toggle():
    enabled = laptop_speaker.toggle_enabled()
    status = "bật" if enabled else "tắt"
    flash(f'Thông báo loa laptop đã được {status}.', 'success')
    
    return redirect(url_for('admin.automation_settings'))

@bp.route('/admin/speaker_voice_settings', methods=['POST'])
@super_admin_required
def speaker_voice_settings():
    rate = request.form.get('voice_rate')
    volume = request.form.get('voice_volume')
    
    try:
        # Chuyển đổi thành số nếu có
        rate_value = int(rate) if rate else None
        volume_value = float(volume) if volume else None
        
        # Gọi set_voice_settings một lần với cả hai tham số
        laptop_speaker.set_voice_settings(rate=rate_value, volume=volume_value)
        
        flash('Cài đặt giọng nói đã được cập nhật!', 'success')
    except Exception as e:
        flash(f'Lỗi cập nhật cài đặt: {e}', 'error')
    
    return redirect(url_for('admin.automation_settings'))

@bp.route('/admin/toggle_tts_engine', methods=['POST'])
@super_admin_required
def toggle_tts_engine():
    try:
        # Toggle between gTTS and pyttsx3
        laptop_speaker.use_gtts = not laptop_speaker.use_gtts
        
        engine_type = "gTTS (Google Text-to-Speech)" if laptop_speaker.use_gtts else "pyttsx3 (Windows TTS)"
        flash(f'Đã chuyển sang sử dụng {engine_type}', 'success')
        
        # Reinitialize with new engine
        laptop_speaker.initialize_engine()
        
    except Exception as e:
        flash(f'Lỗi chuyển đổi engine TTS: {e}', 'error')
    
    return redirect(url_for('admin.automation_settings'))

# Account management (Super Admin only)

@bp.route('/admin/accounts')
@super_admin_required
def admin_accounts():
    admins = Admin.query.order_by(Admin.username).all()
    managers = Customer.query.filter_by(role='manager').order_by(Customer.username).all()
    customers = Customer.query.filter_by(role='customer').order_by(Customer.username).all()
    return render_template('admin_accounts.html', admins=admins, managers=managers, customers=customers)

@bp.route('/admin/accounts/add_admin', methods=['POST'])
@super_admin_required
def admin_accounts_add_admin():
    username = request.form.get('username', '').strip()
    password = request.form.get('password', '').strip()
    role = request.form.get('role', 'admin')

    if role not in ('admin', 'super_admin'):
        role = 'admin'

    if not username or not password:
        flash('Vui lòng nhập đầy đủ tên đăng nhập và mật khẩu', 'error')
        return redirect(url_for('admin.admin_accounts'))

    if Admin.query.filter_by(username=username).first():
        flash('Tên đăng nhập admin đã tồn tại', 'error')
        return redirect(url_for('admin.admin_accounts'))

    db.session.add(Admin(username=username, password=generate_password_hash(password), role=role))
    db.session.commit()
    flash(f'Đã tạo tài khoản {role} "{username}"', 'success')
    return redirect(url_for('admin.admin_accounts'))

@bp.route('/admin/accounts/<int:admin_id>/change_role', methods=['POST'])
@super_admin_required
def admin_accounts_change_role(admin_id):
    target = Admin.query.get_or_404(admin_id)
    new_role = request.form.get('role')
    if new_role not in ('admin', 'super_admin'):
        flash('Vai trò không hợp lệ', 'error')
        return redirect(url_for('admin.admin_accounts'))

    if target.role == 'super_admin' and new_role == 'admin':
        remaining = Admin.query.filter(Admin.role == 'super_admin', Admin.id != target.id).count()
        if remaining == 0:
            flash('Không thể hạ quyền — đây là Super Admin cuối cùng', 'error')
            return redirect(url_for('admin.admin_accounts'))

    target.role = new_role
    db.session.commit()
    flash(f'Đã đổi quyền của "{target.username}" thành {new_role}', 'success')
    return redirect(url_for('admin.admin_accounts'))

@bp.route('/admin/accounts/<int:admin_id>/reset_password', methods=['POST'])
@super_admin_required
def admin_accounts_reset_admin_password(admin_id):
    target = Admin.query.get_or_404(admin_id)
    new_password = request.form.get('new_password', '')
    if len(new_password) < 6:
        flash('Mật khẩu mới phải có ít nhất 6 ký tự', 'error')
        return redirect(url_for('admin.admin_accounts'))
    target.password = generate_password_hash(new_password)
    db.session.commit()
    flash(f'Đã đặt lại mật khẩu cho "{target.username}"', 'success')
    return redirect(url_for('admin.admin_accounts'))

@bp.route('/admin/accounts/<int:customer_id>/reset_customer_password', methods=['POST'])
@super_admin_required
def admin_accounts_reset_customer_password(customer_id):
    target = Customer.query.get_or_404(customer_id)
    new_password = request.form.get('new_password', '')
    if len(new_password) < 6:
        flash('Mật khẩu mới phải có ít nhất 6 ký tự', 'error')
        return redirect(url_for('admin.admin_accounts'))
    target.password = generate_password_hash(new_password)
    db.session.commit()
    flash(f'Đã đặt lại mật khẩu cho "{target.username}"', 'success')
    return redirect(url_for('admin.admin_accounts'))

@bp.route('/admin/accounts/<int:admin_id>/delete_admin', methods=['POST'])
@super_admin_required
def admin_accounts_delete_admin(admin_id):
    target = Admin.query.get_or_404(admin_id)

    if target.username == session.get('admin_username'):
        flash('Không thể tự xóa tài khoản đang đăng nhập', 'error')
        return redirect(url_for('admin.admin_accounts'))

    if target.role == 'super_admin':
        remaining = Admin.query.filter(Admin.role == 'super_admin', Admin.id != target.id).count()
        if remaining == 0:
            flash('Không thể xóa — đây là Super Admin cuối cùng', 'error')
            return redirect(url_for('admin.admin_accounts'))

    db.session.delete(target)
    db.session.commit()
    flash(f'Đã xóa tài khoản "{target.username}"', 'success')
    return redirect(url_for('admin.admin_accounts'))

@bp.route('/admin/accounts/<int:customer_id>/toggle_manager', methods=['POST'])
@super_admin_required
def admin_accounts_toggle_manager(customer_id):
    customer = Customer.query.get_or_404(customer_id)
    customer.role = 'customer' if customer.role == 'manager' else 'manager'
    db.session.commit()
    status = 'chỉ định làm Manager' if customer.role == 'manager' else 'gỡ quyền Manager'
    flash(f'Đã {status} cho "{customer.username}"', 'success')
    return redirect(url_for('admin.admin_accounts'))
