"""Smoke test: GET every route and record the status code.

Unlike the other test_*.py scripts here, this one needs no running server -
it drives the app through Flask's test client.

    python test_smoke_routes.py --save     # record the current behaviour
    python test_smoke_routes.py            # compare against that recording

The saved baseline (smoke_baseline.json) is what makes a refactor safe: take
it before touching app.py, then re-run plain afterwards. Any route whose
status code moved is reported as a regression.
"""

import json
import os
import re
import sys

BASELINE_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                             'smoke_baseline.json')

# Routes with side effects we don't want a smoke test to trigger.
def short(endpoint):
    """Endpoint name without its blueprint prefix.

    The baseline was recorded before the routes moved into blueprints, when
    endpoints were bare function names. Comparing on the short name lets that
    recording stay valid across the move."""
    return endpoint.rsplit('.', 1)[-1]


SKIP = {'admin_logout', 'customer_logout', 'static',
        # flips room.available on every call - would mutate data each run
        'admin_toggle_room'}


def sample_values(app_module):
    """Real ids from the database, so <int:...> routes resolve to real rows."""
    import models
    with app_module.app.app_context():
        first = lambda model: (model.query.first().id
                               if model.query.first() else 1)
        return {
            'product_id': first(models.Product),
            'room_id': first(models.Room),
            'order_id': first(models.Order),
            'booking_id': first(models.RoomBooking),
            'item_id': first(models.DailyMenuItem),
            'image_id': first(models.ProductImage),
            'admin_id': first(models.Admin),
            'customer_id': first(models.Customer),
            'lang': 'vi',
        }


def build_url(rule, values):
    """Fill a rule's arguments from `values`; None if we can't supply one."""
    args = {}
    for arg in rule.arguments:
        if arg not in values:
            return None
        args[arg] = values[arg]
    try:
        return rule.rule if not args else _substitute(rule, args)
    except Exception:
        return None


def _substitute(rule, args):
    from werkzeug.routing import BuildError
    try:
        return rule.build(args, append_unknown=False)[1]
    except (BuildError, Exception):
        return None


def sign_in(client):
    """Log in as admin, carrying the CSRF token the login form hands out."""
    page = client.get('/admin/login').get_data(as_text=True)
    token = re.search(r'name="csrf_token" value="([^"]+)"', page)
    data = {'username': 'admin', 'password': 'admin123'}
    if token:
        data['csrf_token'] = token.group(1)
    return client.post('/admin/login', data=data)


def collect(app_module):
    """Map every GET route to the status code it returns.

    Each route is hit twice: once signed in as admin, and once anonymously.
    The anonymous pass is what exercises the access-control decorators - a
    protected page must redirect rather than render, and a broken redirect
    target only shows up when you are logged out.
    """
    values = sample_values(app_module)
    results = {}

    client = app_module.app.test_client()
    sign_in(client)
    anon = app_module.app.test_client()

    for rule in sorted(app_module.app.url_map.iter_rules(),
                       key=lambda r: r.endpoint):
        if short(rule.endpoint) in SKIP or 'GET' not in rule.methods:
            continue
        url = build_url(rule, values)
        if url is None:
            continue
        try:
            resp = client.get(url)
            results[short(rule.endpoint)] = resp.status_code
            results['anon:' + short(rule.endpoint)] = anon.get(url).status_code
            # How many sidebar entries mark themselves current. The sidebars
            # compare the view name against a list; when the routes moved into
            # blueprints those comparisons stopped matching and every page
            # quietly lost its highlight, which status codes cannot show.
            # Only HTML has a sidebar; the Excel export is binary and would
            # blow up on decode (and differ every run, since it embeds a time).
            if resp.status_code == 200 and resp.mimetype == 'text/html':
                body = resp.get_data(as_text=True)
                results['nav:' + short(rule.endpoint)] = len(
                    re.findall(r'class="sidebar-(?:sub)?link [^"]*active', body))
        except Exception as exc:
            results[short(rule.endpoint)] = f'EXCEPTION: {type(exc).__name__}: {exc}'
            results.pop('anon:' + short(rule.endpoint), None)
    return results


def main():
    import app as app_module

    results = collect(app_module)

    if '--save' in sys.argv:
        with open(BASELINE_PATH, 'w') as fh:
            json.dump(results, fh, indent=2, sort_keys=True)
        print(f'Saved baseline for {len(results)} routes -> {BASELINE_PATH}')
        for endpoint, status in sorted(results.items()):
            print(f'  {status}  {endpoint}')
        return 0

    if not os.path.exists(BASELINE_PATH):
        print('No baseline yet. Run with --save first.')
        return 1

    with open(BASELINE_PATH) as fh:
        baseline = json.load(fh)

    regressions = []
    for endpoint, was in sorted(baseline.items()):
        now = results.get(endpoint, 'MISSING ROUTE')
        if now != was:
            regressions.append(f'  {endpoint}: {was} -> {now}')
    for endpoint in sorted(set(results) - set(baseline)):
        print(f'  new route (not in baseline): {endpoint}')

    if regressions:
        print(f'REGRESSIONS ({len(regressions)}):')
        print('\n'.join(regressions))
        return 1

    print(f'OK - all {len(baseline)} routes match the baseline.')
    return 0


if __name__ == '__main__':
    sys.exit(main())
