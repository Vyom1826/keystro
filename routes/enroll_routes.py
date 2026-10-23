"""
KeyStro Enrollment Routes Blueprint
Handles user registration, typing calibration data collection, and per-user model training.
"""

import logging
from flask import request, jsonify
from routes import enroll_bp
import core.database as db
import core.model_pipeline as mp
import core.feature_extractor as fe

logger = logging.getLogger("KeyStro.Enroll")


@enroll_bp.route("/api/users", methods=["GET"])
def get_users():
    """Returns list of enrolled users."""
    users = db.list_users()
    return jsonify({
        "success": True,
        "count": len(users),
        "users": users
    })


@enroll_bp.route("/api/enroll", methods=["POST"])
def enroll_user():
    """
    Enroll a new user with baseline keystroke timing passages.
    Payload:
    {
        "username": "alice",
        "passages": [
            [ {"down": t, "up": t}, ... ],
            [ {"down": t, "up": t}, ... ],
            [ {"down": t, "up": t}, ... ]
        ]
    }
    """
    data = request.get_json() or {}
    username = (data.get("username") or "").strip()
    passages = data.get("passages", [])

    if not username:
        return jsonify({"success": False, "error": "Username is required."}), 400

    if not passages or len(passages) < 2:
        return jsonify({
            "success": False,
            "error": "At least 2-3 calibration passages are required for robust baseline modeling."
        }), 400

    # Ensure total keystrokes across passages is sufficient
    total_events = sum(len(p) for p in passages)
    if total_events < 25:
        return jsonify({
            "success": False,
            "error": f"Insufficient keystroke data ({total_events} keystrokes provided). Please type more characters to capture rhythm accurately."
        }), 400

    try:
        # Save raw passages to enrollment_samples table for audit/re-training
        for idx, passage in enumerate(passages):
            passage_features = fe.extract_features(passage)
            db.save_enrollment_sample(username, idx + 1, passage, passage_features)

        # Train dual-mode ML pipeline (IsolationForest + RandomForest)
        train_res = mp.train_user_models(username, passages)

        # Save user profile in database
        baseline = train_res["baseline_stats"]
        db.save_user(
            username=username,
            total_samples=train_res["sample_count"],
            avg_dwell=baseline["dwell_mean"],
            avg_flight=baseline["flight_mean"],
            avg_speed=baseline["speed_kpm"],
            model_path=train_res["model_path"]
        )

        logger.info(f"User '{username}' successfully enrolled. Baseline: {baseline}")

        return jsonify({
            "success": True,
            "message": f"User '{username}' successfully enrolled with {train_res['sample_count']} baseline samples.",
            "username": username,
            "baseline": baseline,
            "calibration": train_res["calibration"]
        })

    except Exception as e:
        logger.error(f"Enrollment error for {username}: {str(e)}", exc_info=True)
        return jsonify({"success": False, "error": str(e)}), 500
