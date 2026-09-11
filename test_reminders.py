"""Check the daily-dish appointment reminder end to end.

    python test_reminders.py

reminders.check_due_reminders() is called the same way the background thread
calls it - with no app context already open - since a nested app_context()
around a Flask-SQLAlchemy call is its own trap: it can look like a working
session while quietly reading through a different scope.
"""

import re
import sys
from datetime import datetime, timedelta

import app as app_module
import models
import reminders
from app import db


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
        print(f'\n{len(self.rows) - failed}/{len(self.rows)} reminder checks passed')
        return failed


def make_order(**over):
    app = app_module.app
    with app.app_context():
        fields = dict(customer_name='QA Reminder', customer_phone='0912345678',
                     total_amount=1, status='pending', payment_method='bank')
        fields.update(over)
        o = models.Order(**fields)
        db.session.add(o)
        db.session.commit()
        return o.id


def get_order(order_id):
    with app_module.app.app_context():
        return db.session.get(models.Order, order_id)


def notified(order_id):
    return get_order(order_id).reminder_notified


def reminder_count():
    with app_module.app.app_context():
        return models.Notification.query.filter_by(type='order_reminder').count()


def delete_order(order_id):
    with app_module.app.app_context():
        for it in models.OrderItem.query.filter_by(order_id=order_id).all():
            product = db.session.get(models.Product, it.product_id)
            if product:
                product.stock += it.quantity
            db.session.delete(it)
        row = db.session.get(models.Order, order_id)
        if row:
            db.session.delete(row)
        db.session.commit()


def main():
    rep = Report()
    app = app_module.app
    made = []

    # --- checkout: the field is optional, and gated on a daily item --------
    with app.app_context():
        daily = models.Product.query.filter_by(is_daily=True).first()
        if daily is None:
            daily = models.Product(name='QA Daily Dish', description='x', price=40000,
                                  stock=50, category='food', item_type='food', is_daily=True)
            db.session.add(daily)
            db.session.commit()
        daily_id, daily_stock = daily.id, daily.stock

        drink = models.Product.query.filter_by(item_type='drink').first()
        drink_id = drink.id if drink else None

    c = app.test_client()
    token = lambda path: re.search(r'name="csrf_token" value="([^"]+)"',
                                   c.get(path).get_data(as_text=True)).group(1)

    c.post(f'/add_to_cart/{daily_id}', data={'quantity': '1',
                                             'csrf_token': token('/products?type=food')})
    cart_html = c.get('/cart').get_data(as_text=True)
    rep.check('name="reminder_at"' in cart_html,
              'the reminder field appears when the cart has a daily dish')

    if drink_id:
        with app.app_context():
            db.session.get(models.Product, daily_id)  # keep session warm
        c2 = app.test_client()
        c2.post(f'/add_to_cart/{drink_id}', data={'quantity': '1',
                                                   'csrf_token': token('/products')})
        cart_html2 = c2.get('/cart').get_data(as_text=True)
        rep.check('name="reminder_at"' not in cart_html2,
                  'and stays hidden for an order with no daily dish')

    # placing the order with no reminder set must still work (it is optional)
    r = c.post('/process_order', data={'name': 'QA No Reminder', 'phone': '0912345678',
                                       'csrf_token': token('/cart')}, follow_redirects=True)
    with app.app_context():
        blank_order = models.Order.query.filter_by(customer_name='QA No Reminder').first()
    rep.check(blank_order is not None and blank_order.reminder_at is None,
              'leaving the reminder blank places the order with no reminder set')
    if blank_order:
        made.append(blank_order.id)

    # placing the order with a reminder set must store it, in the future
    c.post(f'/add_to_cart/{daily_id}', data={'quantity': '1', 'csrf_token': token('/products?type=food')})
    when = (datetime.now() + timedelta(minutes=25)).strftime('%Y-%m-%dT%H:%M')
    c.post('/process_order', data={'name': 'QA With Reminder', 'phone': '0912345678',
                                   'reminder_at': when, 'csrf_token': token('/cart')},
           follow_redirects=True)
    with app.app_context():
        order = models.Order.query.filter_by(customer_name='QA With Reminder').first()
    rep.check(order is not None and order.reminder_at is not None,
              'a chosen reminder time is stored on the order')
    if order:
        made.append(order.id)
        page = c.get(f'/order_confirmation/{order.id}').get_data(as_text=True)
        rep.check('Hẹn nhận món' in page,
                  'the reminder time shows on the order confirmation page')

        with app.app_context():
            latest = models.Notification.query.order_by(models.Notification.id.desc()).first()
        rep.check(latest and 'Hẹn nhận lúc' in latest.message,
                  'the placed-order notification mentions the reminder time',
                  latest.message if latest else '-')

        # the CSRF token has to come from the same session that submits it -
        # fetching it via a throwaway client and posting through a different
        # one is what made this silently fail the login (302 back to it)
        a = app.test_client()
        acsrf = re.search(r'name="csrf_token" value="([^"]+)"',
                          a.get('/admin/login').get_data(as_text=True)).group(1)
        a.post('/admin/login', data={'username': 'admin', 'password': 'admin123',
                                     'csrf_token': acsrf})
        orders_resp = a.get('/admin/orders')
        orders_html = orders_resp.get_data(as_text=True)
        rep.check('order-reminder-badge' in orders_html,
                  'the reminder shows as a badge in the admin orders list',
                  f'HTTP {orders_resp.status_code}, order in page: '
                  f'{"QA With Reminder" in orders_html}')

    # a past reminder time is silently dropped, not rejected
    c.post(f'/add_to_cart/{daily_id}', data={'quantity': '1', 'csrf_token': token('/products?type=food')})
    past = (datetime.now() - timedelta(hours=1)).strftime('%Y-%m-%dT%H:%M')
    c.post('/process_order', data={'name': 'QA Past Reminder', 'phone': '0912345678',
                                   'reminder_at': past, 'csrf_token': token('/cart')},
           follow_redirects=True)
    with app.app_context():
        past_order = models.Order.query.filter_by(customer_name='QA Past Reminder').first()
    rep.check(past_order is not None and past_order.reminder_at is None,
              'a reminder time already in the past is dropped, order still placed')
    if past_order:
        made.append(past_order.id)

    # --- the background check itself, called the way the thread calls it --
    due_id = make_order(reminder_at=datetime.now() + timedelta(minutes=7))
    made.append(due_id)
    before = reminder_count()
    reminders.check_due_reminders(app)
    after = reminder_count()
    rep.check(after == before + 1,
              'an order 7 minutes out (inside the 10-minute lead) gets reminded',
              f'{before} -> {after}')
    rep.check(notified(due_id), 'and is marked notified so it is not repeated')

    with app.app_context():
        last = models.Notification.query.filter_by(type='order_reminder').order_by(
            models.Notification.id.desc()).first()
    rep.check(last and last.message.startswith('⏰ Nhắc hẹn đơn hàng'),
              'the reminder message carries the required text',
              last.message if last else '-')

    reminders.check_due_reminders(app)
    rep.check(reminder_count() == after,
              'running the check again does not send a second reminder for it')

    far_id = make_order(reminder_at=datetime.now() + timedelta(minutes=30))
    made.append(far_id)
    reminders.check_due_reminders(app)
    rep.check(notified(far_id) is False,
              'an order 30 minutes out is left alone - not due yet')

    stale_id = make_order(reminder_at=datetime.now() - timedelta(hours=5))
    made.append(stale_id)
    before_stale = reminder_count()
    reminders.check_due_reminders(app)
    rep.check(notified(stale_id) is True,
              'an order 5 hours overdue is marked handled')
    rep.check(reminder_count() == before_stale,
              'but a reminder for a time long past is not announced', 'no new row')

    # the poll endpoint the dashboard reads from
    r = a.get(f'/admin/api/reminders?since=0')
    data = r.get_json()
    rep.check(r.status_code == 200 and any('#%d' % due_id in x['message']
                                           for x in data['reminders']),
              'the reminders endpoint surfaces the fired reminder')

    for order_id in made:
        delete_order(order_id)
    with app.app_context():
        models.Notification.query.filter_by(type='order_reminder').delete()
        db.session.commit()

    return 1 if rep.summary() else 0


if __name__ == '__main__':
    sys.exit(main())
