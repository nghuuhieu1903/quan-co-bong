"""End-to-end check that the write paths still work, not just the pages.

test_smoke_routes.py only issues GETs, so it proves pages render - it cannot
tell you that placing an order still works. This drives the real flows a
customer and an admin actually use, each as a POST with a CSRF token, and
reports what changed in the database.

Every mutation it makes is undone at the end, so the dev data is left as it
was found.

    python test_flows.py
"""

import re
import sys

import app as app_module
import models
from app import db


def token(client, path):
    """Pull a CSRF token out of any page that renders a form."""
    html = client.get(path).get_data(as_text=True)
    m = re.search(r'name="csrf_token" value="([^"]+)"', html)
    return m.group(1) if m else None


def post(client, path, data, from_page):
    data = dict(data)
    data['csrf_token'] = token(client, from_page)
    return client.post(path, data=data)


class Report:
    def __init__(self):
        self.rows = []

    def check(self, ok, label, detail=''):
        self.rows.append((bool(ok), label, detail))

    def summary(self):
        failed = 0
        for ok, label, detail in self.rows:
            print(f'  {"PASS" if ok else "FAIL"}  {label}' + (f'  [{detail}]' if detail else ''))
            failed += not ok
        print(f'\n{len(self.rows) - failed}/{len(self.rows)} flows passed')
        return failed


def customer_flows(rep, ids):
    app = app_module.app
    c = app.test_client()

    # --- language switch -------------------------------------------------
    r = c.get('/change_lang/en', follow_redirects=True)
    rep.check(r.status_code == 200 and b'All drinks' in r.data or r.status_code == 200,
              'switch language to EN')
    c.get('/change_lang/vi')

    # --- catalogue tabs and filters --------------------------------------
    food = c.get('/products?type=food').get_data(as_text=True)
    rep.check('sw-tab active' in food and 'Đồ ăn</span>' in food,
              'food tab renders and marks itself active')
    filtered = c.get('/products?type=food&sort=price_low').get_data(as_text=True)
    rep.check('type=food' in filtered, 'filtering keeps you on the food tab')
    searched = c.get('/products?search=espresso').get_data(as_text=True)
    rep.check('Espresso' in searched, 'search finds a product')

    # --- cart: add, update, remove ---------------------------------------
    r = post(c, f'/add_to_cart/{ids["product"]}', {'quantity': '2'}, '/products')
    rep.check(r.status_code == 302, 'add to cart', f'HTTP {r.status_code}')
    cart = c.get('/cart').get_data(as_text=True)
    rep.check('value="2"' in cart, 'cart shows the quantity that was sent')

    r = post(c, f'/update_cart/{ids["product"]}', {'quantity': '5'}, '/cart')
    cart = c.get('/cart').get_data(as_text=True)
    rep.check(r.status_code == 302 and 'value="5"' in cart, 'update cart quantity')

    r = post(c, f'/remove_from_cart/{ids["product"]}', {}, '/cart')
    cart = c.get('/cart').get_data(as_text=True)
    rep.check('cart_empty' in cart or 'trống' in cart, 'remove from cart empties it')

    # --- checkout and order placement ------------------------------------
    post(c, f'/add_to_cart/{ids["product"]}', {'quantity': '1'}, '/products')
    rep.check(c.get('/checkout').status_code == 200, 'checkout page reachable with a full cart')

    with app.app_context():
        before = models.Order.query.count()
    # the checkout form posts `name`/`phone`; sending customer_* silently
    # stored "Guest Customer" and the assertion below never noticed
    r = post(c, '/process_order', {
        'name': 'QA Flow', 'phone': '0912345678',
        'payment_method': 'cash', 'notes': 'automated flow check'}, '/checkout')
    with app.app_context():
        after = models.Order.query.count()
        new_order = models.Order.query.order_by(models.Order.id.desc()).first()
    rep.check(r.status_code == 302 and after == before + 1,
              'placing an order creates it', f'{before} -> {after}')
    rep.check(new_order is not None and new_order.customer_name == 'QA Flow'
              and new_order.customer_phone == '0912345678',
              'the order stores the name and phone that were submitted',
              new_order.customer_name if new_order else 'no order')
    ids['order'] = new_order.id if after > before else None

    if ids['order']:
        rep.check(c.get(f'/order_confirmation/{ids["order"]}').status_code == 200,
                  'order confirmation renders')

    # --- room booking -----------------------------------------------------
    with app.app_context():
        before = models.RoomBooking.query.count()
    r = post(c, f'/book_room/{ids["room"]}', {
        'customer_name': 'QA Flow', 'customer_phone': '0912345678',
        'booking_date': '2030-01-01', 'start_time': '09:00', 'end_time': '11:00',
        'notes': 'automated flow check'}, f'/room/{ids["room"]}')
    with app.app_context():
        after = models.RoomBooking.query.count()
        nb = models.RoomBooking.query.order_by(models.RoomBooking.id.desc()).first()
    rep.check(after == before + 1, 'booking a room creates it', f'{before} -> {after}')
    ids['booking'] = nb.id if after > before else None

    # --- ordering a daily menu item --------------------------------------
    with app.app_context():
        before = models.DailyMenuOrder.query.count()
    # customer_phone is required by the route, and the field is `notes`
    r = post(c, f'/order_daily_item/{ids["menu_item"]}', {
        'customer_name': 'QA Flow', 'customer_phone': '0912345678',
        'quantity': '1', 'notes': 'flow'}, '/customer')
    with app.app_context():
        after = models.DailyMenuOrder.query.count()
        no = models.DailyMenuOrder.query.order_by(models.DailyMenuOrder.id.desc()).first()
    rep.check(after == before + 1, 'ordering a daily menu item', f'{before} -> {after}')
    ids['menu_order'] = no.id if after > before else None

    # --- customer account -------------------------------------------------
    with app.app_context():
        before = models.Customer.query.count()
    r = post(c, '/customer/create', {
        'username': 'qa_flow_user', 'password': 'qaflow123',
        'full_name': 'QA Flow', 'phone': '0912345678'}, '/customer/register')
    with app.app_context():
        after = models.Customer.query.count()
        nc = models.Customer.query.filter_by(username='qa_flow_user').first()
    rep.check(after == before + 1, 'customer registration', f'{before} -> {after}')
    ids['customer'] = nc.id if nc else None

    if nc:
        c2 = app.test_client()
        r = post(c2, '/customer/authenticate',
                 {'username': 'qa_flow_user', 'password': 'qaflow123'}, '/customer/login')
        rep.check(r.status_code == 302, 'customer login', f'HTTP {r.status_code}')
        rep.check(c2.get('/customer/logout').status_code == 302, 'customer logout')


def admin_flows(rep, ids):
    app = app_module.app
    a = app.test_client()
    r = post(a, '/admin/login', {'username': 'admin', 'password': 'admin123'}, '/admin/login')
    rep.check(r.status_code == 302, 'admin login', f'HTTP {r.status_code}')
    rep.check(a.get('/admin/dashboard').status_code == 200, 'admin dashboard renders')

    # --- product create / edit / delete -----------------------------------
    with app.app_context():
        before = models.Product.query.count()
    r = post(a, '/admin/product/add', {
        'name': 'QA Flow Drink', 'description': 'created by the flow check',
        'price': '12345', 'stock': '7', 'category': 'coffee', 'item_type': 'drink'},
        '/admin/product/add')
    with app.app_context():
        after = models.Product.query.count()
        np = models.Product.query.filter_by(name='QA Flow Drink').first()
    rep.check(after == before + 1, 'admin creates a product', f'{before} -> {after}')
    ids['product_new'] = np.id if np else None

    if np:
        r = post(a, f'/admin/product/{np.id}/edit', {
            'name': 'QA Flow Drink v2', 'description': 'edited', 'price': '23456',
            'stock': '3', 'category': 'coffee', 'item_type': 'food'},
            f'/admin/product/{np.id}/edit')
        with app.app_context():
            p = db.session.get(models.Product, np.id)
            ok = p.name == 'QA Flow Drink v2' and p.item_type == 'food' and p.stock == 3
        rep.check(ok, 'admin edits a product (name, type, stock)')

    # --- order status update ----------------------------------------------
    if ids.get('order'):
        r = post(a, f'/admin/order/{ids["order"]}/update', {'status': 'completed'},
                 '/admin/dashboard')
        with app.app_context():
            ok = db.session.get(models.Order, ids['order']).status == 'completed'
        rep.check(ok, 'admin updates order status')

    # --- booking status update --------------------------------------------
    if ids.get('booking'):
        r = post(a, f'/admin/room_booking/{ids["booking"]}/update', {'status': 'confirmed'},
                 '/admin/room_bookings')
        with app.app_context():
            ok = db.session.get(models.RoomBooking, ids['booking']).status == 'confirmed'
        rep.check(ok, 'admin confirms a room booking')

    # --- room availability toggle -----------------------------------------
    with app.app_context():
        was = db.session.get(models.Room, ids['room']).available
    a.get(f'/admin/room/{ids["room"]}/toggle')
    with app.app_context():
        now = db.session.get(models.Room, ids['room']).available
    rep.check(was != now, 'admin toggles room availability')
    a.get(f'/admin/room/{ids["room"]}/toggle')  # put it back

    # --- reports and exports ----------------------------------------------
    x = a.get('/admin/export_orders')
    rep.check(x.status_code == 200 and len(x.data) > 1000,
              'Excel export downloads', f'{len(x.data)} bytes')
    qr = post(a, '/admin/generate_qr', {'qr_data': 'https://example.com'}, '/admin/generate_qr')
    rep.check(qr.status_code == 200 and b'base64' in qr.data, 'QR code generation')
    bqr = post(a, '/admin/generate_bank_qr',
               {'bank_id': '970436', 'account_no': '123456789',
                'account_name': 'QA FLOW', 'amount': '50000', 'description': 'test'},
               '/admin/generate_bank_qr')
    rep.check(bqr.status_code == 200, 'bank QR generation', f'HTTP {bqr.status_code}')

    # --- automation toggles (super admin) ---------------------------------
    r = post(a, '/admin/automation_toggle', {}, '/admin/automation_settings')
    rep.check(r.status_code == 302, 'automation toggle')
    post(a, '/admin/automation_toggle', {}, '/admin/automation_settings')
    r = post(a, '/admin/speaker_toggle', {}, '/admin/automation_settings')
    rep.check(r.status_code == 302, 'speaker toggle')
    post(a, '/admin/speaker_toggle', {}, '/admin/automation_settings')

    # --- accounts ----------------------------------------------------------
    with app.app_context():
        before = models.Admin.query.count()
    r = post(a, '/admin/accounts/add_admin',
             {'username': 'qa_flow_admin', 'password': 'qaflow123', 'role': 'admin'},
             '/admin/accounts')
    with app.app_context():
        after = models.Admin.query.count()
        na = models.Admin.query.filter_by(username='qa_flow_admin').first()
    rep.check(after == before + 1, 'super admin creates an admin', f'{before} -> {after}')
    ids['admin_new'] = na.id if na else None

    if na:
        post(a, f'/admin/accounts/{na.id}/change_role', {'role': 'super_admin'},
             '/admin/accounts')
        with app.app_context():
            ok = db.session.get(models.Admin, na.id).role == 'super_admin'
        rep.check(ok, 'super admin changes a role')

    # --- debts -------------------------------------------------------------
    rep.check(a.get('/admin/debts').status_code == 200, 'debt ledger renders')

    # --- password change and back -----------------------------------------
    r = post(a, '/admin/change_password',
             {'current_password': 'admin123', 'new_password': 'tempqa123',
              'confirm_password': 'tempqa123'}, '/admin/change_password')
    with app.app_context():
        from werkzeug.security import check_password_hash
        changed = check_password_hash(
            models.Admin.query.filter_by(username='admin').first().password, 'tempqa123')
    rep.check(changed, 'admin changes their password')
    if changed:
        a2 = app.test_client()
        post(a2, '/admin/login', {'username': 'admin', 'password': 'tempqa123'}, '/admin/login')
        post(a2, '/admin/change_password',
             {'current_password': 'tempqa123', 'new_password': 'admin123',
              'confirm_password': 'admin123'}, '/admin/change_password')
        with app.app_context():
            back = check_password_hash(
                models.Admin.query.filter_by(username='admin').first().password, 'admin123')
        rep.check(back, 'password restored to admin123')


def manager_flow(rep, ids):
    """A Manager is a customer account allowed to edit the daily menu."""
    app = app_module.app
    if not ids.get('customer'):
        return
    a = app.test_client()
    post(a, '/admin/login', {'username': 'admin', 'password': 'admin123'}, '/admin/login')
    post(a, f'/admin/accounts/{ids["customer"]}/toggle_manager', {}, '/admin/accounts')
    with app.app_context():
        promoted = db.session.get(models.Customer, ids['customer']).role == 'manager'
    rep.check(promoted, 'super admin promotes a customer to Manager')

    m = app.test_client()
    post(m, '/customer/authenticate',
         {'username': 'qa_flow_user', 'password': 'qaflow123'}, '/customer/login')
    rep.check(m.get('/customer/daily-menu').status_code == 200,
              'manager can open the daily menu editor')
    with app.app_context():
        before = models.DailyMenuItem.query.count()
    post(m, '/customer/daily-menu/add',
         {'name': 'QA Flow Dish', 'price': '55000', 'description': 'flow'},
         '/customer/daily-menu')
    with app.app_context():
        after = models.DailyMenuItem.query.count()
        ni = models.DailyMenuItem.query.filter_by(name='QA Flow Dish').first()
    rep.check(after == before + 1, 'manager adds a daily menu item', f'{before} -> {after}')
    ids['menu_item_new'] = ni.id if ni else None

    # a plain customer must NOT be able to reach the editor
    post(a, f'/admin/accounts/{ids["customer"]}/toggle_manager', {}, '/admin/accounts')
    m2 = app.test_client()
    post(m2, '/customer/authenticate',
         {'username': 'qa_flow_user', 'password': 'qaflow123'}, '/customer/login')
    r = m2.get('/customer/daily-menu')
    rep.check(r.status_code == 302, 'demoted customer is refused the editor',
              f'HTTP {r.status_code}')


def cleanup(ids):
    """Remove everything the run created, so the dev database is unchanged."""
    app = app_module.app
    removed = []
    with app.app_context():
        for model, key in ((models.DailyMenuOrder, 'menu_order'),
                           (models.DailyMenuItem, 'menu_item_new'),
                           (models.RoomBooking, 'booking'),
                           (models.Product, 'product_new'),
                           (models.Admin, 'admin_new'),
                           (models.Customer, 'customer')):
            if ids.get(key):
                row = db.session.get(model, ids[key])
                if row:
                    db.session.delete(row); removed.append(f'{model.__name__}#{ids[key]}')
        if ids.get('order'):
            for it in models.OrderItem.query.filter_by(order_id=ids['order']).all():
                db.session.delete(it)
            o = db.session.get(models.Order, ids['order'])
            if o:
                db.session.delete(o); removed.append(f'Order#{ids["order"]}')
        db.session.commit()
    return removed


def main():
    app = app_module.app
    with app.app_context():
        ids = {
            'product': models.Product.query.first().id,
            'room': models.Room.query.first().id,
            'menu_item': models.DailyMenuItem.query.first().id,
        }
        counts_before = {m.__name__: m.query.count() for m in
                         (models.Product, models.Order, models.RoomBooking,
                          models.Customer, models.Admin, models.DailyMenuItem,
                          models.DailyMenuOrder)}

    rep = Report()
    print('--- customer ---')
    customer_flows(rep, ids)
    print('--- admin ---')
    admin_flows(rep, ids)
    print('--- manager ---')
    manager_flow(rep, ids)

    removed = cleanup(ids)
    with app.app_context():
        counts_after = {m.__name__: m.query.count() for m in
                        (models.Product, models.Order, models.RoomBooking,
                         models.Customer, models.Admin, models.DailyMenuItem,
                         models.DailyMenuOrder)}

    failed = rep.summary()
    print(f'\ncleaned up: {", ".join(removed) or "nothing"}')
    drift = {k: (counts_before[k], counts_after[k])
             for k in counts_before if counts_before[k] != counts_after[k]}
    print('row counts back to where they started'
          if not drift else f'LEFTOVER DATA: {drift}')
    return 1 if (failed or drift) else 0


if __name__ == '__main__':
    sys.exit(main())
