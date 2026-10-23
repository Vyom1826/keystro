"""
KeyStro Security Analytics & Audit Routes Blueprint
Provides FAR, FRR, EER biometric accuracy metrics, live telemetry audit logs, and health checks.
"""

from flask import request, jsonify
from routes import analytics_bp
import core.database as db


@analytics_bp.route("/api/health", methods=["GET"])
def health_check():
    """System health check endpoint."""
    return jsonify({
        "status": "healthy",
        "service": "KeyStro Continuous Keystroke Authentication",
        "version": "1.0.0",
        "team": "TRISHUL"
    })


@analytics_bp.route("/api/metrics", methods=["GET"])
def get_metrics():
    """
    Returns security analytics, FAR, FRR, EER, and recent verification telemetry logs.
    """
    session_id = request.args.get("session_id")
    stats = db.get_security_metrics()
    recent_logs = db.get_recent_logs(session_id=session_id, limit=30)

    return jsonify({
        "success": True,
        "metrics": stats,
        "logs": recent_logs
    })


@analytics_bp.route("/api/reset", methods=["POST"])
def reset_system():
    """Resets verification logs and sessions for a fresh test cycle."""
    db.reset_database()
    return jsonify({
        "success": True,
        "message": "Database verification logs and sessions reset."
    })
