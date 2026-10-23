"""
KeyStro Seed Data Generator
Pre-populates the database with realistic synthetic user typing profiles,
trained models, and validation telemetry logs for immediate out-of-the-box demonstration.
"""

import os
import random
import numpy as np
from datetime import datetime, timedelta

import sys
CURRENT_DIR = os.path.dirname(os.path.abspath(__file__))
if CURRENT_DIR not in sys.path:
    sys.path.insert(0, CURRENT_DIR)

import core.database as db
import core.model_pipeline as mp
import core.feature_extractor as fe

SAMPLE_TEXTS = [
    "The quick brown fox jumps over the lazy dog in the cyber laboratory.",
    "Continuous keystroke authentication protects active cloud sessions without interruption.",
    "Behavioral biometrics evaluate typing rhythm flight latency and key dwell durations.",
    "Adaptive multi factor authentication triggers verification when anomaly scores spike.",
    "Security zero trust architecture verifies user identity dynamically throughout the session."
]


def generate_synthetic_passage(
    mean_dwell: float,
    std_dwell: float,
    mean_flight: float,
    std_flight: float,
    pause_chance: float = 0.05,
    pause_duration: float = 400.0,
    keystroke_count: int = 70
):
    """Generates an array of keystroke timing dicts: [{'down': t_down, 'up': t_up}, ...]"""
    events = []
    current_time = 1000.0

    for i in range(keystroke_count):
        # Dwell time
        dt = max(25.0, np.random.normal(mean_dwell, std_dwell))
        t_down = current_time
        t_up = t_down + dt

        events.append({
            "down": round(t_down, 1),
            "up": round(t_up, 1)
        })

        # Flight time to next key
        if np.random.random() < pause_chance:
            ft = np.random.normal(pause_duration, 80.0)
        else:
            ft = np.random.normal(mean_flight, std_flight)

        ft = max(10.0, ft)
        current_time = t_up + ft

    return events


def seed_database():
    print("=" * 60)
    print("KeyStro - Seeding Synthetic Profiles & Calibration Data")
    print("=" * 60)

    db.init_db()

    # Pre-defined typist personas
    personas = [
        {
            "username": "alice_swift",
            "title": "Alice (High-Speed Software Engineer)",
            "dwell": (80.0, 12.0),
            "flight": (65.0, 18.0),
            "pause_chance": 0.03,
            "pause_duration": 350.0
        },
        {
            "username": "bob_deliberate",
            "title": "Bob (Deliberate Compliance Officer)",
            "dwell": (165.0, 25.0),
            "flight": (210.0, 35.0),
            "pause_chance": 0.10,
            "pause_duration": 550.0
        },
        {
            "username": "charlie_analyst",
            "title": "Charlie (Financial Risk Analyst)",
            "dwell": (115.0, 18.0),
            "flight": (125.0, 24.0),
            "pause_chance": 0.06,
            "pause_duration": 420.0
        }
    ]

    for p in personas:
        username = p["username"]
        print(f"\n[+] Enrolling {p['title']} ({username})...")

        # Generate 4 calibration passages
        passages = []
        for i in range(4):
            passage = generate_synthetic_passage(
                mean_dwell=p["dwell"][0],
                std_dwell=p["dwell"][1],
                mean_flight=p["flight"][0],
                std_flight=p["flight"][1],
                pause_chance=p["pause_chance"],
                pause_duration=p["pause_duration"],
                keystroke_count=random.randint(65, 85)
            )
            passages.append(passage)
            feat = fe.extract_features(passage)
            db.save_enrollment_sample(username, i + 1, passage, feat)

        # Train dual-mode model
        train_res = mp.train_user_models(username, passages)
        baseline = train_res["baseline_stats"]

        db.save_user(
            username=username,
            total_samples=train_res["sample_count"],
            avg_dwell=baseline["dwell_mean"],
            avg_flight=baseline["flight_mean"],
            avg_speed=baseline["speed_kpm"],
            model_path=train_res["model_path"]
        )
        print(f"    Trained: Dwell={baseline['dwell_mean']}ms | Flight={baseline['flight_mean']}ms | Speed={baseline['speed_kpm']} KPM")

    print("\n[+] Generating initial telemetry logs for realistic dashboard metrics...")

    # Create an initial demo session for alice_swift
    demo_session_id = "sess_demo_alice_01"
    db.create_session(demo_session_id, "alice_swift")

    # Log 15 genuine typing evaluations
    alice_p = personas[0]
    for step in range(15):
        chunk = generate_synthetic_passage(
            mean_dwell=alice_p["dwell"][0] + np.random.normal(0, 3),
            std_dwell=alice_p["dwell"][1],
            mean_flight=alice_p["flight"][0] + np.random.normal(0, 5),
            std_flight=alice_p["flight"][1],
            keystroke_count=18
        )
        eval_res = mp.evaluate_keystroke_chunk("alice_swift", chunk)
        db.log_verification(
            session_id=demo_session_id,
            username="alice_swift",
            score=eval_res["confidence_score"],
            risk_level=eval_res["risk_level"],
            features=eval_res["features"],
            is_anomaly=eval_res["is_anomaly"],
            action_taken=eval_res["action_taken"],
            is_imposter=False
        )

    # Log 4 imposter evaluations (simulating an unauthorized intruder attempting to use Alice's session)
    for step in range(4):
        # Intruder types much slower with heavy dwell
        imposter_chunk = generate_synthetic_passage(
            mean_dwell=260.0,
            std_dwell=40.0,
            mean_flight=340.0,
            std_flight=70.0,
            keystroke_count=18
        )
        eval_res = mp.evaluate_keystroke_chunk("alice_swift", imposter_chunk)
        db.log_verification(
            session_id=demo_session_id,
            username="alice_swift",
            score=eval_res["confidence_score"],
            risk_level=eval_res["risk_level"],
            features=eval_res["features"],
            is_anomaly=eval_res["is_anomaly"],
            action_taken=eval_res["action_taken"],
            is_imposter=True
        )

    metrics = db.get_security_metrics()
    print("\n[+] Initial Seed Metrics Computed:")
    print(f"    Total Evaluations: {metrics['total_evaluations']}")
    print(f"    FAR: {metrics['far_percentage']}% | FRR: {metrics['frr_percentage']}% | EER: {metrics['eer_percentage']}%")
    print(f"    Avg Confidence: {metrics['average_confidence']}%")
    print("\n>>> Seeding complete! Ready for KeyStro execution.\n")


if __name__ == "__main__":
    seed_database()
