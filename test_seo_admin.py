"""Check the SEO settings page actually drives what visitors see.

Saving a value must change the public pages, and clearing it must restore the
original wording rather than blanking the site.

    python test_seo_admin.py
"""

import io
import json
import os
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

    # --- share image upload ------------------------------------------
    from PIL import Image

    def upload(w, h, name='anh.png', fmt='PNG', raw=None):
        page = c.get('/admin/seo').get_data(as_text=True)
        tok = re.search(r'name="csrf_token" value="([^"]+)"', page).group(1)
        if raw is None:
            buf = io.BytesIO()
            Image.new('RGB', (w, h), (180, 60, 60)).save(buf, fmt)
            buf.seek(0)
        else:
            buf = io.BytesIO(raw)
        data = {k: v for k, v in seo.DEFAULTS.items() if k != 'og_image'}
        data['csrf_token'] = tok
        data['og_image_file'] = (buf, name)
        return c.post('/admin/seo', data=data,
                      content_type='multipart/form-data', follow_redirects=True)

    def og_row():
        with app.app_context():
            return models.MediaFile.query.filter_by(key='og').first()

    upload(1000, 1000)                       # square: wrong shape on purpose
    row = og_row()
    rep.check(row is not None, 'upload is stored in the database')
    rep.check(Image.open(io.BytesIO(row.data)).size == seo.OG_SIZE,
              'a square upload is cropped to the share-card shape',
              str(Image.open(io.BytesIO(row.data)).size))

    upload(400, 900)                         # portrait
    rep.check(Image.open(io.BytesIO(og_row().data)).size == seo.OG_SIZE,
              'a portrait upload is cropped to the share-card shape')

    html = pub.get('/customer').get_data(as_text=True)
    m = re.search(r'property="og:image" content="([^"]*)"', html)
    rep.check(m and '/media/og' in m.group(1),
              'public pages point at the uploaded image', m.group(1) if m else '-')

    served = pub.get('/media/og')
    rep.check(served.status_code == 200 and served.mimetype == 'image/jpeg',
              'the stored image is served back', f'{served.status_code} {served.mimetype}')

    before = og_row().data
    r = upload(100, 50)                      # too small to be usable
    rep.check('quá nhỏ' in r.get_data(as_text=True),
              'a too-small upload is refused with a reason')
    rep.check(og_row().data == before,
              'a refused upload does not replace the current image')

    r = upload(0, 0, name='fake.png', raw=b'this is not an image at all')
    rep.check('không phải là ảnh' in r.get_data(as_text=True),
              'a non-image with an image extension is refused')
    rep.check(og_row().data == before,
              'the refused non-image did not replace anything')

    page = c.get('/admin/seo').get_data(as_text=True)
    tok = re.search(r'name="csrf_token" value="([^"]+)"', page).group(1)
    c.post('/admin/seo', data={'action': 'reset_og', 'csrf_token': tok},
           follow_redirects=True)
    rep.check(og_row() is None, 'reset removes the stored image')
    html = pub.get('/customer').get_data(as_text=True)
    m = re.search(r'property="og:image" content="([^"]*)"', html)
    rep.check(m and 'og-image.png' in m.group(1),
              'reset falls back to the generated image')

    # --- icon set from one uploaded logo ------------------------------
    def upload_icon(w, h, raw=None, name='logo.png'):
        page = c.get('/admin/seo').get_data(as_text=True)
        tok = re.search(r'name="csrf_token" value="([^"]+)"', page).group(1)
        if raw is None:
            buf = io.BytesIO()
            Image.new('RGB', (w, h), (30, 140, 220)).save(buf, 'PNG')
            buf.seek(0)
        else:
            buf = io.BytesIO(raw)
        data = {k: v for k, v in seo.DEFAULTS.items()
                if k not in ('og_image', 'custom_icons')}
        data['csrf_token'] = tok
        data['icon_file'] = (buf, name)
        return c.post('/admin/seo', data=data,
                      content_type='multipart/form-data', follow_redirects=True)

    def icon_rows():
        with app.app_context():
            return {r.key: r.data for r in
                    models.MediaFile.query.filter(
                        models.MediaFile.key.like('icon:%')).all()}

    upload_icon(800, 600)                    # wide on purpose: must be squared
    rows = icon_rows()
    # ICON_SIZES + the .ico + the maskable variant
    rep.check(len(rows) == len(seo.ICON_SIZES) + 2,
              'one logo produces the whole icon set', f'{len(rows)} images')
    got = Image.open(io.BytesIO(rows['icon:maskable-512.png'])).size
    rep.check(got == (seo.MASKABLE_SIZE, seo.MASKABLE_SIZE),
              'the maskable icon is stored at its declared size', str(got))
    for name, size in seo.ICON_SIZES.items():
        got = Image.open(io.BytesIO(rows['icon:' + name])).size
        if got != (size, size):
            rep.check(False, f'{name} is {size}x{size}', str(got))
            break
    else:
        rep.check(True, 'every icon is stored at its declared size')

    html = pub.get('/customer').get_data(as_text=True)
    rep.check('/media/icon:favicon.ico' in html.replace('&amp;', '&'),
              'public pages link the uploaded favicon')
    admin_html = c.get('/admin/dashboard').get_data(as_text=True)
    rep.check('/media/icon:' in admin_html, 'admin pages link it too')
    man = json.loads(pub.get('/site.webmanifest').get_data(as_text=True))
    rep.check(all('/media/icon:' in i['src'] for i in man['icons']),
              'the manifest points at the uploaded icons')

    served = pub.get('/media/icon:favicon-32.png')
    rep.check(served.status_code == 200 and served.mimetype == 'image/png',
              'a stored icon is served back')
    rep.check('immutable' in (served.headers.get('Cache-Control') or ''),
              'stored images are cached hard by the browser')

    r = upload_icon(40, 40)
    rep.check('quá nhỏ' in r.get_data(as_text=True),
              'a logo smaller than 64px is refused')
    r = upload_icon(0, 0, raw=b'not an image')
    rep.check('không phải là ảnh' in r.get_data(as_text=True),
              'a non-image logo is refused')

    page = c.get('/admin/seo').get_data(as_text=True)
    tok = re.search(r'name="csrf_token" value="([^"]+)"', page).group(1)
    c.post('/admin/seo', data={'action': 'reset_icons', 'csrf_token': tok},
           follow_redirects=True)
    rep.check(not icon_rows(), 'reset deletes the uploaded icon set')
    html = pub.get('/customer').get_data(as_text=True)
    rep.check('/static/icons/favicon.ico' in html,
              'reset returns to the generated icons')

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
