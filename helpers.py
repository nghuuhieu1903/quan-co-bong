"""Small shared utilities: console printing, email, and image uploads."""

import builtins
import logging
import os
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

