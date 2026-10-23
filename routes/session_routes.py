"""
KeyStro Session Routes Blueprint
Handles continuous authentication session lifecycle:
- Starting active sessions
- Real-time keystroke timing chunk verification
- Adaptive MFA OTP challenge verification
"""

import uuid
import logging
from flask import request, jsonify
from routes import session_bp
import core.database as db
import core.model_pipeline as mp

logger = logging.getLogger("KeyStro.Session")

# In-memory continuous learning session buffers
_SESSION_BUFFERS = {}

def get_session_buffer(session_id: str, username: str) -> dict:
    if session_id not in _SESSION_BUFFERS:
        user = db.get_user(username) or {}
        _SESSION_BUFFERS[session_id] = {
            "genuine_events": [],
            "accumulated_words": 0,
            "total_words_adapted": user.get("words_adapted", 0),
            "adaptation_count": user.get("adaptation_count", 0),
            "model_version": user.get("model_version", "v1.0")
        }
    return _SESSION_BUFFERS[session_id]


@session_bp.route("/api/start-session", methods=["POST"])
def start_session():
    """
    Initiates an active continuous authentication session for an enrolled user.
    Payload: { "username": "alice" }
    """
    data = request.get_json() or {}
    username = (data.get("username") or "").strip()

    if not username:
        return jsonify({"success": False, "error": "Username is required."}), 400

    user = db.get_user(username)
    if not user:
        return jsonify({
            "success": False,
            "error": f"User '{username}' is not enrolled. Please complete enrollment first."
        }), 404

    session_id = f"sess_{uuid.uuid4().hex[:12]}"
    db.create_session(session_id, username)

    # Initialize continuous learning buffer for this session
    buffer = get_session_buffer(session_id, username)
    buffer["genuine_events"] = []
    buffer["accumulated_words"] = 0
    buffer["adaptation_count"] = user.get("adaptation_count", 0)
    buffer["model_version"] = user.get("model_version", "v1.0")
    buffer["total_words_adapted"] = user.get("words_adapted", 0)

    logger.info(f"Started session {session_id} for user '{username}' (Model {buffer['model_version']}).")

    return jsonify({
        "success": True,
        "session_id": session_id,
        "username": username,
        "user_profile": {
            "avg_dwell": user["avg_dwell"],
            "avg_flight": user["avg_flight"],
            "avg_speed": user["avg_speed"],
            "status": user["status"],
            "model_version": buffer["model_version"],
            "adaptation_count": buffer["adaptation_count"],
            "words_adapted": buffer["total_words_adapted"]
        },
        "continuous_learning": {
            "words_accumulated": 0,
            "words_threshold": 200,
            "progress_percent": 0,
            "model_version": buffer["model_version"],
            "adaptation_count": buffer["adaptation_count"],
            "total_words_adapted": buffer["total_words_adapted"]
        }
    })


@session_bp.route("/api/verify-session", methods=["POST"])
def verify_session():
    """
    Continuously verifies incoming keystroke timing chunks against the session user model.
    Payload:
    {
        "session_id": "sess_...",
        "events": [ {"down": 1200, "up": 1290}, ... ],
        "is_imposter_simulation": false
    }
    """
    data = request.get_json() or {}
    session_id = (data.get("session_id") or "").strip()
    events = data.get("events", [])
    is_imposter = bool(data.get("is_imposter_simulation", False))

    if not session_id:
        return jsonify({"success": False, "error": "session_id is required."}), 400

    session = db.get_session(session_id)
    if not session:
        return jsonify({"success": False, "error": "Session not found or expired."}), 404

    # If already locked/challenged, require OTP resolution before further typing evaluation
    if session["status"] == "challenged":
        return jsonify({
            "success": False,
            "status": "challenged",
            "action_taken": "locked",
            "error": "Session is locked pending Adaptive MFA Verification.",
            "challenge_otp": session.get("challenge_otp")
        }), 403

    if len(events) < 8:
        return jsonify({
            "success": False,
            "error": "Keystroke chunk too small. Need at least 8-15 keystrokes for reliable statistical evaluation."
        }), 400

    username = session["username"]

    try:
        # Retrieve recent score history for this session for temporal EMA smoothing
        recent_logs = db.get_recent_logs(session_id=session_id, limit=5)
        score_history = [log["score"] for log in recent_logs]

        # Evaluate through ML pipeline directly against session user's enrolled profile
        eval_result = mp.evaluate_keystroke_chunk(
            username=username,
            raw_events=events,
            session_history=score_history
        )

        score = eval_result["confidence_score"]
        raw_score = eval_result["raw_chunk_score"]
        risk_level = eval_result["risk_level"]
        action_taken = eval_result["action_taken"]
        is_anomaly = eval_result["is_anomaly"]
        status_message = eval_result["status_message"]

        # Anti-False-Lock consecutive anomaly logic:
        # Injected attacks (is_imposter = True) or severe anomalies (< 0.28) lock immediately.
        # Moderate hesitation (< 0.40) warns on first occurrence, locks only on consecutive anomalies.
        session_anomaly_count = session.get("anomaly_count", 0)
        if is_imposter:
            score = min(score, 0.22)
            action_taken = "locked"
            risk_level = "HIGH"
            is_anomaly = True
            status_message = "Imposter attack burst injected! Session locked immediately for identity verification."
        elif score < 0.28:
            action_taken = "locked"
            risk_level = "HIGH"
            is_anomaly = True
            status_message = "Severe biometric anomaly detected! Session locked for identity verification."
        elif score < 0.40:
            if session_anomaly_count >= 1:
                action_taken = "locked"
                risk_level = "HIGH"
                is_anomaly = True
                status_message = "Persistent biometric rhythm anomaly across consecutive chunks. Adaptive MFA required."
            else:
                action_taken = "warned"
                risk_level = "MEDIUM"
                is_anomaly = True
                status_message = "Rhythm drift or finger hesitation detected. Elevated monitoring active."
        elif score < 0.70:
            action_taken = "warned"
            risk_level = "MEDIUM"
            is_anomaly = False
            status_message = "Mild cadence drift detected. Monitoring active."
        else:
            action_taken = "allowed"
            risk_level = "LOW"
            is_anomaly = False
            status_message = "Typing rhythm authenticated. Active session verified."

        # Continuous Online Learning Engine ("Train Ahead" every 200 verified words)
        buffer = get_session_buffer(session_id, username)
        adapted = False
        adaptation_info = None

        # Imposter defense: only verified genuine typing (score >= 0.60 & not imposter) is admitted
        if not is_imposter and score >= 0.60:
            words_in_chunk = data.get("words_in_chunk")
            if words_in_chunk is None or words_in_chunk <= 0:
                words_in_chunk = max(1, round(len(events) / 5.0))

            buffer["genuine_events"].extend(events)
            buffer["accumulated_words"] += words_in_chunk

            ADAPTATION_WORD_THRESHOLD = 200
            if buffer["accumulated_words"] >= ADAPTATION_WORD_THRESHOLD:
                # Retrain ahead!
                adapt_res = mp.adapt_user_model(
                    username=username,
                    new_genuine_events=buffer["genuine_events"],
                    words_count=buffer["accumulated_words"]
                )
                buffer["total_words_adapted"] += buffer["accumulated_words"]
                words_just_adapted = buffer["accumulated_words"]
                buffer["accumulated_words"] = 0
                buffer["genuine_events"] = []
                buffer["adaptation_count"] = adapt_res["adaptation_count"]
                buffer["model_version"] = adapt_res["model_version"]

                adapted = True
                adaptation_info = {
                    "adapted": True,
                    "model_version": adapt_res["model_version"],
                    "adaptation_count": adapt_res["adaptation_count"],
                    "words_adapted": words_just_adapted,
                    "total_words_adapted": buffer["total_words_adapted"],
                    "new_baseline": adapt_res["baseline_stats"],
                    "message": f"Continuous Learning Activated: Model trained ahead on {words_just_adapted} verified words ({adapt_res['model_version']})!"
                }

                # Mark action as adapted in the audit record
                action_taken = "adapted"
                logger.info(f"MODEL ADAPTED: User '{username}' model trained ahead to {adapt_res['model_version']}.")

        # Update session table in database
        sess_update = db.update_session_evaluation(
            session_id=session_id,
            score=score,
            risk_level=risk_level,
            is_anomaly=is_anomaly,
            action_taken=action_taken
        )

        # Log telemetry record
        db.log_verification(
            session_id=session_id,
            username=username,
            score=score,
            risk_level=risk_level,
            features=eval_result["features"],
            is_anomaly=is_anomaly,
            action_taken=action_taken,
            is_imposter=is_imposter
        )

        response_payload = {
            "success": True,
            "session_id": session_id,
            "username": username,
            "confidence_score": score,
            "risk_level": risk_level,
            "action_taken": action_taken,
            "is_anomaly": is_anomaly,
            "status_message": eval_result["status_message"],
            "session_status": sess_update["status"] if sess_update else session["status"],
            "model_breakdown": eval_result["model_breakdown"],
            "baseline_comparison": eval_result["baseline_comparison"],
            "features": eval_result["features"],
            "adapted": adapted,
            "continuous_learning": {
                "words_accumulated": buffer["accumulated_words"],
                "words_threshold": 200,
                "progress_percent": min(100, round((buffer["accumulated_words"] / 200) * 100)),
                "adaptation_count": buffer["adaptation_count"],
                "model_version": buffer["model_version"],
                "total_words_adapted": buffer["total_words_adapted"],
                "rejected_from_training": bool(is_imposter or score < 0.70)
            }
        }

        if adaptation_info:
            response_payload["adaptation_info"] = adaptation_info

        # If challenged, supply the challenge OTP so UI can simulate MFA alert
        if sess_update and sess_update.get("challenge_otp"):
            response_payload["challenge_otp"] = sess_update["challenge_otp"]
            logger.warning(f"SESSION LOCK: Session {session_id} challenged. OTP generated: {sess_update['challenge_otp']}")

        return jsonify(response_payload)

    except Exception as e:
        logger.error(f"Verification error in session {session_id}: {str(e)}", exc_info=True)
        return jsonify({"success": False, "error": str(e)}), 500


@session_bp.route("/api/adapt-model", methods=["POST"])
def force_adapt_model():
    """
    Fast-Forward / Manual Continuous Adaptation Endpoint:
    Simulates accumulating 200 verified words of genuine cadence and trains the model ahead.
    Payload: { "session_id": "sess_...", "word_count": 200 }
    """
    data = request.get_json() or {}
    session_id = (data.get("session_id") or "").strip()
    words_count = int(data.get("word_count", 200))

    session = db.get_session(session_id) if session_id else None
    username = session["username"] if session else (data.get("username") or "").strip()

    if not username:
        return jsonify({"success": False, "error": "Valid session_id or username required."}), 400

    user = db.get_user(username)
    if not user:
        return jsonify({"success": False, "error": f"User '{username}' not found."}), 404

    from seed_data import generate_synthetic_passage
    dwell_target = user.get("avg_dwell", 85.0)
    flight_target = user.get("avg_flight", 80.0)

    # 200 words equates to ~1000 keystrokes (200 * 5)
    synthetic_stream = generate_synthetic_passage(
        mean_dwell=dwell_target,
        std_dwell=10.0,
        mean_flight=flight_target,
        std_flight=12.0,
        keystroke_count=min(250, max(50, words_count * 2))
    )

    adapt_res = mp.adapt_user_model(username, synthetic_stream, words_count=words_count)

    buf = get_session_buffer(session_id or f"sess_{username}", username)
    buf["total_words_adapted"] += words_count
    buf["accumulated_words"] = 0
    buf["genuine_events"] = []
    buf["adaptation_count"] = adapt_res["adaptation_count"]
    buf["model_version"] = adapt_res["model_version"]

    if session_id:
        db.log_verification(
            session_id=session_id,
            username=username,
            score=0.96,
            risk_level="LOW",
            features={
                "dwell_mean": adapt_res["baseline_stats"]["dwell_mean"],
                "flight_mean": adapt_res["baseline_stats"]["flight_mean"],
                "ikl_mean": adapt_res["baseline_stats"]["dwell_mean"] + adapt_res["baseline_stats"]["flight_mean"],
                "speed_kpm": adapt_res["baseline_stats"]["speed_kpm"]
            },
            is_anomaly=False,
            action_taken="adapted",
            is_imposter=False
        )

    return jsonify({
        "success": True,
        "message": f"Continuous Learning Activated: Model retrained ahead on {words_count} verified words to {adapt_res['model_version']}.",
        "adaptation": adapt_res,
        "continuous_learning": {
            "words_accumulated": 0,
            "words_threshold": 200,
            "progress_percent": 0,
            "adaptation_count": adapt_res["adaptation_count"],
            "model_version": adapt_res["model_version"],
            "total_words_adapted": buf["total_words_adapted"]
        }
    })


@session_bp.route("/api/verify-otp", methods=["POST"])
def verify_otp():
    """
    Adaptive Verification Challenge Endpoint:
    Unlocks a locked session if the correct 6-digit MFA OTP is provided.
    Payload: { "session_id": "sess_...", "otp": "123456" }
    """
    data = request.get_json() or {}
    session_id = (data.get("session_id") or "").strip()
    otp = (data.get("otp") or "").strip()

    if not session_id or not otp:
        return jsonify({"success": False, "error": "session_id and otp are required."}), 400

    success, message = db.verify_session_otp(session_id, otp)
    status_code = 200 if success else 400

    return jsonify({
        "success": success,
        "message": message,
        "session_id": session_id,
        "status": "active" if success else "challenged"
    }), status_code


@session_bp.route("/api/retrain-model", methods=["POST"])
def retrain_model_endpoint():
    """
    Retrains a user's biometric ML model directly from all stored calibration passages in SQLite.
    Refits with strict exclusion zones and realistic human variability to prevent false rejections.
    Payload: { "username": "alice_swift" }
    """
    data = request.get_json() or {}
    username = (data.get("username") or "").strip()

    if not username:
        return jsonify({"success": False, "error": "Username is required."}), 400

    try:
        train_res = mp.retrain_user_from_enrollment(username)
        logger.info(f"Retrained biometric model for '{username}' with updated boundaries: {train_res['baseline_stats']}")
        return jsonify({
            "success": True,
            "message": f"Biometric model for '{username}' successfully retrained with updated boundaries.",
            "username": username,
            "baseline": train_res["baseline_stats"]
        })
    except Exception as e:
        logger.error(f"Failed to retrain model for {username}: {e}", exc_info=True)
        return jsonify({"success": False, "error": str(e)}), 500
