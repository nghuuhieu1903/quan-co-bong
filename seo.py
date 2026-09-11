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

from flask import Blueprint, Response, abort, g, render_template, request, url_for

from extensions import db
from models import MediaFile, Product, Room, SiteSetting

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
    # filename under static/icons of an uploaded share image;
    # blank means use the generated og-image.png
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


# Facebook, Zalo and Twitter all render the share card at roughly 1.91:1.
# An image of any other shape gets cropped by them, unpredictably and usually
# through the middle of the subject, so uploads are fitted here instead.
OG_SIZE = (1200, 630)

# The icon set, and the sizes browsers ask for.
ICON_SIZES = {
    'favicon-16.png': 16,
    'favicon-32.png': 32,
    'apple-touch-icon.png': 180,
    'android-chrome-192.png': 192,
    'android-chrome-512.png': 512,
}

# Android crops a plain icon to a circle, a squircle or a square depending on
# the launcher, and cuts into whatever sits near the edge. A "maskable" icon
# keeps the logo inside a smaller safe zone with padding around it, so every
# shape crops the padding instead of the logo. Chrome's install prompt and
# app icon both use this one when it is present.
MASKABLE_SIZE = 512
MASKABLE_SAFE_ZONE = 0.6   # logo fills 60% of the canvas, centred


def put_media(key, data, content_type):
    """Store (or replace) one uploaded image row."""
    row = db.session.get(MediaFile, key)
    if row is None:
        db.session.add(MediaFile(key=key, data=data, content_type=content_type))
    else:
        row.data, row.content_type = data, content_type
    db.session.commit()


def drop_media(prefix):
    """Delete every stored image whose key starts with `prefix`."""
    rows = MediaFile.query.filter(MediaFile.key.like(prefix + '%')).all()
    for row in rows:
        db.session.delete(row)
    db.session.commit()
    return len(rows)


def has_media(key):
    try:
        return db.session.get(MediaFile, key) is not None
    except Exception:
        logger.exception('Could not read media %r', key)
        return False


def _encode(img, fmt, **kw):
    import io as _io
    buf = _io.BytesIO()
    img.save(buf, fmt, **kw)
    return buf.getvalue()


def save_og_image(file_storage):
    """Fit an upload to the share-card shape and store it in the database."""
    from PIL import Image, UnidentifiedImageError

    try:
        img = Image.open(file_storage.stream)
        img.load()
    except (UnidentifiedImageError, OSError):
        return False, 'Tệp không phải là ảnh hợp lệ'

    if img.mode != 'RGB':
        img = img.convert('RGB')

    target_w, target_h = OG_SIZE
    src_w, src_h = img.size
    if src_w < 200 or src_h < 100:
        return False, f'Ảnh quá nhỏ ({src_w}x{src_h}), cần ít nhất 600x315'

    # cover: scale until both sides reach the target, then centre-crop
    scale = max(target_w / src_w, target_h / src_h)
    new = img.resize((max(1, round(src_w * scale)), max(1, round(src_h * scale))),
                     Image.LANCZOS)
    left, top = (new.width - target_w) // 2, (new.height - target_h) // 2
    new = new.crop((left, top, left + target_w, top + target_h))

    put_media('og', _encode(new, 'JPEG', quality=88, optimize=True), 'image/jpeg')
    return True, f'Đã cập nhật ảnh chia sẻ ({src_w}x{src_h} → 1200x630)'


def clear_og_image():
    drop_media('og')


def save_icons(file_storage):
    """Rebuild the whole icon set from one uploaded logo.

    Browsers ask for half a dozen sizes and a .ico; uploading each by hand
    would be tedious and easy to get inconsistent, so one square image is
    resized into all of them. It is centre-cropped square first - a favicon is
    always square, and letterboxing a wide logo would waste most of the 16
    pixels that decide whether it is recognisable in a tab.
    """
    from PIL import Image, UnidentifiedImageError

    try:
        img = Image.open(file_storage.stream)
        img.load()
    except (UnidentifiedImageError, OSError):
        return False, 'Tệp không phải là ảnh hợp lệ'

    if img.mode != 'RGBA':
        img = img.convert('RGBA')

    w, h = img.size
    if min(w, h) < 64:
        return False, f'Ảnh quá nhỏ ({w}x{h}), cần cạnh ngắn ít nhất 64px'

    side = min(w, h)
    img = img.crop(((w - side) // 2, (h - side) // 2,
                    (w - side) // 2 + side, (h - side) // 2 + side))

    for name, size in ICON_SIZES.items():
        put_media('icon:' + name,
                  _encode(img.resize((size, size), Image.LANCZOS), 'PNG'),
                  'image/png')
    put_media('icon:favicon.ico',
              _encode(img.resize((64, 64), Image.LANCZOS), 'ICO',
                      sizes=[(16, 16), (32, 32), (48, 48), (64, 64)]),
              'image/x-icon')

    # Maskable: the logo on a solid canvas of the theme colour, shrunk into
    # the safe zone so any shape the launcher applies crops padding, not logo.
    canvas = Image.new('RGBA', (MASKABLE_SIZE, MASKABLE_SIZE), '#2F9BFF')
    logo_side = int(MASKABLE_SIZE * MASKABLE_SAFE_ZONE)
    logo = img.resize((logo_side, logo_side), Image.LANCZOS)
    offset = (MASKABLE_SIZE - logo_side) // 2
    canvas.paste(logo, (offset, offset), logo)
    put_media('icon:maskable-512.png', _encode(canvas, 'PNG'), 'image/png')

    return True, f'Đã tạo {len(ICON_SIZES) + 2} kích thước icon từ ảnh {w}x{h}'


def clear_icons():
    drop_media('icon:')

def media_url(key, fallback_static):
    """URL for an uploaded image, or the built-in file when none was uploaded.

    The `v=` stamp is the row's updated_at, so a replaced image appears at
    once instead of the browser serving its cached copy of the old one.
    """
    row = None
    try:
        row = db.session.get(MediaFile, key)
    except Exception:
        logger.exception('Could not read media %r', key)
    if row is None:
        return url_for('static', filename=fallback_static)
    stamp = int(row.updated_at.timestamp()) if row.updated_at else 0
    return url_for('seo.media', key=key, v=stamp)


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
                'image': absolute(media_url('og', 'icons/og-image.png')),
                'locale': 'vi_VN',
                'icons': {name: media_url('icon:' + name, 'icons/' + name)
                          for name in list(ICON_SIZES) + ['favicon.ico']},
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


@bp.route('/offline')
def offline():
    """Shown by the service worker when a tap has no network to answer it."""
    cfg = settings()
    return render_template('offline.html', seo_shop=cfg), 200



def _short_name(full_name, limit=15):
    """A home-screen-length name: whole words, not a truncated first one."""
    words = (full_name or '').split()
    if not words:
        return 'Quán'
    out = words[0]
    for w in words[1:]:
        if len(out) + 1 + len(w) > limit:
            break
        out += ' ' + w
    return out


@bp.route('/site.webmanifest')
def webmanifest():
    """Lets Android offer "add to home screen" with the right icon."""
    cfg = settings()
    data = {
        'name': cfg['site_name'],
        # Android shows this under the home-screen icon, where 12 characters
        # is roughly the cutoff before it gets truncated with an ellipsis.
        # The first word alone ("Cô") reads as broken, so take whole words
        # until the limit instead.
        'short_name': _short_name(cfg['site_name']),
        'description': cfg['site_description'],
        'start_url': '/',
        'display': 'standalone',
        'background_color': '#ffffff',
        'theme_color': '#2F9BFF',
        'icons': [
            {'src': media_url('icon:android-chrome-192.png',
                              'icons/android-chrome-192.png'),
             'sizes': '192x192', 'type': 'image/png', 'purpose': 'any'},
            {'src': media_url('icon:android-chrome-512.png',
                              'icons/android-chrome-512.png'),
             'sizes': '512x512', 'type': 'image/png', 'purpose': 'any'},
            {'src': media_url('icon:maskable-512.png',
                              'icons/maskable-512.png'),
             'sizes': '512x512', 'type': 'image/png', 'purpose': 'maskable'},
        ],
    }
    import json
    return Response(json.dumps(data, ensure_ascii=False),
                    mimetype='application/manifest+json')


@bp.route('/media/<path:key>')
def media(key):
    """Serve an uploaded image out of the database.

    Cached hard by the browser; the URL carries the row's timestamp, so a
    replacement changes the URL and the old copy is never reused.
    """
    row = db.session.get(MediaFile, key)
    if row is None:
        abort(404)
    resp = Response(row.data, mimetype=row.content_type)
    resp.headers['Cache-Control'] = 'public, max-age=31536000, immutable'
    return resp
