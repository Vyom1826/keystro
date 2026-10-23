"""
KeyStro - AI-Powered Continuous Keystroke Authentication System
Application Factory & Server Entry Point
TRISHUL Hackathon Implementation
"""

import os
import logging
from flask import Flask, render_template, send_from_directory
from flask_cors import CORS

import core.database as db
from routes import session_bp, enroll_bp, analytics_bp

# Configure Logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s"
)
logger = logging.getLogger("KeyStro")


def create_app():
    """Application factory: initializes Flask app, database, and route blueprints."""
    app = Flask(__name__, template_folder="templates", static_folder="static")
    app.config["TEMPLATES_AUTO_RELOAD"] = True
    app.jinja_env.auto_reload = True
    CORS(app)

    # Disable HTTP caching for instant telemetry updates
    @app.after_request
    def add_no_cache_headers(response):
        response.headers["Cache-Control"] = "no-cache, no-store, must-revalidate, max-age=0"
        response.headers["Pragma"] = "no-cache"
        response.headers["Expires"] = "0"
        return response

    # Initialize SQLite database
    db.init_db()

    # Register Route Blueprints
    app.register_blueprint(session_bp)
    app.register_blueprint(enroll_bp)
    app.register_blueprint(analytics_bp)

    # Main Dashboard Route
    @app.route("/")
    def index():
        return render_template("index.html")

    # Static assets fallback
    @app.route("/static/<path:path>")
    def send_static(path):
        return send_from_directory("static", path)

    return app


# Application instance for gunicorn / test runners
app = create_app()


if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    print("\n" + "=" * 65)
    print("  [+] KeyStro AI Continuous Keystroke Authentication is LIVE!")
    print(f"  >>> Dashboard URL: http://127.0.0.1:{port}")
    print("=" * 65 + "\n")
    app.run(host="0.0.0.0", port=port, debug=False)
