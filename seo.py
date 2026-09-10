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
    # filename under static/icons of an uploaded share image;
    # blank means use the generated og-image.png
    'og_image': '',
    # '1' when a logo has been uploaded and the icon set regenerated from it
    'custom_icons': '',
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
OG_UPLOAD_NAME = 'og-custom.jpg'


def og_image_path(app_root):
    """Where an uploaded share image lives on disk."""
    return os.path.join(app_root, 'static', 'icons', OG_UPLOAD_NAME)


def save_og_image(file_storage, app_root):
    """Fit an upload to the share-card shape and store it.

    Returns (ok, message). The original is never kept: it is cropped to cover
    1200x630 so nothing is letterboxed, then written as JPEG.
    """
    from PIL import Image, UnidentifiedImageError

    try:
        img = Image.open(file_storage.stream)
        img.load()
    except (UnidentifiedImageError, OSError):
        return False, 'Tệp không phải là ảnh hợp lệ'

    if img.mode not in ('RGB', 'L'):
        img = img.convert('RGB')
    elif img.mode == 'L':
        img = img.convert('RGB')

    target_w, target_h = OG_SIZE
    src_w, src_h = img.size
    if src_w < 200 or src_h < 100:
        return False, f'Ảnh quá nhỏ ({src_w}x{src_h}), cần ít nhất 600x315'

    # cover: scale so both sides reach the target, then centre-crop
    scale = max(target_w / src_w, target_h / src_h)
    new = img.resize((max(1, round(src_w * scale)), max(1, round(src_h * scale))),
                     Image.LANCZOS)
    left = (new.width - target_w) // 2
    top = (new.height - target_h) // 2
    new = new.crop((left, top, left + target_w, top + target_h))

    path = og_image_path(app_root)
    try:
        os.makedirs(os.path.dirname(path), exist_ok=True)
        new.save(path, 'JPEG', quality=88, optimize=True)
    except OSError as exc:
        # Almost always the app user not being able to write into
        # static/icons on the server; say so instead of failing blankly.
        logger.exception('Cannot write the share image to %s', path)
        return False, (f'Không ghi được tệp vào {path} ({exc.strerror or exc}). '
                       'Kiểm tra quyền ghi của thư mục static/icons.')
    return True, f'Đã cập nhật ảnh chia sẻ ({src_w}x{src_h} → 1200x630)'


def clear_og_image(app_root):
    """Drop the upload so the generated image is used again."""
    try:
        os.remove(og_image_path(app_root))
    except FileNotFoundError:
        pass


# The icon set, and the sizes browsers ask for. A custom upload writes the
# same names with a prefix, so the generated originals are never lost and
# "use the default again" is just a flag flip.
ICON_SIZES = {
    'favicon-16.png': 16,
    'favicon-32.png': 32,
    'apple-touch-icon.png': 180,
    'android-chrome-192.png': 192,
    'android-chrome-512.png': 512,
}
CUSTOM_PREFIX = 'custom-'


def icon_file(name):
    """Filename under static/icons for one icon, custom if one was uploaded."""
    if settings().get('custom_icons') == '1':
        return CUSTOM_PREFIX + name
    return name


def save_icons(file_storage, app_root):
    """Rebuild the whole icon set from one uploaded logo.

    Browsers ask for half a dozen sizes and a .ico; uploading each by hand
    would be tedious and easy to get inconsistent, so one square image is
    resized into all of them. The image is centre-cropped to a square first -
    a favicon is always square, and letterboxing a wide logo would waste most
    of the 16 pixels that actually matter.
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

    out_dir = os.path.join(app_root, 'static', 'icons')
    written = []
    try:
        os.makedirs(out_dir, exist_ok=True)
        for name, size in ICON_SIZES.items():
            img.resize((size, size), Image.LANCZOS).save(
                os.path.join(out_dir, CUSTOM_PREFIX + name))
            written.append(name)
        # multi-resolution .ico for the address bar and older browsers
        img.resize((64, 64), Image.LANCZOS).save(
            os.path.join(out_dir, CUSTOM_PREFIX + 'favicon.ico'),
            sizes=[(16, 16), (32, 32), (48, 48), (64, 64)])
        written.append('favicon.ico')
    except OSError as exc:
        logger.exception('Cannot write icons into %s', out_dir)
        return False, (f'Không ghi được vào {out_dir} ({exc.strerror or exc}). '
                       'Kiểm tra quyền ghi của thư mục static/icons.')

    return True, f'Đã tạo {len(written)} kích thước icon từ ảnh {w}x{h}'


def clear_icons(app_root):
    """Delete the uploaded set so the generated icons are used again."""
    out_dir = os.path.join(app_root, 'static', 'icons')
    for name in list(ICON_SIZES) + ['favicon.ico']:
        try:
            os.remove(os.path.join(out_dir, CUSTOM_PREFIX + name))
        except FileNotFoundError:
            pass


def og_image_file():
    """The share image filename under static/icons, upload or generated."""
    return settings().get('og_image') or 'og-image.png'


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
                                          filename='icons/' + og_image_file())),
                'locale': 'vi_VN',
                'icons': {name: icon_file(name)
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
            {'src': url_for('static',
                            filename='icons/' + icon_file('android-chrome-192.png')),
             'sizes': '192x192', 'type': 'image/png'},
            {'src': url_for('static',
                            filename='icons/' + icon_file('android-chrome-512.png')),
             'sizes': '512x512', 'type': 'image/png'},
        ],
    }
    import json
    return Response(json.dumps(data, ensure_ascii=False),
                    mimetype='application/manifest+json')
