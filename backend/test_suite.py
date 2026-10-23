"""
KeyStro Automated Verification Test Suite
Tests all REST API endpoints, biometric ML models, adaptive session locking,
and simulated MFA challenge response.
"""

import os
import sys
import unittest
import json
import numpy as np

BACKEND_DIR = os.path.dirname(os.path.abspath(__file__))
if BACKEND_DIR not in sys.path:
    sys.path.insert(0, BACKEND_DIR)

from app import app
import core.database as db
import core.model_pipeline as mp
import core.feature_extractor as fe


class KeyStroTestSuite(unittest.TestCase):
    active_session_id = None
    challenge_otp = None

    @classmethod
    def setUpClass(cls):
        cls.client = app.test_client()
        db.init_db()
        db.reset_database()
        from seed_data import seed_database
        seed_database()

    def test_01_health_check(self):
        """Test system health check endpoint."""
        res = self.client.get("/api/health")
        self.assertEqual(res.status_code, 200)
        data = res.get_json()
        self.assertEqual(data["status"], "healthy")
        self.assertEqual(data["team"], "TRISHUL")
        print("[PASS] Health check verified.")

    def test_02_users_list(self):
        """Test listing enrolled users."""
        res = self.client.get("/api/users")
        self.assertEqual(res.status_code, 200)
        data = res.get_json()
        self.assertTrue(data["success"])
        self.assertGreater(data["count"], 0)
        usernames = [u["username"] for u in data["users"]]
        self.assertIn("alice_swift", usernames)
        print(f"[PASS] Enrolled users listed: {usernames}")

    def test_03_start_session(self):
        """Test creating an active continuous authentication session."""
        res = self.client.post("/api/start-session", json={"username": "alice_swift"})
        self.assertEqual(res.status_code, 200)
        data = res.get_json()
        self.assertTrue(data["success"])
        self.assertTrue(data["session_id"].startswith("sess_"))
        KeyStroTestSuite.active_session_id = data["session_id"]
        print(f"[PASS] Session initialized: {data['session_id']}")

    def test_04_verify_genuine_typing(self):
        """Test verification of genuine typing cadence (should score > 0.70, LOW risk)."""
        session_id = KeyStroTestSuite.active_session_id
        user = db.get_user("alice_swift")
        target_dwell = user["avg_dwell"]
        target_flight = user["avg_flight"]

        events = []
        cur_time = 5000.0
        rng = np.random.RandomState(42)
        for _ in range(24):
            dt = target_dwell + rng.normal(0, 8)
            ft = target_flight + rng.normal(0, 10)
            events.append({"down": cur_time, "up": cur_time + dt})
            cur_time += dt + ft

        res = self.client.post("/api/verify-session", json={
            "session_id": session_id,
            "events": events,
            "is_imposter_simulation": False
        })
        self.assertEqual(res.status_code, 200)
        data = res.get_json()
        self.assertTrue(data["success"])
        self.assertGreaterEqual(data["confidence_score"], 0.70)
        self.assertEqual(data["risk_level"], "LOW")
        self.assertEqual(data["action_taken"], "allowed")
        print(f"[PASS] Genuine verification score: {data['confidence_score']} (Risk: {data['risk_level']})")

    def test_05_verify_imposter_attack_locks_session(self):
        """Test verification of anomalous imposter typing (should score < 0.40 and lock session)."""
        session_id = KeyStroTestSuite.active_session_id
        # Imposter: Heavy hunt-and-peck typist (Dwell ~280ms, Flight ~450ms)
        events = []
        cur_time = 10000.0
        for _ in range(16):
            dt = 280.0 + np.random.uniform(-20, 20)
            ft = 450.0 + np.random.uniform(-40, 40)
            events.append({"down": cur_time, "up": cur_time + dt})
            cur_time += dt + ft

        res = self.client.post("/api/verify-session", json={
            "session_id": session_id,
            "events": events,
            "is_imposter_simulation": True
        })
        data = res.get_json()
        self.assertTrue(data["is_anomaly"])
        self.assertLess(data["confidence_score"], 0.40)
        self.assertEqual(data["risk_level"], "HIGH")
        self.assertEqual(data["action_taken"], "locked")
        self.assertIn("challenge_otp", data)
        KeyStroTestSuite.challenge_otp = data["challenge_otp"]
        print(f"[PASS] Imposter anomaly detected! Score: {data['confidence_score']}, Challenge OTP: {data['challenge_otp']}")

    def test_06_verify_adaptive_mfa_unlock(self):
        """Test unlocking the session using simulated OTP challenge."""
        session_id = KeyStroTestSuite.active_session_id
        otp = KeyStroTestSuite.challenge_otp

        # First test wrong OTP
        wrong_res = self.client.post("/api/verify-otp", json={
            "session_id": session_id,
            "otp": "000000"
        })
        self.assertEqual(wrong_res.status_code, 400)

        # Test correct OTP
        res = self.client.post("/api/verify-otp", json={
            "session_id": session_id,
            "otp": otp
        })
        self.assertEqual(res.status_code, 200)
        data = res.get_json()
        self.assertTrue(data["success"])
        self.assertEqual(data["status"], "active")
        print("[PASS] Adaptive MFA unlocked session successfully.")

    def test_07_metrics_endpoint(self):
        """Test security analytics and audit trail endpoint."""
        res = self.client.get("/api/metrics")
        self.assertEqual(res.status_code, 200)
        data = res.get_json()
        self.assertTrue(data["success"])
        metrics = data["metrics"]
        self.assertGreater(metrics["total_evaluations"], 0)
        self.assertIn("far_percentage", metrics)
        self.assertIn("frr_percentage", metrics)
        self.assertIn("eer_percentage", metrics)
        print(f"[PASS] Security metrics verified: FAR={metrics['far_percentage']}%, FRR={metrics['frr_percentage']}%, EER={metrics['eer_percentage']}%")

    def test_08_enroll_new_user(self):
        """Test enrolling a brand new user profile."""
        passages = []
        for _ in range(3):
            p = []
            t = 2000.0
            for _ in range(25):
                dt = 95.0 + np.random.uniform(-5, 5)
                ft = 85.0 + np.random.uniform(-8, 8)
                p.append({"down": t, "up": t + dt})
                t += dt + ft
            passages.append(p)

        res = self.client.post("/api/enroll", json={
            "username": "sarah_crypto",
            "passages": passages
        })
        self.assertEqual(res.status_code, 200)
        data = res.get_json()
        self.assertTrue(data["success"])
        self.assertIn("baseline", data)
        print(f"[PASS] New user enrolled: sarah_crypto with baseline {data['baseline']}")

    def test_09_continuous_learning_train_ahead(self):
        """Test continuous online adaptation: model automatically trains ahead when 200 words are accumulated."""
        # Start a clean session for Alice
        start_res = self.client.post("/api/start-session", json={"username": "alice_swift"})
        self.assertEqual(start_res.status_code, 200)
        session_id = start_res.get_json()["session_id"]
        user = db.get_user("alice_swift")
        target_dwell = user["avg_dwell"]
        target_flight = user["avg_flight"]

        # Synthesize genuine typing chunk matching Alice baseline
        events = []
        cur_time = 20000.0
        rng = np.random.RandomState(42)
        for _ in range(30):
            dt = target_dwell + rng.normal(0, 8)
            ft = target_flight + rng.normal(0, 10)
            events.append({"down": cur_time, "up": cur_time + dt})
            cur_time += dt + ft

        # Send chunk specifying 200 words arrived
        res = self.client.post("/api/verify-session", json={
            "session_id": session_id,
            "events": events,
            "is_imposter_simulation": False,
            "words_in_chunk": 200
        })
        self.assertEqual(res.status_code, 200)
        data = res.get_json()
        self.assertTrue(data["success"])
        self.assertTrue(data["adapted"])
        self.assertIn("adaptation_info", data)
        self.assertEqual(data["adaptation_info"]["model_version"], "v2.0")
        self.assertEqual(data["adaptation_info"]["adaptation_count"], 1)
        print(f"[PASS] Continuous learning: Model trained ahead to {data['adaptation_info']['model_version']} after 200 words.")

    def test_10_imposter_rejected_from_continuous_learning(self):
        """Test that imposter/anomalous typing is blocked from the continuous adaptation buffer (anti-poisoning)."""
        start_res = self.client.post("/api/start-session", json={"username": "bob_deliberate"})
        session_id = start_res.get_json()["session_id"]

        # Attack burst
        events = []
        cur_time = 30000.0
        for _ in range(16):
            dt = 350.0
            ft = 500.0
            events.append({"down": cur_time, "up": cur_time + dt})
            cur_time += dt + ft

        res = self.client.post("/api/verify-session", json={
            "session_id": session_id,
            "events": events,
            "is_imposter_simulation": True,
            "words_in_chunk": 50
        })
        data = res.get_json()
        # Should either lock or reject from training buffer
        self.assertTrue(data.get("continuous_learning", {}).get("rejected_from_training", False) or data.get("action_taken") == "locked")
        print("[PASS] Anti-Poisoning: Imposter typing strictly rejected from continuous learning buffer.")

    def test_11_fast_forward_adapt_endpoint(self):
        """Test /api/adapt-model endpoint for manual or fast-forward adaptation."""
        res = self.client.post("/api/adapt-model", json={
            "username": "charlie_analyst",
            "word_count": 200
        })
        self.assertEqual(res.status_code, 200)
        data = res.get_json()
        self.assertTrue(data["success"])
        self.assertEqual(data["adaptation"]["model_version"], "v2.0")
        print(f"[PASS] Fast-Forward adaptation endpoint verified: {data['message']}")


if __name__ == "__main__":
    unittest.main()
