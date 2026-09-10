"""Bank-transfer payment: the shop's account, and the QR shown to a customer.

The QR image comes from VietQR, the same service the admin QR generator
already uses. The account details are read from the environment rather than
stored in the database, so changing them is a .env edit and a restart - and
so an admin session can never be used to redirect payments to another
account.

If the account is not configured the bank option simply does not appear at
checkout, and cash remains the only method. That is deliberate: showing a
customer a QR that pays nobody is worse than not offering the option.
"""

import os
import re
import unicodedata
import urllib.parse

BANK_ID_ENV = 'SHOP_BANK_ID'
ACCOUNT_NO_ENV = 'SHOP_BANK_ACCOUNT_NO'
ACCOUNT_NAME_ENV = 'SHOP_BANK_ACCOUNT_NAME'

# VietQR renders this style; "compact2" includes the amount and content
# printed under the code, which is what a customer needs to check.
QR_TEMPLATE = 'compact2'

# Banks reject or mangle long descriptions, and most Vietnamese banking apps
# will not accept diacritics in the transfer content at all.
MAX_ADD_INFO = 50

# The fallback name process_order stores when nobody filled the name in.
GUEST_NAME = 'Guest Customer'


def bank_config():
    """The shop's account, or None when it has not been set up."""
    bank_id = (os.environ.get(BANK_ID_ENV) or '').strip()
    account_no = (os.environ.get(ACCOUNT_NO_ENV) or '').strip()
    account_name = (os.environ.get(ACCOUNT_NAME_ENV) or '').strip()
    if not (bank_id and account_no):
        return None
    return {
        'bank_id': bank_id,
        'account_no': account_no,
        'account_name': account_name,
    }


def is_configured():
    return bank_config() is not None


def order_code(order_id):
    """Short, unambiguous reference a customer can quote: DH12."""
    return f'DH{order_id}'


def strip_diacritics(text):
    """`Nguyễn Văn Á` -> `Nguyen Van A`.

    Vietnamese banking apps commonly drop or garble accented characters in
    the transfer description, which would leave the shop unable to match a
    payment to an order. Folding them here keeps the reference readable.
    """
    text = text.replace('Đ', 'D').replace('đ', 'd')
    decomposed = unicodedata.normalize('NFD', text)
    return ''.join(c for c in decomposed if not unicodedata.combining(c))


def transfer_content(order):
    """What the customer's banking app puts in the transfer description.

    A named customer gets their name in front of the order code, so the shop
    can recognise a payment even before opening the order. An anonymous
    checkout has no name worth printing, so the code stands alone - the code
    is what actually identifies the order either way.
    """
    code = order_code(order.id)
    name = (order.customer_name or '').strip()

    if not name or name == GUEST_NAME:
        return code

    name = strip_diacritics(name)
    name = re.sub(r'[^A-Za-z0-9 ]+', ' ', name)
    name = re.sub(r'\s+', ' ', name).strip().upper()
    if not name:
        return code

    content = f'{name} {code}'
    if len(content) > MAX_ADD_INFO:
        # keep the code - it is the part that identifies the payment
        keep = MAX_ADD_INFO - len(code) - 1
        content = f'{name[:max(keep, 0)].strip()} {code}'.strip()
    return content


def qr_image_url(order):
    """The VietQR image for this order, or None if no account is configured."""
    cfg = bank_config()
    if cfg is None:
        return None

    params = {
        'amount': f'{order.total_amount:.0f}',
        'addInfo': transfer_content(order),
    }
    if cfg['account_name']:
        params['accountName'] = cfg['account_name']

    return (f"https://img.vietqr.io/image/"
            f"{cfg['bank_id']}-{cfg['account_no']}-{QR_TEMPLATE}.png"
            f"?{urllib.parse.urlencode(params)}")


def payment_details(order):
    """Everything the confirmation page needs to render the transfer panel."""
    cfg = bank_config()
    if cfg is None:
        return None
    return {
        'bank_id': cfg['bank_id'],
        'account_no': cfg['account_no'],
        'account_name': cfg['account_name'],
        'amount': order.total_amount,
        'content': transfer_content(order),
        'qr_url': qr_image_url(order),
    }
