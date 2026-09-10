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


def place_order(client, name, method):
    app = app_module.app
    with app.app_context():
        pid = models.Product.query.first().id
    post(client, f'/add_to_cart/{pid}', {'quantity': '1'}, '/products')
    data = {'payment_method': method}
    if name:
        data['name'] = name
    post(client, '/process_order', data, '/checkout')
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
        # checkout offers the bank option when configured
        c = app.test_client()
        with app.app_context():
            pid = models.Product.query.first().id
        post(c, f'/add_to_cart/{pid}', {'quantity': '1'}, '/products')
        html = c.get('/checkout').get_data(as_text=True)
        rep.check('value="bank"' in html, 'checkout offers the QR option')
        rep.check('value="cash"' in html, 'checkout still offers cash')

        # a named order shows name + code
        c1 = app.test_client()
        oid = place_order(c1, 'Nguyễn Văn An', 'bank'); created.append(oid)
        page = c1.get(f'/order_confirmation/{oid}').get_data(as_text=True)
        rep.check('pay-panel' in page and 'img.vietqr.io' in page,
                  'named order shows a QR')
        rep.check(f'NGUYEN VAN AN DH{oid}' in page,
                  'named order prints name + code as the content')

        # an anonymous order shows the code alone
        c2 = app.test_client()
        oid2 = place_order(c2, None, 'bank'); created.append(oid2)
        page = c2.get(f'/order_confirmation/{oid2}').get_data(as_text=True)
        rep.check('pay-panel' in page and 'img.vietqr.io' in page,
                  'guest order shows a QR')
        rep.check(f'>DH{oid2}<' in page or f'DH{oid2}' in page,
                  'guest order prints the code')
        rep.check('GUEST CUSTOMER' not in page.upper().replace('GUEST CUSTOMER</', 'X'),
                  'guest order does not print a placeholder name in the content')

        # a cash order shows no QR at all
        c3 = app.test_client()
        oid3 = place_order(c3, 'Nguyễn Văn An', 'cash'); created.append(oid3)
        page = c3.get(f'/order_confirmation/{oid3}').get_data(as_text=True)
        rep.check('pay-panel' not in page and 'img.vietqr.io' not in page,
                  'cash order shows no QR')

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


def main():
    rep = Report()
    created = []
    check_transfer_content(rep)
    check_qr_url(rep)
    check_end_to_end(rep, created)
    check_hidden_when_unconfigured(rep, created)

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
