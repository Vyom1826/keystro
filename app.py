"""
KeyStro - AI-Powered Continuous Keystroke Authentication System
Root Application Entry Point
"""

import os
import sys
import socket

# Ensure backend directory is in python module search path
PROJECT_ROOT = os.path.dirname(os.path.abspath(__file__))
BACKEND_DIR = os.path.join(PROJECT_ROOT, "backend")
if BACKEND_DIR not in sys.path:
    sys.path.insert(0, BACKEND_DIR)

from backend.app import app


def find_available_port(preferred_port=5000):
    for candidate in [preferred_port, 5001, 5050, 8080]:
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
            s.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            try:
                s.bind(("0.0.0.0", candidate))
                return candidate
            except OSError:
                continue
    return preferred_port


if __name__ == "__main__":
    env_port = os.environ.get("PORT")
    port = int(env_port) if env_port else find_available_port(5000)
    print("\n" + "=" * 65)
    print("  [+] KeyStro AI Continuous Keystroke Authentication is LIVE!")
    print(f"  >>> Dashboard URL: http://127.0.0.1:{port}")
    print("  >>> Frontend: ./frontend  |  Backend: ./backend  |  Models: ./models")
    print("=" * 65 + "\n")
    app.run(host="0.0.0.0", port=port, debug=False)
