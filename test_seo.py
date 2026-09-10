"""Check the SEO metadata is actually present and well-formed.

Parses what the app renders rather than what the templates say, so a broken
Jinja block or an escaped tag shows up as a failure.

    python test_seo.py
"""

import json
import re
import sys
import xml.etree.ElementTree as ET

import app as app_module
import models
import seo


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
        print(f'\n{len(self.rows) - failed}/{len(self.rows)} SEO checks passed')
        return failed


def meta(html, **attrs):
    """Find a <meta> tag's content by any attribute pair."""
    key, val = next(iter(attrs.items()))
    m = re.search(rf'<meta[^>]+{key}="{re.escape(val)}"[^>]*content="([^"]*)"', html)
    if not m:
        m = re.search(rf'<meta[^>]+content="([^"]*)"[^>]*{key}="{re.escape(val)}"', html)
    return m.group(1) if m else None


def link_href(html, rel):
    m = re.search(rf'<link[^>]+rel="{rel}"[^>]*href="([^"]*)"', html)
    return m.group(1) if m else None


PUBLIC_PAGES = ['/customer', '/products', '/products?type=food', '/rooms',
                '/product/1', '/room/1']
PRIVATE_PAGES = ['/cart', '/customer/login', '/customer/register']


def check_meta(rep, c):
    for path in PUBLIC_PAGES:
        html = c.get(path).get_data(as_text=True)
        d = meta(html, name='description')
        rep.check(d and len(d) >= 50,
                  f'{path} has a usable meta description',
                  f'{len(d) if d else 0} chars')
        rep.check(link_href(html, 'canonical', ) and
                  link_href(html, 'canonical').startswith('http'),
                  f'{path} has an absolute canonical URL',
                  str(link_href(html, 'canonical')))
        rep.check(meta(html, property='og:title') and meta(html, property='og:image'),
                  f'{path} has Open Graph title + image')
        rep.check((meta(html, name='robots') or '').startswith('index'),
                  f'{path} is indexable', meta(html, name='robots'))

    # descriptions must differ per page, or they are worthless
    descs = {p: meta(c.get(p).get_data(as_text=True), name='description')
             for p in PUBLIC_PAGES}
    rep.check(len(set(descs.values())) == len(descs),
              'every public page has a distinct description',
              f'{len(set(descs.values()))} unique of {len(descs)}')


def check_noindex(rep, c):
    for path in PRIVATE_PAGES:
        html = c.get(path).get_data(as_text=True)
        rep.check('noindex' in (meta(html, name='robots') or ''),
                  f'{path} is noindex', meta(html, name='robots'))

    admin = app_module.app.test_client()
    tok = re.search(r'name="csrf_token" value="([^"]+)"',
                    admin.get('/admin/login').get_data(as_text=True)).group(1)
    admin.post('/admin/login', data={'username': 'admin', 'password': 'admin123',
                                     'csrf_token': tok})
    html = admin.get('/admin/dashboard').get_data(as_text=True)
    rep.check('noindex' in (meta(html, name='robots') or ''),
              '/admin/dashboard is noindex', meta(html, name='robots'))


def check_robots_and_sitemap(rep, c):
    r = c.get('/robots.txt')
    body = r.get_data(as_text=True)
    rep.check(r.status_code == 200 and r.mimetype == 'text/plain',
              'robots.txt serves as text/plain', f'HTTP {r.status_code}')
    rep.check('Disallow: /admin' in body, 'robots.txt keeps crawlers off /admin')
    rep.check('Sitemap:' in body and 'sitemap.xml' in body,
              'robots.txt points at the sitemap')

    r = c.get('/sitemap.xml')
    rep.check(r.status_code == 200, 'sitemap.xml responds', f'HTTP {r.status_code}')
    try:
        root = ET.fromstring(r.get_data())
        ns = '{http://www.sitemaps.org/schemas/sitemap/0.9}'
        locs = [e.text for e in root.iter(f'{ns}loc')]
        rep.check(True, 'sitemap.xml is valid XML', f'{len(locs)} URLs')
    except ET.ParseError as e:
        rep.check(False, 'sitemap.xml is valid XML', str(e))
        return

    rep.check(all(u.startswith('http') for u in locs),
              'every sitemap URL is absolute')
    with app_module.app.app_context():
        n_products = models.Product.query.count()
        n_rooms = models.Room.query.filter_by(available=True).count()
    rep.check(sum('/product/' in u for u in locs) == n_products,
              'sitemap lists every product',
              f'{sum("/product/" in u for u in locs)} of {n_products}')
    rep.check(sum('/room/' in u for u in locs) == n_rooms,
              'sitemap lists every available room',
              f'{sum("/room/" in u for u in locs)} of {n_rooms}')
    rep.check(not any('/admin' in u or '/cart' in u for u in locs),
              'sitemap excludes private pages')


def check_icons(rep, c):
    html = c.get('/customer').get_data(as_text=True)
    for rel, label in [('icon', 'favicon'), ('apple-touch-icon', 'apple touch icon'),
                       ('manifest', 'web manifest')]:
        href = link_href(html, rel)
        rep.check(href is not None, f'page links a {label}')
        if href:
            rep.check(c.get(href).status_code == 200,
                      f'{label} file is served', href)

    r = c.get('/site.webmanifest')
    rep.check(r.status_code == 200, 'site.webmanifest responds')
    try:
        data = json.loads(r.get_data(as_text=True))
        rep.check(data.get('name') and len(data.get('icons', [])) >= 2,
                  'manifest names the site and lists icons')
    except ValueError as e:
        rep.check(False, 'manifest is valid JSON', str(e))


def check_structured_data(rep, c):
    html = c.get('/customer').get_data(as_text=True)
    blocks = re.findall(r'<script type="application/ld\+json">(.*?)</script>',
                        html, re.S)
    rep.check(blocks, 'home page carries structured data')
    for b in blocks:
        try:
            data = json.loads(b)
        except ValueError as e:
            rep.check(False, 'structured data is valid JSON', str(e)[:60])
            continue
        rep.check(data.get('@type') == 'CafeOrCoffeeShop',
                  'business is described as a coffee shop', data.get('@type'))

    html = c.get('/product/1').get_data(as_text=True)
    blocks = re.findall(r'<script type="application/ld\+json">(.*?)</script>',
                        html, re.S)
    types = []
    for b in blocks:
        try:
            types.append(json.loads(b).get('@type'))
        except ValueError as e:
            rep.check(False, 'product structured data is valid JSON', str(e)[:60])
    rep.check('Product' in types, 'product page adds Product schema', str(types))
    if 'Product' in types:
        prod = next(json.loads(b) for b in blocks
                    if json.loads(b).get('@type') == 'Product')
        offer = prod.get('offers', {})
        rep.check(offer.get('priceCurrency') == 'VND' and offer.get('price'),
                  'Product schema carries price in VND',
                  f'{offer.get("price")} {offer.get("priceCurrency")}')


def main():
    rep = Report()
    c = app_module.app.test_client()
    print(f'  (canonical origin: {seo.site_url()})\n')
    check_meta(rep, c)
    check_noindex(rep, c)
    check_robots_and_sitemap(rep, c)
    check_icons(rep, c)
    check_structured_data(rep, c)
    return 1 if rep.summary() else 0


if __name__ == '__main__':
    sys.exit(main())
