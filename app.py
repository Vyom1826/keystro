"""
KeyStro - AI-Powered Continuous Keystroke Authentication System
Root Application Entry Point
"""

import os
import sys

# Ensure backend directory is in python module search path
PROJECT_ROOT = os.path.dirname(os.path.abspath(__file__))
BACKEND_DIR = os.path.join(PROJECT_ROOT, "backend")
if BACKEND_DIR not in sys.path:
    sys.path.insert(0, BACKEND_DIR)

from backend.app import app

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    print("\n" + "=" * 65)
    print("  [+] KeyStro AI Continuous Keystroke Authentication is LIVE!")
    print(f"  >>> Dashboard URL: http://127.0.0.1:{port}")
    print("  >>> Frontend: ./frontend  |  Backend: ./backend  |  Models: ./models")
    print("=" * 65 + "\n")
    app.run(host="0.0.0.0", port=port, debug=False)
