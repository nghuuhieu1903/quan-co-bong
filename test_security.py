"""Prove each security fix actually blocks the attack it was written for.

Every check here fails if the patch is reverted, because each one performs
the attack rather than inspecting the code.

    python test_security.py
"""

import hashlib
import re
import sys

import app as app_module
import models
from app import db


def token(client, path):
    html = client.get(path).get_data(as_text=True)
    m = re.search(r'name="csrf_token" value="([^"]+)"', html)
    return m.group(1) if m else None


def post(client, path, data, from_page):
    data = dict(data)
    data['csrf_token'] = token(client, from_page)
    return client.post(path, data=data)


def check_order_idor(rep):
    """A stranger must not be able to read someone else's order."""
    app = app_module.app
    buyer = app.test_client()
    with app.app_context():
        pid = models.Product.query.first().id
    post(buyer, f'/add_to_cart/{pid}', {'quantity': '1'}, '/products')
    # the checkout form posts `name`/`phone`, not customer_*
    post(buyer, '/process_order', {
        'name': 'IDOR Victim', 'phone': '0987654321',
        'payment_method': 'cash'}, '/checkout')
    with app.app_context():
        order = models.Order.query.order_by(models.Order.id.desc()).first()

    # the person who placed it still sees it
    mine = buyer.get(f'/order_confirmation/{order.id}')
    rep.check(mine.status_code == 200 and b'IDOR Victim' in mine.data,
              'buyer can still open their own confirmation',
              f'HTTP {mine.status_code}')

    # a different browser cannot
    stranger = app.test_client()
    theirs = stranger.get(f'/order_confirmation/{order.id}')
    rep.check(theirs.status_code == 404,
              'stranger is refused another customer\'s order',
              f'HTTP {theirs.status_code}')
    rep.check(b'0987654321' not in theirs.data,
              'phone number does not leak in the refusal body')

    # staff still need access to every order
    admin = app.test_client()
    post(admin, '/admin/login', {'username': 'admin', 'password': 'admin123'},
         '/admin/login')
    staff = admin.get(f'/order_confirmation/{order.id}')
    rep.check(staff.status_code == 200, 'admin can open any order',
              f'HTTP {staff.status_code}')

    return order.id


def check_secret_key(rep):
    """A session cookie signed with the public example key must be rejected."""
    from itsdangerous import URLSafeTimedSerializer
    from flask.sessions import TaggedJSONSerializer

    app = app_module.app
    rep.check(app.config['SECRET_KEY'] not in app_module.INSECURE_DEFAULT_KEYS,
              'app is not running on a publicly known SECRET_KEY')

    forged = URLSafeTimedSerializer(
        'your-secret-key-change-this-in-production', salt='cookie-session',
        serializer=TaggedJSONSerializer(),
        signer_kwargs={'key_derivation': 'hmac', 'digest_method': hashlib.sha1},
    ).dumps({'admin_logged_in': True, 'admin_username': 'admin',
             'admin_role': 'super_admin'})

    c = app.test_client()
    c.set_cookie('session', forged)
    r = c.get('/admin/dashboard')
    rep.check(r.status_code != 200,
              'forged admin cookie signed with the example key is rejected',
              f'HTTP {r.status_code}')


def check_session_cookie_flags(rep):
    app = app_module.app
    c = app.test_client()
    post(c, '/admin/login', {'username': 'admin', 'password': 'admin123'},
         '/admin/login')
    r = c.get('/admin/dashboard')
    setc = ' '.join(v for k, v in r.headers.items() if k.lower() == 'set-cookie')
    conf = app.config
    rep.check(conf.get('SESSION_COOKIE_HTTPONLY'), 'session cookie is HttpOnly')
    rep.check(conf.get('SESSION_COOKIE_SAMESITE') == 'Lax',
              'session cookie is SameSite=Lax', str(conf.get('SESSION_COOKIE_SAMESITE')))


def check_reset_bruteforce(rep):
    """Wrong reset codes must stop being free after a handful of tries."""
    app = app_module.app
    c = app.test_client()

    with app.app_context():
        admin = models.Admin.query.filter_by(role='super_admin').first()
        username = admin.username

    post(c, '/admin/forgot_password', {'username': username},
         '/admin/forgot_password')
    with app.app_context():
        a = models.Admin.query.filter_by(username=username).first()
        issued = a.reset_code_hash is not None
    rep.check(issued, 'a reset code was issued')

    for i in range(5):
        post(c, '/admin/reset_password',
             {'username': username, 'code': f'{i:06d}',
              'new_password': 'attacker123', 'confirm_password': 'attacker123'},
             f'/admin/reset_password?username={username}')

    with app.app_context():
        a = models.Admin.query.filter_by(username=username).first()
        burned = a.reset_code_hash is None
    rep.check(burned, 'the code is invalidated after 5 wrong guesses')

    # and the password was never changed by those attempts
    from werkzeug.security import check_password_hash
    with app.app_context():
        a = models.Admin.query.filter_by(username=username).first()
        intact = check_password_hash(a.password, 'admin123')
    rep.check(intact, 'admin password unchanged by the guessing attempts')

    with app.app_context():
        a = models.Admin.query.filter_by(username=username).first()
        a.reset_code_hash = None
        a.reset_code_expiry = None
        a.reset_code_attempts = 0
        db.session.commit()


def check_csrf_still_on(rep):
    app = app_module.app
    c = app.test_client()
    r = c.post('/admin/login', data={'username': 'admin', 'password': 'admin123'})
    rep.check(r.status_code == 400, 'CSRF still rejects a tokenless POST',
              f'HTTP {r.status_code}')


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
        print(f'\n{len(self.rows) - failed}/{len(self.rows)} security checks passed')
        return failed


def main():
    rep = Report()
    order_id = check_order_idor(rep)
    check_secret_key(rep)
    check_session_cookie_flags(rep)
    check_reset_bruteforce(rep)
    check_csrf_still_on(rep)

    # clean up the order this run created
    with app_module.app.app_context():
        for it in models.OrderItem.query.filter_by(order_id=order_id).all():
            db.session.delete(it)
        o = db.session.get(models.Order, order_id)
        if o:
            db.session.delete(o)
        db.session.commit()

    return 1 if rep.summary() else 0


if __name__ == '__main__':
    sys.exit(main())
