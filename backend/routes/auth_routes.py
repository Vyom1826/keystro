"""
KeyStro Authentication Routes Blueprint
Handles user registration, login verification, and seamless onboarding to biometric enrollment.
"""

from flask import Blueprint, request, jsonify
import core.database as db

auth_bp = Blueprint("auth", __name__)


@auth_bp.route("/api/auth/register", methods=["POST"])
def register():
    """
    Registers a new user with full name, email, phone number, and password.
    Directs the user to the Biometric Enrollment calibration flow.
    Payload:
    {
        "full_name": "Vyom Singhal",
        "username": "vyomsinghal",
        "email": "vyom@example.com",
        "phone": "+919876543210",
        "password": "secretpassword"
    }
    """
    data = request.get_json() or {}
    full_name = data.get("full_name", "").strip()
    username = data.get("username", "").strip()
    email = data.get("email", "").strip()
    phone = data.get("phone", "").strip()
    password = data.get("password", "").strip()

    if not username:
        return jsonify({"success": False, "error": "Username is required."}), 400

    if not password:
        return jsonify({"success": False, "error": "Password is required."}), 400

    res = db.register_user(
        username=username,
        full_name=full_name,
        email=email,
        phone=phone,
        password=password
    )

    if not res.get("success"):
        return jsonify(res), 400

    return jsonify({
        "success": True,
        "message": f"Welcome, {full_name or username}! Account created. Let's calibrate your keystroke rhythm.",
        "user": res["user"],
        "next": "enrollment"
    }), 201


@auth_bp.route("/api/auth/login", methods=["POST"])
def login():
    """
    Authenticates an existing user via username or email and password.
    Payload:
    {
        "identifier": "vyomsinghal" (or "vyom@example.com"),
        "password": "secretpassword"
    }
    """
    data = request.get_json() or {}
    identifier = data.get("identifier", "").strip()
    password = data.get("password", "").strip()

    if not identifier:
        return jsonify({"success": False, "error": "Username or email is required."}), 400

    res = db.authenticate_user(identifier, password)
    if not res.get("success"):
        return jsonify(res), 401

    is_enrolled = res.get("is_enrolled", False)
    user = res["user"]

    return jsonify({
        "success": True,
        "message": f"Welcome back, {user.get('full_name') or user['username']}!",
        "user": user,
        "is_enrolled": is_enrolled,
        "next": "workspace" if is_enrolled else "enrollment"
    })
