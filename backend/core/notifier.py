"""
KeyStro Real-time Risk Notification & Alert Dispatcher
Supports automated SMS (Twilio / SMS Gateway) and Email (SMTP / TLS) alerts
triggered when biometric anomaly risk reaches MEDIUM or HIGH.
"""

import os
import time
import logging
import smtplib
import threading
import urllib.parse
import urllib.request
import base64
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from datetime import datetime, timezone

import core.database as db

logger = logging.getLogger("KeyStro.Notifier")

# In-memory tracking of last alert timestamp per session to enforce cooldown
_SESSION_LAST_ALERT = {}


def trigger_risk_alert(username: str, session_id: str, risk_level: str, score: float, status_message: str = "", features: dict = None):
    """
    Evaluates whether an active keystroke evaluation risk triggers an alert notification.
    Runs non-blockingly on a background daemon thread so live typing latency is unaffected.
    """
    risk_level = (risk_level or "").strip().upper()
    if risk_level not in ("MEDIUM", "HIGH"):
        return

    settings = db.get_alert_settings()
    min_level = settings.get("min_risk_level", "MEDIUM").upper()

    # If configured for HIGH only, skip MEDIUM
    if min_level == "HIGH" and risk_level == "MEDIUM":
        return

    # Check cooldown per session
    cooldown = int(settings.get("cooldown_seconds", 60))
    now = time.time()
    last_time = _SESSION_LAST_ALERT.get(session_id, 0)
    if (now - last_time) < cooldown:
        logger.debug(f"Skipping alert for session {session_id} due to cooldown ({int(now - last_time)}s < {cooldown}s).")
        return

    _SESSION_LAST_ALERT[session_id] = now

    # Dispatch asynchronously in daemon thread
    t = threading.Thread(
        target=_dispatch_alert_async,
        args=(username, session_id, risk_level, score, status_message, features, settings),
        daemon=True
    )
    t.start()


def _dispatch_alert_async(username: str, session_id: str, risk_level: str, score: float, status_message: str, features: dict, settings: dict):
    """Background worker that dispatches Email and/or SMS."""
    score_pct = round(score * 100, 1)
    timestamp = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC")

    # 1. Dispatch Email if enabled
    if settings.get("email_enabled", 1):
        recipient_email = settings.get("alert_email", "").strip()
        smtp_user = settings.get("smtp_user", "").strip()
        smtp_pass = settings.get("smtp_pass", "").strip()
        smtp_host = settings.get("smtp_host", "smtp.gmail.com").strip()
        smtp_port = int(settings.get("smtp_port", 587))

        subject = f"⚠️ [KeyStro Alert] {risk_level} Risk Keystroke Anomaly - User '{username}'"
        body_text = f"""KeyStro Zero-Trust Keystroke Authentication Alert
--------------------------------------------------
Risk Level       : {risk_level}
Confidence Score : {score_pct}%
User Profile     : {username}
Session ID       : {session_id}
Timestamp        : {timestamp}
Detection Cause  : {status_message or 'Significant typing rhythm / latency drift detected.'}

Biometric Snapshot:
  - Dwell Mean : {features.get('dwell_mean', '--') if features else '--'} ms
  - Flight Mean: {features.get('flight_mean', '--') if features else '--'} ms
  - Cadence IKL: {features.get('ikl_mean', '--') if features else '--'} ms
  - Speed      : {features.get('speed_kpm', '--') if features else '--'} KPM

Recommended Security Action:
If this session was not authorized by the legitimate owner, lock the terminal or review the Adaptive MFA OTP prompt.
"""

        if recipient_email and smtp_user and smtp_pass:
            try:
                msg = MIMEMultipart()
                msg["From"] = smtp_user
                msg["To"] = recipient_email
                msg["Subject"] = subject
                msg.attach(MIMEText(body_text, "plain"))

                server = smtplib.SMTP(smtp_host, smtp_port, timeout=10)
                server.starttls()
                server.login(smtp_user, smtp_pass)
                server.sendmail(smtp_user, [recipient_email], msg.as_string())
                server.quit()

                db.log_alert(username, session_id, risk_level, score, "email", recipient_email, "sent", f"Email alert sent successfully to {recipient_email}")
                logger.info(f"EMAIL ALERT SENT to {recipient_email} for user {username} ({risk_level}).")
            except Exception as e:
                err_msg = f"Failed to send email alert via SMTP: {e}"
                logger.error(err_msg)
                db.log_alert(username, session_id, risk_level, score, "email", recipient_email, "failed", err_msg)
        else:
            # Simulated Email Alert
            target = recipient_email or "Configured Admin Email"
            sim_msg = f"[SIMULATED EMAIL] {subject} -> {target}"
            db.log_alert(username, session_id, risk_level, score, "email", target, "simulated", sim_msg)
            logger.info(sim_msg)

    # 2. Dispatch SMS if enabled
    if settings.get("sms_enabled", 1):
        recipient_phone = settings.get("alert_phone", "").strip()
        twilio_sid = settings.get("twilio_sid", "").strip()
        twilio_token = settings.get("twilio_token", "").strip()
        twilio_from = settings.get("twilio_from", "").strip()

        sms_body = f"[KeyStro Alert] {risk_level} risk typing anomaly detected for user '{username}' (Score: {score_pct}%). Session: {session_id[:12]}. Check terminal activity."

        if recipient_phone and twilio_sid and twilio_token and twilio_from:
            try:
                twilio_url = f"https://api.twilio.com/2010-04-01/Accounts/{twilio_sid}/Messages.json"
                post_data = urllib.parse.urlencode({
                    "From": twilio_from,
                    "To": recipient_phone,
                    "Body": sms_body
                }).encode("utf-8")

                req = urllib.request.Request(twilio_url, data=post_data, method="POST")
                auth_str = f"{twilio_sid}:{twilio_token}"
                encoded_auth = base64.b64encode(auth_str.encode("utf-8")).decode("utf-8")
                req.add_header("Authorization", f"Basic {encoded_auth}")

                with urllib.request.urlopen(req, timeout=10) as resp:
                    resp_code = resp.getcode()
                    if resp_code in (200, 201):
                        db.log_alert(username, session_id, risk_level, score, "sms", recipient_phone, "sent", f"SMS sent to {recipient_phone}")
                        logger.info(f"SMS ALERT SENT to {recipient_phone} for user {username}.")
                    else:
                        db.log_alert(username, session_id, risk_level, score, "sms", recipient_phone, "failed", f"Twilio HTTP status: {resp_code}")
            except Exception as e:
                err_msg = f"Failed to send SMS via Twilio: {e}"
                logger.error(err_msg)
                db.log_alert(username, session_id, risk_level, score, "sms", recipient_phone, "failed", err_msg)
        else:
            # Simulated SMS Alert
            target = recipient_phone or "Configured Admin Mobile"
            sim_msg = f"[SIMULATED SMS] {sms_body} -> {target}"
            db.log_alert(username, session_id, risk_level, score, "sms", target, "simulated", sim_msg)
            logger.info(sim_msg)


def dispatch_test_alert(settings_override: dict = None) -> dict:
    """
    Sends a test Email and SMS immediately using current or provided settings.
    Returns status breakdown for UI confirmation.
    """
    settings = settings_override or db.get_alert_settings()
    results = {"email": {"status": "skipped", "message": "Email disabled."}, "sms": {"status": "skipped", "message": "SMS disabled."}}

    now_str = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC")

    # 1. Test Email
    if settings.get("email_enabled", 1):
        recipient_email = settings.get("alert_email", "").strip()
        smtp_user = settings.get("smtp_user", "").strip()
        smtp_pass = settings.get("smtp_pass", "").strip()
        smtp_host = settings.get("smtp_host", "smtp.gmail.com").strip()
        smtp_port = int(settings.get("smtp_port", 587))

        subject = "🔔 [KeyStro Test Alert] Verification Notification"
        body = f"This is a test notification from KeyStro Continuous Keystroke Dynamics.\nTimestamp: {now_str}\nIf you received this message, your alert channel is operational!"

        if recipient_email and smtp_user and smtp_pass:
            try:
                msg = MIMEMultipart()
                msg["From"] = smtp_user
                msg["To"] = recipient_email
                msg["Subject"] = subject
                msg.attach(MIMEText(body, "plain"))

                server = smtplib.SMTP(smtp_host, smtp_port, timeout=8)
                server.starttls()
                server.login(smtp_user, smtp_pass)
                server.sendmail(smtp_user, [recipient_email], msg.as_string())
                server.quit()

                results["email"] = {"status": "sent", "message": f"Real test email delivered to {recipient_email}!"}
                db.log_alert("TEST_USER", "test_session", "MEDIUM", 0.55, "email", recipient_email, "sent", "Delivered live test email.")
            except Exception as e:
                results["email"] = {"status": "failed", "message": f"SMTP Error: {str(e)}"}
                db.log_alert("TEST_USER", "test_session", "MEDIUM", 0.55, "email", recipient_email, "failed", str(e))
        else:
            target = recipient_email or "No email provided (simulation active)"
            results["email"] = {"status": "simulated", "message": f"Simulated email alert registered for '{target}' (enter SMTP password to send live)."}
            db.log_alert("TEST_USER", "test_session", "MEDIUM", 0.55, "email", target, "simulated", "Simulated test email.")

    # 2. Test SMS
    if settings.get("sms_enabled", 1):
        recipient_phone = settings.get("alert_phone", "").strip()
        twilio_sid = settings.get("twilio_sid", "").strip()
        twilio_token = settings.get("twilio_token", "").strip()
        twilio_from = settings.get("twilio_from", "").strip()

        sms_body = f"[KeyStro Test Alert] Verification test successful at {now_str}. SMS notifications are active."

        if recipient_phone and twilio_sid and twilio_token and twilio_from:
            try:
                twilio_url = f"https://api.twilio.com/2010-04-01/Accounts/{twilio_sid}/Messages.json"
                post_data = urllib.parse.urlencode({
                    "From": twilio_from,
                    "To": recipient_phone,
                    "Body": sms_body
                }).encode("utf-8")

                req = urllib.request.Request(twilio_url, data=post_data, method="POST")
                auth_str = f"{twilio_sid}:{twilio_token}"
                encoded_auth = base64.b64encode(auth_str.encode("utf-8")).decode("utf-8")
                req.add_header("Authorization", f"Basic {encoded_auth}")

                with urllib.request.urlopen(req, timeout=8) as resp:
                    if resp.getcode() in (200, 201):
                        results["sms"] = {"status": "sent", "message": f"Real test SMS delivered to {recipient_phone}!"}
                        db.log_alert("TEST_USER", "test_session", "MEDIUM", 0.55, "sms", recipient_phone, "sent", "Delivered live test SMS.")
                    else:
                        results["sms"] = {"status": "failed", "message": f"Twilio API Error Code {resp.getcode()}"}
            except Exception as e:
                results["sms"] = {"status": "failed", "message": f"Twilio Error: {str(e)}"}
                db.log_alert("TEST_USER", "test_session", "MEDIUM", 0.55, "sms", recipient_phone, "failed", str(e))
        else:
            target = recipient_phone or "No phone provided (simulation active)"
            results["sms"] = {"status": "simulated", "message": f"Simulated SMS alert registered for '{target}' (enter Twilio keys to send live)."}
            db.log_alert("TEST_USER", "test_session", "MEDIUM", 0.55, "sms", target, "simulated", "Simulated test SMS.")

    return results
