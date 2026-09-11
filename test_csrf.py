"""Check that CSRF protection is on and that it did not break the forms.

Three things have to hold at once, and testing only one of them is how a
half-working setup slips through:

  1. a POST with no token is rejected,
  2. a POST with a valid token still goes through,
  3. every POST form the app renders actually carries a token - otherwise
     protection is on but the site is broken for real users.

    python test_csrf.py
"""

import re
import sys

import app as app_module


def login(client):
    page = client.get('/admin/login')
    token = extract_token(page.get_data(as_text=True))
    return client.post('/admin/login', data={
        'username': 'admin', 'password': 'admin123', 'csrf_token': token})


def extract_token(html):
    m = re.search(r'name="csrf_token" value="([^"]+)"', html)
    return m.group(1) if m else None


def check_rejects_without_token(results):
    """A write with no token must not be accepted."""
    client = app_module.app.test_client()
    resp = client.post('/admin/login',
                       data={'username': 'admin', 'password': 'admin123'})
    ok = resp.status_code == 400
    results.append((ok, f'POST without token is rejected '
                        f'(got {resp.status_code}, want 400)'))


def check_accepts_with_token(results):
    """The same write must still succeed once the token is included."""
    client = app_module.app.test_client()
    resp = login(client)
    ok = resp.status_code == 302 and '/admin/dashboard' in resp.headers.get('Location', '')
    results.append((ok, f'admin login with token succeeds '
                        f'(got {resp.status_code} -> '
                        f'{resp.headers.get("Location", "no redirect")})'))
    if ok:
        dash = client.get('/admin/dashboard')
        results.append((dash.status_code == 200,
                        f'dashboard reachable after login (got {dash.status_code})'))


# Pages worth rendering: each has at least one POST form. Anything that only
# renders for a specific record uses the ids seeded in the dev database.
PAGES = [
    '/', '/products', '/cart', '/checkout', '/customer/login',
    '/customer/register', '/customer/daily-menu',
    '/admin/login', '/admin/dashboard', '/admin/manage_products',
    '/admin/product/add', '/admin/rooms', '/admin/room/add',
    '/admin/room_bookings', '/admin/debts', '/admin/generate_qr',
    '/admin/generate_bank_qr',
    '/admin/accounts', '/admin/change_password', '/admin/forgot_password',
    '/admin/reset_password',
    '/product/{product_id}', '/room/{room_id}', '/order_confirmation/{order_id}',
    '/admin/product/{product_id}/edit', '/admin/room/{room_id}/edit',
]


def resolve_pages():
    """Fill the {id} placeholders from rows that actually exist."""
    import models
    with app_module.app.app_context():
        first = lambda M: (M.query.first().id if M.query.first() else 1)
        ids = {'product_id': first(models.Product),
               'room_id': first(models.Room),
               'order_id': first(models.Order)}
    return [p.format(**ids) for p in PAGES]


def check_rendered_forms_have_tokens(results):
    """Every POST form on every reachable page must carry a token."""
    client = app_module.app.test_client()
    login(client)

    total_forms = missing = 0
    bad_pages = []
    for path in resolve_pages():
        resp = client.get(path)
        if resp.status_code != 200:
            continue
        html = resp.get_data(as_text=True)
        for m in re.finditer(r'<form\b[^>]*>(.*?)</form>', html, re.I | re.S):
            if not re.search(r'method\s*=\s*["\']?post', m.group(0), re.I):
                continue
            total_forms += 1
            if 'name="csrf_token"' not in m.group(1):
                missing += 1
                bad_pages.append(path)

    results.append((missing == 0,
                    f'{total_forms} rendered POST forms carry a token, '
                    f'{missing} missing'
                    + (f' -> {sorted(set(bad_pages))}' if bad_pages else '')))
    results.append((total_forms > 0,
                    f'actually found POST forms to check ({total_forms})'))


def check_meta_tag(results):
    """The fetch() callers read the token out of a meta tag."""
    client = app_module.app.test_client()
    login(client)
    for path in ('/products', '/admin/dashboard'):
        html = client.get(path).get_data(as_text=True)
        ok = re.search(r'<meta name="csrf-token" content="[^"]+"', html) is not None
        results.append((ok, f'{path} exposes the csrf-token meta tag'))


def main():
    results = []
    check_rejects_without_token(results)
    check_accepts_with_token(results)
    check_rendered_forms_have_tokens(results)
    check_meta_tag(results)

    failed = 0
    for ok, message in results:
        print(f'  {"PASS" if ok else "FAIL"}  {message}')
        failed += not ok

    print(f'\n{len(results) - failed}/{len(results)} checks passed')
    return 1 if failed else 0


if __name__ == '__main__':
    sys.exit(main())
