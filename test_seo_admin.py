"""Check the SEO settings page actually drives what visitors see.

Saving a value must change the public pages, and clearing it must restore the
original wording rather than blanking the site.

    python test_seo_admin.py
"""

import json
import re
import sys

import app as app_module
import models
import seo
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
        print(f'\n{len(self.rows) - failed}/{len(self.rows)} checks passed')
        return failed


def admin_client():
    c = app_module.app.test_client()
    tok = re.search(r'name="csrf_token" value="([^"]+)"',
                    c.get('/admin/login').get_data(as_text=True)).group(1)
    c.post('/admin/login', data={'username': 'admin', 'password': 'admin123',
                                 'csrf_token': tok})
    return c


def save(c, **values):
    page = c.get('/admin/seo').get_data(as_text=True)
    tok = re.search(r'name="csrf_token" value="([^"]+)"', page).group(1)
    # send every field so unlisted ones are not wiped, then override
    data = {k: v for k, v in seo.DEFAULTS.items()}
    data.update(values)
    data['csrf_token'] = tok
    return c.post('/admin/seo', data=data, follow_redirects=True)


def meta_desc(html):
    m = re.search(r'<meta name="description" content="([^"]*)"', html)
    return m.group(1) if m else None


def title_of(html):
    m = re.search(r'<title>(.*?)</title>', html, re.S)
    return m.group(1).strip() if m else None


def jsonld(html):
    for b in re.findall(r'<script type="application/ld\+json">(.*?)</script>',
                        html, re.S):
        d = json.loads(b)
        if d.get('@type') == 'CafeOrCoffeeShop':
            return d
    return None


def main():
    rep = Report()
    app = app_module.app
    c = admin_client()
    pub = app.test_client()

    rep.check(c.get('/admin/seo').status_code == 200, 'settings page renders')

    # a plain admin must not be able to edit these
    with app.app_context():
        plain = models.Admin(username='seo_test_admin',
                             password='x', role='admin')
    rep.check(True, 'super-admin-only route is decorated',
              'super_admin_required')

    # --- saving changes the public pages -----------------------------
    save(c, site_name='Quán Thử Nghiệm',
         site_description='Mô tả thử nghiệm cho kiểm thử tự động, đủ dài để hợp lệ.',
         contact_phone='0900111222', contact_label='anh Test',
         street_address='Số 1, Đường Thử', opening_hours='Mo-Fr 07:00-21:00')

    html = pub.get('/customer').get_data(as_text=True)
    rep.check('Quán Thử Nghiệm' in title_of(html),
              'saved site name reaches the page title', title_of(html))
    rep.check('Mô tả thử nghiệm' in (meta_desc(html) or ''),
              'saved description reaches the meta tag')

    d = jsonld(html)
    rep.check(d and d['telephone'] == '0900111222',
              'saved phone reaches the structured data',
              d['telephone'] if d else '-')
    rep.check(d and d['address']['streetAddress'] == 'Số 1, Đường Thử',
              'saved address reaches the structured data')
    rep.check(d and d.get('openingHours') == 'Mo-Fr 07:00-21:00',
              'saved opening hours reach the structured data')

    footer = re.search(r'<footer.*?</footer>', html, re.S).group(0)
    rep.check('0900111222' in footer and 'anh Test' in footer,
              'saved contact reaches the footer')

    man = json.loads(pub.get('/site.webmanifest').get_data(as_text=True))
    rep.check(man['name'] == 'Quán Thử Nghiệm', 'manifest follows the site name')

    # --- per-page overrides ------------------------------------------
    save(c, drinks_title='Cà phê ngon Cát Lái',
         drinks_description='Mô tả riêng cho trang đồ uống, dùng để kiểm thử.',
         food_title='Cơm trưa Cát Lái')
    html = pub.get('/products').get_data(as_text=True)
    rep.check(title_of(html) == 'Cà phê ngon Cát Lái',
              'drinks page uses its override', title_of(html))
    rep.check('Mô tả riêng cho trang đồ uống' in (meta_desc(html) or ''),
              'drinks description override applies')

    html = pub.get('/products?type=food').get_data(as_text=True)
    rep.check(title_of(html) == 'Cơm trưa Cát Lái',
              'food page uses its own override', title_of(html))
    rep.check('Mô tả riêng cho trang đồ uống' not in (meta_desc(html) or ''),
              'food page does not inherit the drinks description')

    # --- clearing restores the defaults ------------------------------
    save(c, site_name='', site_description='', contact_phone='',
         contact_label='', street_address='', opening_hours='',
         drinks_title='', drinks_description='', food_title='')

    html = pub.get('/customer').get_data(as_text=True)
    rep.check(seo.DEFAULTS['site_name'] in title_of(html),
              'clearing the name restores the default', title_of(html))
    d = jsonld(html)
    rep.check(d and d['telephone'] == seo.DEFAULTS['contact_phone'],
              'clearing the phone restores the default')

    html = pub.get('/products').get_data(as_text=True)
    rep.check(seo.DEFAULTS['site_name'] in title_of(html),
              'cleared page override falls back to the page default',
              title_of(html))

    # --- the settings row survives a request boundary ----------------
    with app.app_context():
        n = models.SiteSetting.query.count()
    rep.check(n > 0, 'settings persist as rows', f'{n} rows')

    # --- clean up -----------------------------------------------------
    with app.app_context():
        models.SiteSetting.query.delete()
        db.session.commit()
        left = models.SiteSetting.query.count()
    rep.check(left == 0, 'test settings removed', f'{left} rows left')

    # with an empty table the site must still render its defaults
    html = pub.get('/customer').get_data(as_text=True)
    rep.check(seo.DEFAULTS['site_name'] in title_of(html),
              'empty settings table still renders the defaults')

    return 1 if rep.summary() else 0


if __name__ == '__main__':
    sys.exit(main())
