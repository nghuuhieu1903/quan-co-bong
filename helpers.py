"""Small shared utilities: console printing, email, and image uploads."""

import builtins
import logging
import os
import re
import smtplib
import sys
import time
from email.mime.text import MIMEText

from flask import current_app
from werkzeug.utils import secure_filename


def safe_print(*args, **kwargs):
    safe_args = []
    encoding = sys.stdout.encoding or 'utf-8'
    for arg in args:
        if isinstance(arg, str):
            try:
                arg.encode(encoding)
                safe_args.append(arg)
            except UnicodeEncodeError:
                safe_args.append(arg.encode(encoding, errors='replace').decode(encoding, errors='replace'))
        else:
            safe_args.append(arg)
    builtins.print(*safe_args, **kwargs)

print = safe_print

logger = logging.getLogger(__name__)


def configure_logging(level=None):
    """Send log records to stderr with a timestamp and level.

    Handlers across the app call logger.exception(), which prints the message
    *and* the traceback - the plain print() calls this replaced showed only
    str(e), so a failure told you what broke but never where. Set LOG_LEVEL
    (e.g. DEBUG) to change the verbosity.
    """
    level = level or os.environ.get('LOG_LEVEL', 'INFO').upper()
    logging.basicConfig(
        level=getattr(logging, level, logging.INFO),
        format='%(asctime)s %(levelname)-7s %(name)s: %(message)s',
    )

# via environment variables (.env) on the server; nothing is sent if
# SMTP_USER/SMTP_PASSWORD aren't set.
SMTP_HOST = os.environ.get('SMTP_HOST', 'smtp.gmail.com')
SMTP_PORT = int(os.environ.get('SMTP_PORT', '587'))
SMTP_USER = os.environ.get('SMTP_USER')
SMTP_PASSWORD = os.environ.get('SMTP_PASSWORD')
SUPER_ADMIN_RECOVERY_EMAIL = os.environ.get('SUPER_ADMIN_RECOVERY_EMAIL', 'hhieu193@gmail.com')

def send_email(to_email, subject, body):
    """Sends a plain-text email via SMTP. Returns True on success, False
    (and prints the error) if SMTP isn't configured or sending fails."""
    if not SMTP_USER or not SMTP_PASSWORD:
        print(f"SMTP not configured - would have sent to {to_email}: {subject}")
        return False
    try:
        msg = MIMEText(body, 'plain', 'utf-8')
        msg['Subject'] = subject
        msg['From'] = SMTP_USER
        msg['To'] = to_email
        with smtplib.SMTP(SMTP_HOST, SMTP_PORT) as server:
            server.starttls()
            server.login(SMTP_USER, SMTP_PASSWORD)
            server.sendmail(SMTP_USER, [to_email], msg.as_string())
        return True
    except Exception as e:
        logger.exception(f"Failed to send email to {to_email}")
        return False


ALLOWED_EXTENSIONS = {'png', 'jpg', 'jpeg', 'gif', 'webp'}

def allowed_file(filename):
    return '.' in filename and \
           filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS

def save_uploaded_file(file, prefix=''):
    """Save one uploaded file with a unique timestamped name. Returns the saved filename, or None if no valid file was given."""
    if not file or file.filename == '' or not allowed_file(file.filename):
        return None
    filename = secure_filename(file.filename)
    timestamp = int(time.time())
    filename = f"{timestamp}_{prefix}{filename}"

    upload_path = os.path.join(current_app.root_path,
                               current_app.config['UPLOAD_FOLDER'])
    os.makedirs(upload_path, exist_ok=True)
    file.save(os.path.join(upload_path, filename))
    return filename

def save_uploaded_files(files, prefix='detail_'):
    """Save multiple uploaded files, returning the list of saved filenames (skips invalid entries)."""
    return [name for name in (save_uploaded_file(f, prefix=prefix) for f in files) if name]



def format_vnd(value):
    """Vietnamese money: a dot every three digits, no decimals.

    Vietnamese uses the dot as the thousands separator, which is the opposite
    of Python's "{:,}". Registered as the "vnd" Jinja filter so every screen
    formats money the same way.
    """
    try:
        number = round(float(value or 0))
    except (TypeError, ValueError):
        return value
    return f'{number:,.0f}'.replace(',', '.')


def parse_vnd(raw):
    """Read a money field back: accepts 45000, "45.000" or "45 000".

    The price boxes show a dot every three digits, so what posts back is not a
    bare number. Anything that is not plainly an amount returns None so the
    caller can show a message instead of raising and returning a 500.

    Separators are only accepted where they really group thousands: "45.000"
    is 45000, but "45,5" is rejected rather than silently read as 455, which
    would be ten times the intended price.
    """
    text = str(raw if raw is not None else '')
    for junk in ('VN\u0110', 'VND', 'vnd', '\u0111', '\u0110', ' ', '\xa0', '\u202f'):
        text = text.replace(junk, '')
    text = text.strip()

    if text.isdigit():
        return float(text)
    # one separator, repeated, with exact groups of three
    if re.fullmatch(r'\d{1,3}(\.\d{3})+', text):
        return float(text.replace('.', ''))
    if re.fullmatch(r'\d{1,3}(,\d{3})+', text):
        return float(text.replace(',', ''))
    return None


def _relative_luminance(hex_colour):
    """WCAG relative luminance of #rrggbb, 0 (black) to 1 (white)."""
    value = (hex_colour or '').strip().lstrip('#')
    if len(value) == 3:
        value = ''.join(ch * 2 for ch in value)
    if len(value) != 6:
        raise ValueError(f'not a colour: {hex_colour!r}')
    channels = []
    for i in (0, 2, 4):
        c = int(value[i:i + 2], 16) / 255
        channels.append(c / 12.92 if c <= 0.03928 else ((c + 0.055) / 1.055) ** 2.4)
    return 0.2126 * channels[0] + 0.7152 * channels[1] + 0.0722 * channels[2]


def contrast_ratio(colour_a, colour_b):
    """How far apart two colours are, 1:1 (identical) to 21:1 (black/white)."""
    a, b = _relative_luminance(colour_a), _relative_luminance(colour_b)
    high, low = max(a, b), min(a, b)
    return (high + 0.05) / (low + 0.05)


# Below this a printed code stops being reliable for a phone camera, even
# though a software decoder reading the exact pixels still manages.
MIN_QR_CONTRAST = 4.0


def check_qr_colours(background, foreground):
    """Return an error message for a colour pair a scanner would struggle with."""
    try:
        ratio = contrast_ratio(background, foreground)
    except ValueError:
        return 'Màu không hợp lệ.'

    if _relative_luminance(foreground) >= _relative_luminance(background):
        return ('Ô vuông phải đậm hơn nền. Mã ngược màu (ô sáng trên nền tối) '
                'nhiều máy quét không đọc được.')
    if ratio < MIN_QR_CONTRAST:
        return (f'Hai màu quá giống nhau (độ tương phản {ratio:.1f}:1, '
                f'cần ít nhất {MIN_QR_CONTRAST:.0f}:1). '
                'Camera điện thoại sẽ không quét nổi, nhất là khi in ra.')
    return None
