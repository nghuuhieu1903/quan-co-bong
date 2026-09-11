"""Check the bank-transfer flow, especially what goes in the transfer content.

The rule under test: a customer who gave a name gets `NAME DHxx`, an
anonymous one gets `DHxx` alone. Both must always carry the order code,
because that is what the shop matches the payment against.

    python test_payments.py
"""

import os
import re
import sys
import urllib.parse

import app as app_module
import models
import payments
from app import db


class Order:
    """Just enough of a real order for the content/QR builders."""
    def __init__(self, id, customer_name, total_amount=45000):
        self.id = id
        self.customer_name = customer_name
        self.total_amount = total_amount


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
        print(f'\n{len(self.rows) - failed}/{len(self.rows)} payment checks passed')
        return failed


def check_transfer_content(rep):
    cases = [
        # (name stored on the order, expected content, why)
        ('Nguyễn Văn An', 'NGUYEN VAN AN DH7', 'named customer: name + code'),
        ('Guest Customer', 'DH7', 'the guest placeholder is not a name'),
        ('', 'DH7', 'empty name: code only'),
        (None, 'DH7', 'missing name: code only'),
        ('   ', 'DH7', 'whitespace-only name: code only'),
        ('Trần Thị Bích Đào', 'TRAN THI BICH DAO DH7', 'Đ folds to D'),
        ('Lê   Văn   B', 'LE VAN B DH7', 'runs of spaces collapse'),
        ('O\'Brien-Nguyễn', 'O BRIEN NGUYEN DH7', 'punctuation becomes a space'),
        ('!!!', 'DH7', 'name with nothing usable left: code only'),
    ]
    for name, expected, why in cases:
        got = payments.transfer_content(Order(7, name))
        rep.check(got == expected, f'{why}', f'{name!r} -> {got!r}')

    # the code must survive a very long name
    long_name = 'Nguyễn ' + 'Văn ' * 20 + 'Cuối'
    got = payments.transfer_content(Order(1234, long_name))
    rep.check(got.endswith('DH1234'), 'long name keeps the order code', got)
    rep.check(len(got) <= payments.MAX_ADD_INFO,
              'long content is trimmed to the bank limit', f'{len(got)} chars')

    # no diacritics may survive anywhere
    got = payments.transfer_content(Order(9, 'Đặng Thuỳ Dương'))
    rep.check(got.isascii(), 'content is pure ASCII', got)


def check_qr_url(rep):
    saved = {k: os.environ.get(k) for k in
             (payments.BANK_ID_ENV, payments.ACCOUNT_NO_ENV, payments.ACCOUNT_NAME_ENV)}
    try:
        # unconfigured: no QR, no bank option
        for k in saved:
            os.environ.pop(k, None)
        rep.check(payments.is_configured() is False,
                  'bank option is off when no account is configured')
        rep.check(payments.qr_image_url(Order(1, 'A')) is None,
                  'no QR is produced without an account')

        # configured
        os.environ[payments.BANK_ID_ENV] = '970436'
        os.environ[payments.ACCOUNT_NO_ENV] = '1234567890'
        os.environ[payments.ACCOUNT_NAME_ENV] = 'QUAN CO BONG'
        rep.check(payments.is_configured(), 'bank option turns on once configured')

        url = payments.qr_image_url(Order(42, 'Nguyễn Văn An', 123456))
        rep.check(url.startswith('https://img.vietqr.io/image/970436-1234567890-'),
                  'QR URL targets the configured account')

        q = urllib.parse.parse_qs(urllib.parse.urlparse(url).query)
        rep.check(q.get('amount') == ['123456'],
                  'QR carries the exact order total', str(q.get('amount')))
        rep.check(q.get('addInfo') == ['NGUYEN VAN AN DH42'],
                  'QR carries the transfer content', str(q.get('addInfo')))
        rep.check(q.get('accountName') == ['QUAN CO BONG'],
                  'QR carries the account name')

        # amount must never be a float like 45000.0 - banks reject it
        url = payments.qr_image_url(Order(1, 'A', 45000.0))
        q = urllib.parse.parse_qs(urllib.parse.urlparse(url).query)
        rep.check(q['amount'] == ['45000'], 'amount has no decimal part',
                  str(q['amount']))
    finally:
        for k, v in saved.items():
            if v is None:
                os.environ.pop(k, None)
            else:
                os.environ[k] = v


def token(client, path):
    html = client.get(path).get_data(as_text=True)
    m = re.search(r'name="csrf_token" value="([^"]+)"', html)
    return m.group(1) if m else None


def post(client, path, data, from_page):
    data = dict(data)
    data['csrf_token'] = token(client, from_page)
    return client.post(path, data=data)


def place_order(client, name, method, expect_order=True):
    app = app_module.app
    with app.app_context():
        pid = models.Product.query.first().id
    post(client, f'/add_to_cart/{pid}', {'quantity': '1'}, '/products')
    data = {'payment_method': method}
    if name:
        data['name'] = name
    r = post(client, '/process_order', data, '/checkout')
    if not expect_order:
        return r
    with app.app_context():
        return models.Order.query.order_by(models.Order.id.desc()).first().id


def check_end_to_end(rep, created):
    app = app_module.app
    saved = {k: os.environ.get(k) for k in
             (payments.BANK_ID_ENV, payments.ACCOUNT_NO_ENV, payments.ACCOUNT_NAME_ENV)}
    os.environ[payments.BANK_ID_ENV] = '970436'
    os.environ[payments.ACCOUNT_NO_ENV] = '1234567890'
    os.environ[payments.ACCOUNT_NAME_ENV] = 'QUAN CO BONG'
    try:
        # Customers no longer pick a method: every order is a transfer and
        # the confirmation shows the QR.
        c = app.test_client()
        with app.app_context():
            pid = models.Product.query.first().id
        post(c, f'/add_to_cart/{pid}', {'quantity': '1'}, '/products')
        html = c.get('/checkout').get_data(as_text=True)
        rep.check('name="payment_method"' not in html,
                  'checkout no longer asks how to pay')
        rep.check('pay-note' in html, 'checkout says the QR comes next')

        # a named order shows name + code
        c1 = app.test_client()
        oid = place_order(c1, 'Nguyễn Văn An', 'bank'); created.append(oid)
        page = c1.get(f'/order_confirmation/{oid}').get_data(as_text=True)
        rep.check('pay-panel' in page and 'img.vietqr.io' in page,
                  'named order shows a QR')
        rep.check(f'NGUYEN VAN AN DH{oid}' in page,
                  'named order prints name + code as the content')

        # A name is now required - there is no delivery, so it is the only
        # way the shop knows who a ready order belongs to. An order placed
        # with no name is refused, not silently filed under "Guest Customer".
        c2 = app.test_client()
        with app.app_context():
            before = models.Order.query.count()
        place_order(c2, None, 'bank', expect_order=False)
        with app.app_context():
            after = models.Order.query.count()
        rep.check(after == before, 'an order with no name is not created',
                  f'{before} -> {after}')
        rep.check('Vui lòng nhập tên' in c2.get('/checkout').get_data(as_text=True),
                  'and the customer is told why')

        # transfer_content()'s "code alone, no placeholder name" behaviour for
        # a blank/guest name is exercised directly in check_transfer_content()
        # above - it stays correct defensively even though this route can no
        # longer produce that order in practice.

        # even an order posted with payment_method=cash is stored as a
        # transfer and still gets its QR - the form no longer sends one, and
        # a hand-crafted post must not slip past
        c3 = app.test_client()
        oid3 = place_order(c3, 'Nguyễn Văn An', 'cash'); created.append(oid3)
        page = c3.get(f'/order_confirmation/{oid3}').get_data(as_text=True)
        rep.check('pay-panel' in page and 'img.vietqr.io' in page,
                  'every customer order shows a QR')
        with app.app_context():
            stored = db.session.get(models.Order, oid3).payment_method
        rep.check(stored == 'bank', 'the order is recorded as a transfer',
                  stored)

        with app.app_context():
            rep.check(db.session.get(models.Order, oid).payment_method == 'bank',
                      'the chosen payment method is stored')
    finally:
        for k, v in saved.items():
            if v is None:
                os.environ.pop(k, None)
            else:
                os.environ[k] = v


def check_hidden_when_unconfigured(rep, created):
    app = app_module.app
    saved = {k: os.environ.pop(k, None) for k in
             (payments.BANK_ID_ENV, payments.ACCOUNT_NO_ENV, payments.ACCOUNT_NAME_ENV)}
    try:
        c = app.test_client()
        with app.app_context():
            pid = models.Product.query.first().id
        post(c, f'/add_to_cart/{pid}', {'quantity': '1'}, '/products')
        html = c.get('/checkout').get_data(as_text=True)
        rep.check('value="bank"' not in html,
                  'QR option is hidden when no account is configured')
    finally:
        for k, v in saved.items():
            if v is not None:
                os.environ[k] = v


def check_saved_account(rep):
    """The account saved on the bank-QR screen drives the customer's QR."""
    import payments
    app = app_module.app

    def admin_client():
        c = app.test_client()
        tok = re.search(r'name="csrf_token" value="([^"]+)"',
                        c.get('/admin/login').get_data(as_text=True)).group(1)
        c.post('/admin/login', data={'username': 'admin', 'password': 'admin123',
                                     'csrf_token': tok})
        return c

    c = admin_client()
    page = c.get('/admin/generate_bank_qr').get_data(as_text=True)
    tok = re.search(r'name="csrf_token" value="([^"]+)"', page).group(1)
    c.post('/admin/generate_bank_qr', data={
        'csrf_token': tok, 'action': 'set_default', 'bank_id': 'tcb',
        'account_no': '1903 8888 6666', 'account_name': 'nguyen huu hieu'},
        follow_redirects=True)

    with app.app_context():
        cfg = payments.bank_config()
    rep.check(cfg and cfg['bank_id'] == 'TCB', 'the saved bank is used',
              cfg['bank_id'] if cfg else '-')
    rep.check(cfg and cfg['account_no'] == '190388886666',
              'spaces are stripped from the account number',
              cfg['account_no'] if cfg else '-')
    rep.check(cfg and cfg['account_name'] == 'NGUYEN HUU HIEU',
              'the account name is upper-cased for the bank')

    # An account number with letters in it must survive untouched. Stripping
    # every non-digit turned NP82502251356252VCB into 82502251356252, which is
    # a different account - the worst thing this screen can get wrong.
    page = c.get('/admin/generate_bank_qr').get_data(as_text=True)
    tok = re.search(r'name="csrf_token" value="([^"]+)"', page).group(1)
    c.post('/admin/generate_bank_qr', data={
        'csrf_token': tok, 'action': 'set_default', 'bank_id': 'VCB',
        'account_no': 'NP8250 2251-356252VCB', 'account_name': 'LUU THI NHU HOA'},
        follow_redirects=True)
    with app.app_context():
        cfg = payments.bank_config()
    rep.check(cfg and cfg['account_no'] == 'NP82502251356252VCB',
              'letters in an account number are kept, separators dropped',
              cfg['account_no'] if cfg else '-')

    # and the form must come back showing what is actually saved
    page = c.get('/admin/generate_bank_qr').get_data(as_text=True)
    shown = re.search(r'name="account_no"[^>]*value="([^"]*)"', page)
    rep.check(shown and shown.group(1) == 'NP82502251356252VCB',
              'the form reopens on the saved account, not a placeholder',
              shown.group(1) if shown else '-')
    picked = re.search(r'<option value="([A-Z]+)" selected>', page)
    rep.check(picked and picked.group(1) == 'VCB',
              'the bank list reopens on the saved bank',
              picked.group(1) if picked else '-')

    # put the test account back for the checks that follow
    page = c.get('/admin/generate_bank_qr').get_data(as_text=True)
    tok = re.search(r'name="csrf_token" value="([^"]+)"', page).group(1)
    c.post('/admin/generate_bank_qr', data={
        'csrf_token': tok, 'action': 'set_default', 'bank_id': 'TCB',
        'account_no': '1903 8888 6666', 'account_name': 'nguyen huu hieu'},
        follow_redirects=True)

    # it must reach a real customer's QR, not just the settings table
    cc = app.test_client()
    with app.app_context():
        pid = models.Product.query.first().id
    tok2 = lambda path: re.search(r'name="csrf_token" value="([^"]+)"',
                                  cc.get(path).get_data(as_text=True)).group(1)
    cc.post(f'/add_to_cart/{pid}', data={'quantity': '1', 'csrf_token': tok2('/products')})
    cc.post('/process_order', data={'name': 'Nguyễn Văn An', 'phone': '0912345678',
                                    'csrf_token': tok2('/cart')}, follow_redirects=True)
    with app.app_context():
        order = models.Order.query.order_by(models.Order.id.desc()).first()
    page = cc.get(f'/order_confirmation/{order.id}').get_data(as_text=True)
    rep.check('TCB-190388886666' in page,
              "the customer's QR collects into the saved account")
    rep.check(f'NGUYEN VAN AN DH{order.id}' in page,
              'the reference is still name plus order code')

    # only the super admin may move where the money goes
    with app.app_context():
        plain = models.Admin(username='qa_plain_admin', password='x', role='admin')
        db.session.add(plain)
        db.session.commit()
        plain_id = plain.id
    c2 = app.test_client()
    tok3 = re.search(r'name="csrf_token" value="([^"]+)"',
                     c2.get('/admin/login').get_data(as_text=True)).group(1)
    c2.post('/admin/login', data={'username': 'qa_plain_admin', 'password': 'x',
                                  'csrf_token': tok3})
    page = c2.get('/admin/generate_bank_qr').get_data(as_text=True)
    tok4 = re.search(r'name="csrf_token" value="([^"]+)"', page)
    if tok4:
        c2.post('/admin/generate_bank_qr', data={
            'csrf_token': tok4.group(1), 'action': 'set_default', 'bank_id': 'VCB',
            'account_no': '999999', 'account_name': 'KE GIAN'}, follow_redirects=True)
    with app.app_context():
        after = payments.bank_config()
    rep.check(after and after['account_no'] == '190388886666',
              'a plain admin cannot redirect the payments',
              after['account_no'] if after else '-')

    # clean up
    with app.app_context():
        for it in models.OrderItem.query.filter_by(order_id=order.id).all():
            prod = db.session.get(models.Product, it.product_id)
            if prod:
                prod.stock += it.quantity
            db.session.delete(it)
        db.session.delete(db.session.get(models.Order, order.id))
        row = db.session.get(models.Admin, plain_id)
        if row:
            db.session.delete(row)
        models.SiteSetting.query.filter(
            models.SiteSetting.key.in_(payments.SAVED_KEYS)).delete(
                synchronize_session=False)
        db.session.commit()


def main():
    rep = Report()
    created = []
    check_transfer_content(rep)
    check_qr_url(rep)
    check_end_to_end(rep, created)
    check_hidden_when_unconfigured(rep, created)
    check_saved_account(rep)

    with app_module.app.app_context():
        for oid in created:
            for it in models.OrderItem.query.filter_by(order_id=oid).all():
                # give the stock back, or repeated runs drain the shop
                product = db.session.get(models.Product, it.product_id)
                if product:
                    product.stock += it.quantity
                db.session.delete(it)
            o = db.session.get(models.Order, oid)
            if o:
                db.session.delete(o)
        db.session.commit()

    return 1 if rep.summary() else 0


if __name__ == '__main__':
    sys.exit(main())
