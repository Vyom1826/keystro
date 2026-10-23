"""
KeyStro Modular REST API Route Blueprints
Separates session verification, user enrollment, and security analytics.
"""
from flask import Blueprint

session_bp = Blueprint("session", __name__)
enroll_bp = Blueprint("enroll", __name__)
analytics_bp = Blueprint("analytics", __name__)

from routes import session_routes, enroll_routes, analytics_routes
