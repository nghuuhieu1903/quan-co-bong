"""Application factory for the Cô Bông Cát Lái site.

This file used to hold everything - models, routes, the speaker/automation
code and the migrations, ~2900 lines of it. It now only wires the pieces
together; the pieces themselves live in:

    extensions.py    db / session objects, created unbound
    models.py        SQLAlchemy models
    translations.py  the VI/EN strings
    helpers.py       printing, email, image uploads
    decorators.py    admin / super-admin / manager access control
    automation.py    LaptopSpeaker and AutomationController
    db_init.py       ALTER TABLE migrations and first-run seed data
    blueprints/      the routes, in four groups

Run locally with `python app.py`; Gunicorn imports the module-level `app`.
"""

import logging
import os
import secrets
from datetime import timedelta

from flask import Flask, request, session

try:
    from dotenv import load_dotenv
    # Loads variables from a .env file placed next to app.py (if present).
    # Lets DATABASE_URL/SECRET_KEY be set via a plain file on the VPS
    # instead of relying on a control panel's "environment variables" UI.
    load_dotenv(os.path.join(os.path.dirname(os.path.abspath(__file__)), '.env'))
except ImportError:
    pass

from blueprints import all_blueprints
from db_init import init_database
from helpers import configure_logging
from extensions import csrf, db, sess
from translations import TRANSLATIONS


# The value this used to fall back to is committed in a public repository,
# so anyone could compute a valid session cookie - including one that says
# admin_role=super_admin - against any deployment that had not set its own.
# A random per-process key means unset SECRET_KEY costs you sessions on
# restart instead of costing you the admin account.
INSECURE_DEFAULT_KEYS = {'your-secret-key-change-this-in-production',
                         'change-this-to-a-long-random-string'}


def resolve_secret_key():
    key = os.environ.get('SECRET_KEY')
    if key and key not in INSECURE_DEFAULT_KEYS:
        return key
    reason = 'is not set' if not key else 'is still the example value'
    logging.getLogger(__name__).warning(
        'SECRET_KEY %s, so a random one was generated for this process. '
        'Sessions will not survive a restart and will not be shared between '
        'workers. Set SECRET_KEY in .env to a long random string '
        '(python -c "import secrets; print(secrets.token_hex(32))").', reason)
    return secrets.token_hex(32)


def configure(app):
    app.config['SECRET_KEY'] = resolve_secret_key()

    # The session cookie is the only thing standing between a visitor and an
    # admin session, so keep it out of JavaScript and off cross-site requests.
    # SESSION_COOKIE_SECURE is opt-in because it would break plain-http local
    # testing; turn it on once the site is behind HTTPS.
    app.config['SESSION_COOKIE_HTTPONLY'] = True
    app.config['SESSION_COOKIE_SAMESITE'] = 'Lax'
    app.config['SESSION_COOKIE_SECURE'] = os.environ.get('SESSION_COOKIE_SECURE') == '1' 

    # MySQL database configuration.
    # Set DATABASE_URL to e.g. mysql+pymysql://user:password@host:3306/dbname
    # Falls back to a local MySQL default for development if not set.
    db_url = os.environ.get('DATABASE_URL',
                            'mysql+pymysql://root:@localhost:3306/ecommerce')
    if db_url.startswith('mysql://'):
        db_url = db_url.replace('mysql://', 'mysql+pymysql://', 1)
    app.config['SQLALCHEMY_DATABASE_URI'] = db_url
    # Force utf8mb4 on every connection so Vietnamese text is stored correctly
    # regardless of the MySQL server's default charset. Only MySQL connections
    # understand this option, so skip it for local SQLite/dev databases.
    if db_url.startswith('mysql'):
        app.config['SQLALCHEMY_ENGINE_OPTIONS'] = {
            'connect_args': {'charset': 'utf8mb4'}}

    app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
    app.config['SESSION_TYPE'] = 'filesystem'
    app.config['UPLOAD_FOLDER'] = 'static/images'
    app.config['MAX_CONTENT_LENGTH'] = 16 * 1024 * 1024  # 16MB max file size
    # Customers stay logged in across visits; admins do not (see
    # admin_authenticate / customer_authenticate - only the customer session
    # is marked permanent).
    app.config['PERMANENT_SESSION_LIFETIME'] = timedelta(days=30)


def register_translations(app):
    @app.context_processor
    def inject_translations():
        lang = session.get('lang', 'vi')

        def get_text(key):
            return TRANSLATIONS.get(lang, TRANSLATIONS['vi']).get(key, key)

        return dict(_=get_text, current_lang=lang)

    @app.context_processor
    def inject_endpoint():
        """`current_endpoint` is the view name without its blueprint prefix.

        The sidebars highlight the current page by comparing against names
        like 'admin_dashboard'. Once the routes moved into blueprints,
        request.endpoint became 'admin.admin_dashboard' and every one of
        those comparisons silently stopped matching - no page looked active.
        Comparing on the short name keeps the templates working whatever
        blueprint a route ends up in.
        """
        return dict(current_endpoint=(request.endpoint or '').rsplit('.', 1)[-1])


def create_app():
    configure_logging()

    app = Flask(__name__)
    configure(app)

    db.init_app(app)
    sess.init_app(app)
    # Rejects any POST/PUT/DELETE without a valid token. Templates get the
    # token from the csrf_token() global; the two fetch() callers send it in
    # an X-CSRFToken header (see modern_base.html / admin_base.html).
    csrf.init_app(app)

    register_translations(app)
    for blueprint in all_blueprints:
        app.register_blueprint(blueprint)

    # Runs on both local development and a production Gunicorn import.
    with app.app_context():
        init_database()

    return app


app = create_app()


if __name__ == '__main__':
    print("Registered Routes:")
    for rule in app.url_map.iter_rules():
        print(f"{rule.endpoint}: {rule}")

    # Binds to every interface so another device on the same network can
    # reach it - that is the point of running it locally to test from a
    # phone or a second laptop. Set FLASK_RUN_HOST=127.0.0.1 to keep it to
    # this machine only.
    #
    # Debug mode stays opt-in: its interactive console runs arbitrary code
    # for anyone who can reach a traceback, which is genuinely unsafe on a
    # shared network. Turn it on deliberately when you want auto-reload:
    #   FLASK_DEBUG=1 python app.py
    app.run(debug=os.environ.get('FLASK_DEBUG') == '1',
            host=os.environ.get('FLASK_RUN_HOST', '0.0.0.0'),
            port=int(os.environ.get('FLASK_RUN_PORT', '5000')))
