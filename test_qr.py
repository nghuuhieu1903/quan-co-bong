"""Check the QR generator produces codes a phone can actually scan.

The generated image is decoded back, and the colour pair is measured, because
a picture that looks like a QR is not the same as a QR that scans.

    python test_qr.py
"""

import base64
import io
import re
import sys

import app as app_module
from helpers import check_qr_colours, contrast_ratio

try:
    import zxingcpp
except ImportError:                      # pragma: no cover - optional
    zxingcpp = None

from PIL import Image


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
        print(f'\n{len(self.rows) - failed}/{len(self.rows)} QR checks passed')
        return failed


def admin_client():
    c = app_module.app.test_client()
    tok = re.search(r'name="csrf_token" value="([^"]+)"',
                    c.get('/admin/login').get_data(as_text=True)).group(1)
    c.post('/admin/login', data={'username': 'admin', 'password': 'admin123',
                                 'csrf_token': tok})
    return c


def token(c, path='/admin/generate_qr'):
    return re.search(r'name="csrf_token" value="([^"]+)"',
                     c.get(path).get_data(as_text=True)).group(1)


def image_of(html):
    m = re.search(r'data:image/png;base64,([A-Za-z0-9+/=]+)', html)
    if not m:
        return None
    return Image.open(io.BytesIO(base64.b64decode(m.group(1)))).convert('RGB')


def main():
    rep = Report()
    c = admin_client()

    # --- the colour rule, measured rather than eyeballed -----------------
    rep.check(contrast_ratio('#ffffff', '#000000') > 20,
              'black on white measures as maximum contrast',
              f"{contrast_ratio('#ffffff', '#000000'):.1f}:1")
    rep.check(check_qr_colours('#ffffff', '#000000') is None,
              'black on white is allowed')
    rep.check(check_qr_colours('#000000', '#ffffff') is not None,
              'an inverted code is refused')
    rep.check(check_qr_colours('#ffffff', '#ffff00') is not None,
              'yellow on white is refused',
              f"{contrast_ratio('#ffffff', '#ffff00'):.1f}:1")
    rep.check(check_qr_colours('#ffffff', '#cccccc') is not None,
              'light grey on white is refused')
    rep.check(check_qr_colours('nonsense', '#000000') is not None,
              'a malformed colour is refused, not crashed on')

    # --- the page itself --------------------------------------------------
    html = c.get('/admin/generate_qr').get_data(as_text=True)
    img = image_of(html)
    rep.check(img is not None, 'the page renders a code on first load')

    corner = img.getpixel((2, 2))
    rep.check(sum(corner) > 600,
              'the default code is dark-on-light, not inverted', str(corner))
    rep.check('localhost' not in html,
              'nothing on the page still points at localhost')

    # --- a refused pair must not produce an image -------------------------
    r = c.post('/admin/generate_qr',
               data={'csrf_token': token(c), 'url': 'https://calaci.com.vn',
                     'size': '10', 'border': '4',
                     'bg_color': '#ffffff', 'fg_color': '#ffff00'},
               follow_redirects=True)
    body = r.get_data(as_text=True)
    rep.check('tương phản' in body, 'a low-contrast request is refused with a reason')

    # --- an allowed pair round-trips --------------------------------------
    r = c.post('/admin/generate_qr',
               data={'csrf_token': token(c), 'url': 'https://calaci.com.vn/products',
                     'size': '10', 'border': '4',
                     'bg_color': '#ffffff', 'fg_color': '#1a4d8f'})
    img = image_of(r.get_data(as_text=True))
    rep.check(img is not None, 'a dark colour on white is accepted')
    if img:
        colours = {c for _, c in img.getcolors(maxcolors=100000)}
        rep.check((26, 77, 143) in colours, 'the chosen colour is the one drawn',
                  str(sorted(colours)[:2]))

    if zxingcpp is None:
        rep.check(True, 'decoder not installed - skipping the read-back check',
                  'pip install zxing-cpp')
    else:
        for label, fg in (('black', '#000000'), ('dark blue', '#1a4d8f')):
            r = c.post('/admin/generate_qr',
                       data={'csrf_token': token(c), 'url': 'https://calaci.com.vn/cart',
                             'size': '10', 'border': '4',
                             'bg_color': '#ffffff', 'fg_color': fg})
            got = zxingcpp.read_barcode(image_of(r.get_data(as_text=True)))
            rep.check(got and got.text == 'https://calaci.com.vn/cart',
                      f'a {label} code reads back as the URL that went in',
                      got.text if got else 'unreadable')

    # --- the quiet zone the standard asks for -----------------------------
    r = c.post('/admin/generate_qr',
               data={'csrf_token': token(c), 'url': 'https://calaci.com.vn',
                     'size': '10', 'border': '0',
                     'bg_color': '#ffffff', 'fg_color': '#000000'})
    img = image_of(r.get_data(as_text=True))
    # with border 0 the code would start at pixel 0; 4 modules of 10px means
    # the first 40 pixels along the top edge are all background
    edge = [img.getpixel((x, 0)) for x in range(40)] if img else []
    rep.check(img is not None and all(px == (255, 255, 255) for px in edge),
              'a border of 0 is raised to the standard quiet zone',
              str(edge[:2]))

    # --- a hand-edited size must not blow the page up ---------------------
    r = c.post('/admin/generate_qr',
               data={'csrf_token': token(c), 'url': 'https://calaci.com.vn',
                     'size': '9999', 'border': '-5',
                     'bg_color': '#ffffff', 'fg_color': '#000000'})
    rep.check(r.status_code == 200, 'absurd size and border are clamped, not fatal',
              f'HTTP {r.status_code}')

    return 1 if rep.summary() else 0


if __name__ == '__main__':
    sys.exit(main())
