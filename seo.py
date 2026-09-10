"""Search-engine and social-sharing metadata.

Three things live here:

  * `robots.txt` and `sitemap.xml`, generated from the database so new
    products and rooms appear without anyone remembering to update a file;
  * `site.webmanifest`, so the site can be added to a phone's home screen;
  * a context processor that gives every template a `seo` object with sane
    defaults, which individual pages override.

The canonical origin comes from SITE_URL. Getting it wrong is worse than
leaving it out - canonical tags and sitemaps pointing at the wrong host tell
search engines to index the wrong site - so it is read from the environment
rather than guessed from the request, which a proxy can spoof.
"""

import logging
import os
from datetime import datetime

from flask import Blueprint, Response, g, request, url_for

from extensions import db
from models import Product, Room, SiteSetting

logger = logging.getLogger(__name__)

bp = Blueprint('seo', __name__)

DEFAULT_SITE_URL = 'https://calaci.com.vn'

SITE_NAME = 'Cô Bông Cát Lái'
DEFAULT_DESCRIPTION = (
    'Quán cà phê Cô Bông Cát Lái - cà phê nguyên chất, đồ uống và món ăn '
    'hằng ngày, cùng căn hộ dịch vụ cho thuê ngắn và dài hạn tại Cát Lái, '
    'Thủ Đức, TP.HCM.'
)

# Every editable setting, with the value the site used before the admin page
# existed. A key missing from the database falls back to its default, so an
# empty settings table renders exactly what the hard-coded version did.
DEFAULTS = {
    'site_name': SITE_NAME,
    'site_description': DEFAULT_DESCRIPTION,
    'contact_phone': '0917331628',
    'contact_label': 'cô Bông',
    'street_address': 'Số 78, Đường 54CL',
    'locality': 'Phường Cát Lái, TP. Thủ Đức',
    'region': 'TP. Hồ Chí Minh',
    'price_range': '20.000₫ - 150.000₫',
    'map_url': 'https://maps.app.goo.gl/CXc9XrmZKGgiUMX39',
    'latitude': '10.7734753',
    'longitude': '106.7972421',
    'opening_hours': 'Mo-Su 06:00-22:00',
    # per-page overrides; blank means "use the page's own text"
    'home_title': '',
    'home_description': '',
    'drinks_title': '',
    'drinks_description': '',
    'food_title': '',
    'food_description': '',
    'rooms_title': '',
    'rooms_description': '',
}


def settings():
    """All settings, defaults filled in. Read once per request."""
    cached = getattr(g, '_seo_settings', None)
    if cached is not None:
        return cached
    values = dict(DEFAULTS)
    try:
        for row in SiteSetting.query.all():
            if row.key in DEFAULTS and (row.value or '').strip():
                values[row.key] = row.value.strip()
    except Exception:
        # Before the table exists (first boot) the defaults are correct.
        logger.exception('Could not read site settings; using defaults')
    g._seo_settings = values
    return values


def save_settings(new_values):
    """Write the settings that changed. Blank means 'back to default'."""
    changed = 0
    for key, value in new_values.items():
        if key not in DEFAULTS:
            continue
        value = (value or '').strip()
        row = db.session.get(SiteSetting, key)
        if row is None:
            if not value:
                continue
            db.session.add(SiteSetting(key=key, value=value))
            changed += 1
        elif row.value != value:
            row.value = value
            changed += 1
    db.session.commit()
    g.pop('_seo_settings', None)
    return changed


def site_url():
    return os.environ.get('SITE_URL', DEFAULT_SITE_URL).rstrip('/')


def absolute(path):
    """Turn a site-relative path into a full URL on the canonical origin."""
    if not path:
        return site_url()
    if path.startswith(('http://', 'https://')):
        return path
    return site_url() + '/' + path.lstrip('/')


def register(app):
    app.register_blueprint(bp)

    @app.context_processor
    def inject_seo():
        """Defaults every page gets; templates override with blocks."""
        cfg = settings()
        return {
            'seo': {
                'site_name': cfg['site_name'],
                'site_url': site_url(),
                'description': cfg['site_description'],
                'shop': cfg,
                'canonical': absolute(request.path),
                'image': absolute(url_for('static',
                                          filename='icons/og-image.png')),
                'locale': 'vi_VN',
            },
            'seo_absolute': absolute,
        }


@bp.route('/robots.txt')
def robots():
    """Keep crawlers out of anything private or pointless to index."""
    lines = [
        'User-agent: *',
        # nothing behind a login, and nothing that mutates state
        'Disallow: /admin',
        'Disallow: /customer/login',
        'Disallow: /customer/register',
        'Disallow: /cart',
        'Disallow: /checkout',
        'Disallow: /order_confirmation',
        'Disallow: /add_to_cart',
        'Disallow: /update_cart',
        'Disallow: /remove_from_cart',
        'Allow: /',
        '',
        f'Sitemap: {absolute("/sitemap.xml")}',
        '',
    ]
    return Response('\n'.join(lines), mimetype='text/plain')


@bp.route('/sitemap.xml')
def sitemap():
    """Every page worth indexing, including one entry per product and room."""
    pages = [
        ('/', '1.0', 'daily'),
        ('/products', '0.9', 'daily'),
        ('/products?type=food', '0.9', 'daily'),
        ('/rooms', '0.9', 'weekly'),
    ]

    try:
        for p in Product.query.all():
            pages.append((f'/product/{p.id}', '0.7', 'weekly'))
        for r in Room.query.filter_by(available=True).all():
            pages.append((f'/room/{r.id}', '0.7', 'weekly'))
    except Exception:
        # A sitemap missing its detail pages still beats a 500: search
        # engines back off from a broken sitemap for a long time.
        logger.exception('Could not read products/rooms for the sitemap')

    today = datetime.utcnow().strftime('%Y-%m-%d')
    body = ['<?xml version="1.0" encoding="UTF-8"?>',
            '<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">']
    for path, priority, freq in pages:
        body.append(
            '  <url>'
            f'<loc>{absolute(path).replace("&", "&amp;")}</loc>'
            f'<lastmod>{today}</lastmod>'
            f'<changefreq>{freq}</changefreq>'
            f'<priority>{priority}</priority>'
            '</url>')
    body.append('</urlset>')
    return Response('\n'.join(body), mimetype='application/xml')


@bp.route('/site.webmanifest')
def webmanifest():
    """Lets Android offer "add to home screen" with the right icon."""
    cfg = settings()
    data = {
        'name': cfg['site_name'],
        'short_name': cfg['site_name'].split()[0] if cfg['site_name'] else 'Quán',
        'description': cfg['site_description'],
        'start_url': '/',
        'display': 'standalone',
        'background_color': '#ffffff',
        'theme_color': '#2F9BFF',
        'icons': [
            {'src': url_for('static', filename='icons/android-chrome-192.png'),
             'sizes': '192x192', 'type': 'image/png'},
            {'src': url_for('static', filename='icons/android-chrome-512.png'),
             'sizes': '512x512', 'type': 'image/png'},
        ],
    }
    import json
    return Response(json.dumps(data, ensure_ascii=False),
                    mimetype='application/manifest+json')
