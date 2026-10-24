"""
KeyStro Security Analytics & Audit Routes Blueprint
Provides FAR, FRR, EER biometric accuracy metrics, live telemetry audit logs, and health checks.
"""

from flask import request, jsonify
from routes import analytics_bp
import core.database as db
import core.notifier as notifier


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
    Supports filtering by username so when user logs in, only their dataset is shown.
    """
    session_id = request.args.get("session_id")
    username = request.args.get("username", "").strip() or None
    stats = db.get_security_metrics(username=username)
    recent_logs = db.get_recent_logs(session_id=session_id, username=username, limit=200)

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


@analytics_bp.route("/api/alerts/settings", methods=["GET"])
def get_alert_settings():
    """Retrieves current SMS & Email alert settings."""
    settings = db.get_alert_settings()
    # Mask sensitive credentials in GET response
    safe_settings = dict(settings)
    if safe_settings.get("smtp_pass"):
        safe_settings["smtp_pass_set"] = True
        safe_settings["smtp_pass"] = "••••••••"
    else:
        safe_settings["smtp_pass_set"] = False

    if safe_settings.get("twilio_token"):
        safe_settings["twilio_token_set"] = True
        safe_settings["twilio_token"] = "••••••••"
    else:
        safe_settings["twilio_token_set"] = False

    return jsonify({"success": True, "settings": safe_settings})


@analytics_bp.route("/api/alerts/settings", methods=["POST"])
def save_alert_settings():
    """Saves updated SMS & Email alert settings."""
    data = request.get_json() or {}
    curr = db.get_alert_settings()

    # If password or token was masked or empty, preserve existing
    if data.get("smtp_pass") in ("••••••••", "", None):
        data["smtp_pass"] = curr.get("smtp_pass", "")
    if data.get("twilio_token") in ("••••••••", "", None):
        data["twilio_token"] = curr.get("twilio_token", "")

    updated = db.update_alert_settings(data)
    return jsonify({
        "success": True,
        "message": "Alert notification settings saved successfully.",
        "settings": updated
    })


@analytics_bp.route("/api/alerts/test", methods=["POST"])
def test_alerts():
    """Sends immediate test alerts (Email & SMS) to verify configured credentials."""
    data = request.get_json() or {}
    curr = db.get_alert_settings()

    # Allow testing with submitted form fields before saving
    merged = dict(curr)
    if "email_enabled" in data:
        merged["email_enabled"] = data["email_enabled"]
    if "alert_email" in data:
        merged["alert_email"] = data["alert_email"]
    if "smtp_host" in data:
        merged["smtp_host"] = data["smtp_host"]
    if "smtp_port" in data:
        merged["smtp_port"] = data["smtp_port"]
    if "smtp_user" in data:
        merged["smtp_user"] = data["smtp_user"]
    if data.get("smtp_pass") and data["smtp_pass"] != "••••••••":
        merged["smtp_pass"] = data["smtp_pass"]

    if "sms_enabled" in data:
        merged["sms_enabled"] = data["sms_enabled"]
    if "alert_phone" in data:
        merged["alert_phone"] = data["alert_phone"]
    if "twilio_sid" in data:
        merged["twilio_sid"] = data["twilio_sid"]
    if data.get("twilio_token") and data["twilio_token"] != "••••••••":
        merged["twilio_token"] = data["twilio_token"]
    if "twilio_from" in data:
        merged["twilio_from"] = data["twilio_from"]

    res = notifier.dispatch_test_alert(merged)
    return jsonify({
        "success": True,
        "message": "Test alert dispatch routine executed.",
        "results": res
    })


@analytics_bp.route("/api/alerts/logs", methods=["GET"])
def get_alert_logs():
    """Retrieves recent SMS & Email alert logs."""
    logs = db.get_alert_logs(limit=25)
    return jsonify({"success": True, "logs": logs})
