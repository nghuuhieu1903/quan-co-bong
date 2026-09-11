"""Bank-transfer payment: the shop's account, and the QR shown to a customer.

The QR image comes from VietQR, the same service the admin QR generator
already uses. The account is whatever the shop saved on the bank-QR screen,
falling back to the environment when nothing has been saved.

Note the trade-off that came with making it editable: a stolen super-admin
session can now point customer payments at another account. Saving is
therefore limited to the super admin, and the change is worth knowing about
if the account ever looks wrong.

If the account is not configured the bank option simply does not appear at
checkout, and cash remains the only method. That is deliberate: showing a
customer a QR that pays nobody is worse than not offering the option.
"""

import logging
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
logger = logging.getLogger(__name__)

# Banks reject long descriptions
MAX_ADD_INFO = 50

# The fallback name process_order stores when nobody filled the name in.
GUEST_NAME = 'Guest Customer'


# Saved from the bank-QR screen; these keys live in the settings table.
SAVED_KEYS = ('shop_bank_id', 'shop_bank_account_no', 'shop_bank_account_name')


def saved_config():
    """What the shop saved on the bank-QR screen, or an empty dict."""
    try:
        from extensions import db
        from models import SiteSetting
        rows = {r.key: (r.value or '').strip()
                for r in SiteSetting.query.filter(
                    SiteSetting.key.in_(SAVED_KEYS)).all()}
    except Exception:
        # before the table exists, or outside an app context
        logger.exception('Could not read the saved bank account')
        return {}
    return {k: v for k, v in rows.items() if v}


def save_config(bank_id, account_no, account_name):
    """Store the account the whole site should collect into."""
    from extensions import db
    from models import SiteSetting

    values = {
        'shop_bank_id': (bank_id or '').strip().upper(),
        # Only separators come out. Stripping every non-digit looked safe
        # until an account with letters in it silently became a different
        # account - and a QR pointing at an account that is not yours is the
        # worst thing this screen can produce.
        'shop_bank_account_no': re.sub(r'[\s.\-]', '', (account_no or '')).upper(),
        'shop_bank_account_name': (account_name or '').strip().upper(),
    }
    if not (values['shop_bank_id'] and values['shop_bank_account_no']):
        return False

    for key, value in values.items():
        row = db.session.get(SiteSetting, key)
        if row is None:
            db.session.add(SiteSetting(key=key, value=value))
        else:
            row.value = value
    db.session.commit()
    return True


def bank_config():
    """The shop's account, or None when it has not been set up.

    What was saved in the admin wins; the environment is the fallback, so an
    existing .env deployment keeps working untouched.
    """
    saved = saved_config()
    bank_id = saved.get('shop_bank_id') or (os.environ.get(BANK_ID_ENV) or '').strip()
    account_no = (saved.get('shop_bank_account_no')
                  or (os.environ.get(ACCOUNT_NO_ENV) or '').strip())
    account_name = (saved.get('shop_bank_account_name')
                    or (os.environ.get(ACCOUNT_NAME_ENV) or '').strip())
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
