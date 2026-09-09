"""Flask extension objects, created unbound so modules can import them
without importing the app (which would be a circular import). The app
factory in app.py calls init_app on each."""

from flask_session import Session
from flask_sqlalchemy import SQLAlchemy
from flask_wtf.csrf import CSRFProtect

db = SQLAlchemy()
sess = Session()
csrf = CSRFProtect()
