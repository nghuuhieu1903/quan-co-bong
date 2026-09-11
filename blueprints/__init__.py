"""Route blueprints, split out of the original single-file app.py."""

from blueprints import admin, auth, public

all_blueprints = (public.bp, auth.bp, admin.bp)
