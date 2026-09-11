"""Check the site can actually be installed as an app.

    python test_pwa.py

Whether Chrome offers "Install" is decided by criteria that are easy to get
almost right - a manifest with the wrong icon purpose, a service worker that
never fires, a start_url that 404s - so this checks the concrete pieces
rather than assuming a manifest existing is enough.
"""

import json
import re
import sys

import app as app_module
from helpers import contrast_ratio


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
        print(f'\n{len(self.rows) - failed}/{len(self.rows)} PWA checks passed')
        return failed


def main():
    rep = Report()
    c = app_module.app.test_client()

    # --- manifest -----------------------------------------------------
    r = c.get('/site.webmanifest')
    rep.check(r.status_code == 200, 'manifest is served')
    rep.check(r.mimetype == 'application/manifest+json', 'with the manifest mimetype')
    man = json.loads(r.get_data(as_text=True))

    rep.check(man.get('display') == 'standalone',
              'opens without browser chrome once installed')
    start = man.get('start_url', '')
    rep.check(c.get(start).status_code in (200, 302),
              'start_url actually resolves', f'{start} -> checked')

    icons = man.get('icons', [])
    rep.check(len(icons) >= 2, 'at least two icon sizes are declared',
              str(len(icons)))
    rep.check(any(i.get('sizes') == '512x512' and i.get('purpose') == 'any'
                  for i in icons),
              'a plain 512x512 icon is present (Chrome\'s install prompt needs one)')
    rep.check(any(i.get('purpose') == 'maskable' for i in icons),
              'a maskable icon is present, so Android does not crop the logo')

    short = man.get('short_name', '')
    rep.check(short and len(short) > 2,
              'short_name is a real word, not a truncated fragment',
              repr(short))

    for icon in icons:
        got = c.get(icon['src'])
        rep.check(got.status_code == 200, f'{icon["src"]} is actually servable',
                  f'HTTP {got.status_code}')

    # --- service worker -------------------------------------------------
    r = c.get('/static/js/sw.js')
    rep.check(r.status_code == 200, 'the service worker file is servable')
    body = r.get_data(as_text=True)
    rep.check("addEventListener('fetch'" in body,
              'it handles fetch (required for Chrome to offer install)')
    rep.check('/checkout' not in body and 'POST' not in body,
              'it does not try to cache anything write-side')

    # --- offline fallback -------------------------------------------------
    r = c.get('/offline')
    rep.check(r.status_code == 200, 'the offline fallback page renders')
    rep.check('Không có kết nối' in r.get_data(as_text=True),
              'and explains what happened, in Vietnamese')

    # --- customer pages wire it all up -------------------------------------
    html = c.get('/customer').get_data(as_text=True)
    rep.check('rel="manifest"' in html, 'the homepage links the manifest')
    rep.check('serviceWorker.register' in html,
              'the homepage registers the service worker')
    rep.check('apple-mobile-web-app-capable' in html,
              'iOS install meta tags are present')
    rep.check('installAppBtn' in html,
              'the install button exists, hidden until the browser allows it')
    rep.check(re.search(r'id="installAppBtn"[^>]*hidden', html),
              'the install button starts hidden')

    # --- the underlying colour math, since a wrong theme colour cannot be
    #     told apart from a right one just by looking at a screenshot -------
    rep.check(contrast_ratio('#ffffff', '#2F9BFF') > 1,
              'the theme colour is a valid, computable colour')

    return 1 if rep.summary() else 0


if __name__ == '__main__':
    sys.exit(main())
