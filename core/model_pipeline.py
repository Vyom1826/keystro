"""
KeyStro Machine Learning Pipeline
Dual-mode hybrid continuous biometric authentication:
1. IsolationForest (unsupervised anomaly detector tailored to user baseline)
2. RandomForestClassifier (discriminative model against synthetic imposter baselines)
3. Confidence score calibration with dynamic risk assessment (LOW, MEDIUM, HIGH)
"""

import os
import joblib
import numpy as np
from typing import Dict, Any, List, Tuple, Optional
from sklearn.ensemble import IsolationForest, RandomForestClassifier
from sklearn.preprocessing import StandardScaler

from core.feature_extractor import (
    FEATURE_COLUMNS,
    feature_dict_to_vector,
    extract_features,
    create_rolling_windows,
)

ROOT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
MODELS_DIR = os.path.join(ROOT_DIR, "models")
os.makedirs(MODELS_DIR, exist_ok=True)

# In-memory cache for trained models for ultra-fast session evaluation
_MODEL_CACHE: Dict[str, Dict[str, Any]] = {}


def generate_synthetic_imposters(
    user_features: np.ndarray,
    n_samples: int = 150
) -> np.ndarray:
    """
    Generates synthetic background imposter feature vectors representing varied typists.
    Guarantees a strict exclusion zone so that NO imposter sample ever collides with
    or pollutes the genuine user's personal typing baseline envelope.
    """
    imposters = []
    rng = np.random.RandomState(42)

    u_mean = np.mean(user_features, axis=0)
    u_std = np.std(user_features, axis=0) + 1e-4

    target_count = max(150, n_samples)
    attempts = 0

    while len(imposters) < target_count and attempts < target_count * 10:
        attempts += 1
        cat = rng.choice([1, 2, 3, 4])

        if cat == 1:
            # 1. Robotic bot / scripted fast typist
            dwell = rng.uniform(25, 55)
            flight = rng.uniform(15, 60)
            speed = rng.uniform(450, 750)
            pause = rng.uniform(0.0, 0.04)
            cadence_cv = rng.uniform(0.08, 0.22)
            d_std = rng.uniform(4, 12)
            f_std = rng.uniform(6, 18)

        elif cat == 2:
            # 2. Slow, heavy hunt-and-peck typist
            dwell = rng.uniform(230, 420)
            flight = rng.uniform(550, 1400)
            speed = rng.uniform(30, 85)
            pause = rng.uniform(0.35, 0.75)
            cadence_cv = rng.uniform(0.7, 1.4)
            d_std = rng.uniform(35, 90)
            f_std = rng.uniform(100, 300)

        elif cat == 3:
            # 3. Ratio-inverted cadence (abnormally high or low flight-to-dwell ratio)
            dwell_mult = rng.choice([0.35, 2.3])
            flight_mult = rng.choice([0.25, 2.4])
            dwell = max(25.0, u_mean[0] * dwell_mult)
            flight = max(35.0, u_mean[6] * flight_mult)
            speed = max(30.0, u_mean[18] * rng.choice([0.4, 2.2]))
            pause = rng.uniform(0.05, 0.40)
            cadence_cv = rng.uniform(0.3, 0.9)
            d_std = max(10.0, u_std[0] * 1.5)
            f_std = max(20.0, u_std[6] * 1.5)

        else:
            # 4. Statistical shift beyond user's personal variance envelope (>= 2.5 std devs)
            d_dir = rng.choice([-1, 1])
            f_dir = rng.choice([-1, 1])
            dwell = max(25.0, u_mean[0] + d_dir * (u_std[0] * rng.uniform(2.5, 4.8)))
            flight = max(35.0, u_mean[6] + f_dir * (u_std[6] * rng.uniform(2.5, 4.8)))
            sp_dir = rng.choice([-1, 1])
            speed = max(30.0, u_mean[18] + sp_dir * (u_std[18] * rng.uniform(2.5, 4.2)))
            pause = rng.uniform(0.08, 0.45)
            cadence_cv = rng.uniform(0.4, 1.1)
            d_std = max(12.0, u_std[0] * 1.4)
            f_std = max(25.0, u_std[6] * 1.4)

        # STRICT EXCLUSION FILTER:
        # Never place an imposter within 2.0 standard deviations of the user's personal mean
        dwell_dist = abs(dwell - u_mean[0]) / u_std[0]
        flight_dist = abs(flight - u_mean[6]) / u_std[6]
        if dwell_dist < 2.0 and flight_dist < 2.0:
            continue

        ikl_m = dwell + flight
        ikl_s = float(np.sqrt(d_std ** 2 + f_std ** 2))
        vec = [
            dwell, d_std, dwell, max(15.0, dwell - 1.5 * d_std), dwell + 1.8 * d_std, max(5.0, 1.35 * d_std),
            flight, f_std, flight, max(10.0, flight - 1.5 * f_std), flight + 1.8 * f_std, max(10.0, 1.35 * f_std),
            ikl_m, ikl_s, ikl_m, max(25.0, ikl_m - 1.5 * ikl_s), ikl_m + 1.8 * ikl_s, max(15.0, 1.35 * ikl_s),
            speed, pause, flight / max(1.0, dwell), cadence_cv
        ]
        imposters.append(vec)

    return np.array(imposters, dtype=np.float64)


def augment_genuine_vectors(X_genuine: np.ndarray, target_count: int = 250) -> np.ndarray:
    """
    Expands the user's genuine feature matrix with realistic day-to-day human typing variability
    while strictly preserving feature domains and physical relationships (pause_ratio <= 1.0, etc.).
    """
    rng = np.random.RandomState(42)
    augmented = []
    copies = max(2, int(np.ceil((target_count - len(X_genuine)) / max(1, len(X_genuine)))))

    for vec in X_genuine:
        for _ in range(copies):
            # Jitter slightly (7% std dev)
            jitter = rng.normal(1.0, 0.07, size=vec.shape)
            v = vec.copy() * jitter

            # Feature boundary protections
            v[0] = max(25.0, v[0])                   # dwell_mean
            v[1] = max(5.0, v[1])                    # dwell_std
            v[2] = max(25.0, v[2])                   # dwell_median
            v[3] = max(10.0, v[3])                   # dwell_min
            v[4] = max(v[0] + 5.0, v[4])             # dwell_max
            v[5] = max(5.0, v[5])                    # dwell_iqr

            v[6] = max(20.0, v[6])                   # flight_mean
            v[7] = max(8.0, v[7])                    # flight_std
            v[8] = max(20.0, v[8])                   # flight_median
            v[9] = max(-100.0, v[9])                 # flight_min
            v[10] = max(v[6] + 10.0, v[10])          # flight_max
            v[11] = max(8.0, v[11])                  # flight_iqr

            v[12] = max(30.0, v[12])                 # ikl_mean
            v[13] = max(10.0, v[13])                 # ikl_std
            v[14] = max(30.0, v[14])                 # ikl_median
            v[15] = max(15.0, v[15])                 # ikl_min
            v[16] = max(v[12] + 15.0, v[16])         # ikl_max
            v[17] = max(10.0, v[17])                 # ikl_iqr

            v[18] = np.clip(v[18], 20.0, 1000.0)     # speed_kpm
            v[19] = np.clip(v[19], 0.0, 1.0)         # pause_ratio (strictly in [0, 1])
            v[20] = max(0.1, v[6] / max(1.0, v[0]))  # ft_dt_ratio
            v[21] = np.clip(v[21], 0.05, 2.5)        # cadence_cv

            augmented.append(v)

    if augmented:
        return np.vstack([X_genuine, np.array(augmented, dtype=np.float64)])
    return X_genuine


def train_user_models(
    username: str,
    raw_passages: List[List[Any]],
    contamination: float = 0.02
) -> Dict[str, Any]:
    """
    Trains a dual-mode ML authentication model for the specified user:
    - IsolationForest for unsupervised inlier/outlier bounding
    - RandomForestClassifier for genuine vs. imposter boundary learning
    - StandardScaler fitted on combined baseline
    """
    all_feature_dicts = []

    # 1. Extract rolling windows from each passage
    for passage_events in raw_passages:
        if len(passage_events) >= 15:
            windows = create_rolling_windows(passage_events, window_size=15, step=3)
            all_feature_dicts.extend(windows)
        else:
            all_feature_dicts.append(extract_features(passage_events))

    if len(all_feature_dicts) == 0:
        raise ValueError("Insufficient keystroke data for enrollment.")

    # Convert to feature matrix
    X_genuine = np.array([feature_dict_to_vector(fd) for fd in all_feature_dicts], dtype=np.float64)

    # Domain-aware data augmentation for small enrollment sets:
    X_genuine_aug = augment_genuine_vectors(X_genuine, target_count=250)

    # 2. Fit Scaler
    scaler = StandardScaler()
    X_genuine_scaled = scaler.fit_transform(X_genuine_aug)

    # 3. Train Isolation Forest (One-class anomaly detector)
    iso_forest = IsolationForest(
        n_estimators=100,
        contamination=0.02,
        random_state=42,
        max_samples="auto"
    )
    iso_forest.fit(X_genuine_scaled)

    # Calculate baseline scores for calibration
    raw_scores = iso_forest.decision_function(X_genuine_scaled)
    score_p10 = float(np.percentile(raw_scores, 10))
    score_p50 = float(np.median(raw_scores))
    score_p90 = float(np.percentile(raw_scores, 90))

    # 4. Synthesize Imposter Baseline and train Random Forest Classifier
    X_imposters = generate_synthetic_imposters(X_genuine_aug, n_samples=max(150, len(X_genuine_aug) * 2))
    X_imposters_scaled = scaler.transform(X_imposters)

    X_train_rf = np.vstack([X_genuine_scaled, X_imposters_scaled])
    y_train_rf = np.hstack([np.ones(len(X_genuine_scaled)), np.zeros(len(X_imposters_scaled))])

    rf_classifier = RandomForestClassifier(
        n_estimators=100,
        max_depth=6,
        random_state=42,
        class_weight="balanced"
    )
    rf_classifier.fit(X_train_rf, y_train_rf)

    # Feature baseline stats for quick diagnostics
    dwell_mean_overall = float(np.mean([fd["dwell_mean"] for fd in all_feature_dicts]))
    flight_mean_overall = float(np.mean([fd["flight_mean"] for fd in all_feature_dicts]))
    speed_mean_overall = float(np.mean([fd["speed_kpm"] for fd in all_feature_dicts]))

    model_bundle = {
        "username": username,
        "scaler": scaler,
        "isolation_forest": iso_forest,
        "random_forest": rf_classifier,
        "genuine_vectors": X_genuine_aug,
        "adaptation_count": 0,
        "model_version": "v1.0",
        "words_trained": 0,
        "calibration": {
            "p10": score_p10,
            "p50": score_p50,
            "p90": score_p90,
            "min_raw": float(np.min(raw_scores)),
            "max_raw": float(np.max(raw_scores)),
        },
        "baseline_stats": {
            "dwell_mean": round(dwell_mean_overall, 2),
            "flight_mean": round(flight_mean_overall, 2),
            "speed_kpm": round(speed_mean_overall, 2),
            "sample_count": len(X_genuine_aug)
        }
    }

    # Save to disk
    model_path = os.path.join(MODELS_DIR, f"{username}_model.joblib")
    joblib.dump(model_bundle, model_path)

    # Store in memory cache
    _MODEL_CACHE[username] = model_bundle

    return {
        "model_path": model_path,
        "baseline_stats": model_bundle["baseline_stats"],
        "calibration": model_bundle["calibration"],
        "sample_count": len(X_genuine_aug),
        "model_version": "v1.0"
    }


def adapt_user_model(
    username: str,
    new_genuine_events: List[Any],
    words_count: int = 200
) -> Dict[str, Any]:
    """
    Continuous Online Adaptation ("Train Ahead"):
    Incrementally updates the user's biometric baseline model with newly verified genuine typing data.
    Only triggered when new data (e.g. 200 verified words) of genuine typing cadence is collected.
    """
    model_bundle = load_user_model(username)
    if not model_bundle:
        raise ValueError(f"Cannot adapt model: No trained profile found for '{username}'.")

    # 1. Extract feature vectors from newly received genuine events
    if len(new_genuine_events) >= 15:
        new_windows = create_rolling_windows(new_genuine_events, window_size=15, step=3)
    else:
        new_windows = [extract_features(new_genuine_events)]

    X_new = np.array([feature_dict_to_vector(w) for w in new_windows], dtype=np.float64)

    # 2. Retrieve existing baseline genuine vectors
    X_old = model_bundle.get("genuine_vectors")
    if X_old is None or len(X_old) == 0:
        # Load from enrollment samples if needed or synthesize from baseline
        try:
            from core.database import get_user_enrollment_features
            saved_features = get_user_enrollment_features(username)
            if saved_features:
                X_old = np.array([feature_dict_to_vector(fd) for fd in saved_features], dtype=np.float64)
            else:
                stats = model_bundle.get("baseline_stats", {})
                dwell = stats.get("dwell_mean", 90.0)
                flight = stats.get("flight_mean", 100.0)
                speed = stats.get("speed_kpm", 300.0)
                vec = [
                    dwell, 10.0, dwell, dwell - 15, dwell + 20, 10.0,
                    flight, 12.0, flight, flight - 15, flight + 25, 12.0,
                    dwell + flight, 18.0, dwell + flight, 40.0, dwell + flight + 40, 20.0,
                    speed, 0.05, flight / max(1.0, dwell), 0.25
                ]
                X_old = np.tile(vec, (30, 1))
        except Exception:
            stats = model_bundle.get("baseline_stats", {})
            dwell = stats.get("dwell_mean", 90.0)
            flight = stats.get("flight_mean", 100.0)
            speed = stats.get("speed_kpm", 300.0)
            vec = [
                dwell, 10.0, dwell, dwell - 15, dwell + 20, 10.0,
                flight, 12.0, flight, flight - 15, flight + 25, 12.0,
                dwell + flight, 18.0, dwell + flight, 40.0, dwell + flight + 40, 20.0,
                speed, 0.05, flight / max(1.0, dwell), 0.25
            ]
            X_old = np.tile(vec, (30, 1))

    # 3. Combine old and new genuine vectors with continuous recency weighting
    # Cap total genuine history window at 350 to prevent unbounded memory growth while preserving anchor
    X_combined = np.vstack([X_old, X_new])
    if len(X_combined) > 350:
        # Keep earliest 70 anchor vectors + latest 280 most recent vectors
        n_anchor = 70
        X_anchor = X_combined[:n_anchor]
        X_recent = X_combined[-(350 - n_anchor):]
        X_combined = np.vstack([X_anchor, X_recent])

    # 4. Refit Scaler on updated combined distribution
    scaler = StandardScaler()
    X_combined_scaled = scaler.fit_transform(X_combined)

    # 5. Retrain Isolation Forest (One-class anomaly detector)
    iso_forest = IsolationForest(
        n_estimators=100,
        contamination=0.05,
        random_state=42,
        max_samples="auto"
    )
    iso_forest.fit(X_combined_scaled)

    raw_scores = iso_forest.decision_function(X_combined_scaled)
    score_p10 = float(np.percentile(raw_scores, 10))
    score_p50 = float(np.median(raw_scores))
    score_p90 = float(np.percentile(raw_scores, 90))

    # 6. Re-synthesize background imposters tailored to the newly adapted baseline
    X_imposters = generate_synthetic_imposters(X_combined, n_samples=max(120, len(X_combined) * 2))
    X_imposters_scaled = scaler.transform(X_imposters)

    X_train_rf = np.vstack([X_combined_scaled, X_imposters_scaled])
    y_train_rf = np.hstack([np.ones(len(X_combined_scaled)), np.zeros(len(X_imposters_scaled))])

    rf_classifier = RandomForestClassifier(
        n_estimators=100,
        max_depth=6,
        random_state=42,
        class_weight="balanced"
    )
    rf_classifier.fit(X_train_rf, y_train_rf)

    # 7. Compute updated baseline metrics
    new_dwell_mean = float(np.mean(X_combined[:, 0]))
    new_flight_mean = float(np.mean(X_combined[:, 6]))
    new_speed_mean = float(np.mean(X_combined[:, 18]))

    current_adaptation_count = model_bundle.get("adaptation_count", 0) + 1
    new_version = f"v{current_adaptation_count + 1}.0"

    # Update model bundle in place
    model_bundle["scaler"] = scaler
    model_bundle["isolation_forest"] = iso_forest
    model_bundle["random_forest"] = rf_classifier
    model_bundle["genuine_vectors"] = X_combined
    model_bundle["adaptation_count"] = current_adaptation_count
    model_bundle["model_version"] = new_version
    model_bundle["words_trained"] = model_bundle.get("words_trained", 0) + words_count
    model_bundle["calibration"] = {
        "p10": score_p10,
        "p50": score_p50,
        "p90": score_p90,
        "min_raw": float(np.min(raw_scores)),
        "max_raw": float(np.max(raw_scores)),
    }
    model_bundle["baseline_stats"] = {
        "dwell_mean": round(new_dwell_mean, 2),
        "flight_mean": round(new_flight_mean, 2),
        "speed_kpm": round(new_speed_mean, 2),
        "sample_count": len(X_combined)
    }

    # Save to disk
    model_path = os.path.join(MODELS_DIR, f"{username}_model.joblib")
    joblib.dump(model_bundle, model_path)
    _MODEL_CACHE[username] = model_bundle

    # Update SQLite persistence
    try:
        import core.database as db
        db.update_user_baseline(
            username=username,
            dwell_mean=round(new_dwell_mean, 2),
            flight_mean=round(new_flight_mean, 2),
            speed_kpm=round(new_speed_mean, 2),
            sample_count=len(X_combined),
            model_version=new_version,
            adaptation_count=current_adaptation_count,
            words_adapted=words_count
        )
    except Exception as e:
        print(f"Warning: Failed to update DB baseline for {username}: {e}")

    return {
        "success": True,
        "username": username,
        "model_version": new_version,
        "adaptation_count": current_adaptation_count,
        "words_adapted": words_count,
        "baseline_stats": model_bundle["baseline_stats"],
        "sample_count": len(X_combined)
    }


def load_user_model(username: str) -> Optional[Dict[str, Any]]:
    """Loads a user's model bundle from memory cache or disk."""
    if username in _MODEL_CACHE:
        return _MODEL_CACHE[username]

    model_path = os.path.join(MODELS_DIR, f"{username}_model.joblib")
    if not os.path.exists(model_path):
        return None

    try:
        model_bundle = joblib.load(model_path)
        _MODEL_CACHE[username] = model_bundle
        return model_bundle
    except Exception as e:
        print(f"Error loading model for {username}: {e}")
        return None


def calculate_confidence_score(
    model_bundle: Dict[str, Any],
    feature_vec: np.ndarray
) -> Tuple[float, float, float]:
    """
    Computes calibrated confidence score in [0.0, 1.0].
    Returns (composite_score, if_score, rf_prob).
    """
    scaler: StandardScaler = model_bundle["scaler"]
    iso_forest: IsolationForest = model_bundle["isolation_forest"]
    rf_classifier: RandomForestClassifier = model_bundle["random_forest"]
    calib = model_bundle["calibration"]

    vec_scaled = scaler.transform(feature_vec.reshape(1, -1))

    # 1. Isolation Forest Decision Score
    raw_if_score = float(iso_forest.decision_function(vec_scaled)[0])

    # Calibrate Isolation Forest score: scikit-learn decision_function >= 0 is inlier, < 0 is outlier
    if raw_if_score >= 0.0:
        p90 = max(0.04, calib.get("p90", 0.12))
        norm = float(np.clip(raw_if_score / p90, 0.0, 1.0))
        if_score = 0.75 + 0.23 * norm
    else:
        min_raw = min(-0.04, calib.get("min_raw", -0.10))
        norm = float(np.clip((raw_if_score - min_raw) / abs(min_raw), 0.0, 1.0))
        if_score = 0.10 + 0.55 * norm

    # 2. Random Forest Probability (Class 1 = Genuine)
    rf_probs = rf_classifier.predict_proba(vec_scaled)[0]
    rf_prob = float(rf_probs[1]) if len(rf_probs) > 1 else float(rf_probs[0])

    # 3. Composite score (weighted blend: 30% Isolation Forest, 70% Random Forest)
    composite = 0.30 * if_score + 0.70 * rf_prob
    if rf_prob >= 0.85:
        composite = max(composite, 0.76 + 0.22 * (rf_prob - 0.85))
    composite = float(np.clip(composite, 0.01, 0.99))

    return round(composite, 3), round(if_score, 3), round(rf_prob, 3)


def evaluate_keystroke_chunk(
    username: str,
    raw_events: List[Any],
    session_history: Optional[List[float]] = None
) -> Dict[str, Any]:
    """
    Evaluates an active typing chunk against the enrolled user model.

    Threshold logic according to specifications:
    - Score > 0.70: Genuine user -> Session continues seamlessly (LOW risk).
    - Score between 0.40 and 0.70: Uncertain/Fatigue -> Soft warning (MEDIUM risk).
    - Score < 0.40: High anomaly -> Lock session / MFA Challenge (HIGH risk).
    """
    model_bundle = load_user_model(username)
    if not model_bundle:
        raise ValueError(f"No trained profile found for user '{username}'. Please enroll first.")

    features = extract_features(raw_events)
    feature_vec = feature_dict_to_vector(features)

    chunk_score, if_score, rf_prob = calculate_confidence_score(model_bundle, feature_vec)

    # Responsive temporal smoothing across recent verification chunks
    # For genuine typists, smoothing buffers temporary micro-hesitations.
    # If the current chunk is an anomaly (< 0.40), do NOT allow past genuine inertia to mask it.
    if session_history and len(session_history) > 0 and chunk_score >= 0.40:
        recent_avg = float(np.mean(session_history[-3:]))
        current_weight = 0.70
        smoothed_score = round(current_weight * chunk_score + (1.0 - current_weight) * recent_avg, 3)
    else:
        smoothed_score = chunk_score

    # Determine risk level and operational action
    if smoothed_score >= 0.70:
        risk_level = "LOW"
        action = "allowed"
        is_anomaly = False
        status_message = "Typing rhythm authenticated. Active session verified."
    elif 0.40 <= smoothed_score < 0.70:
        risk_level = "MEDIUM"
        action = "warned"
        is_anomaly = False
        status_message = "Rhythm drift or fatigue detected. Elevated monitoring active."
    else:
        risk_level = "HIGH"
        action = "locked"
        is_anomaly = True
        status_message = "Rhythm anomaly detected! Potential session hijacking. Adaptive MFA verification required."

    return {
        "confidence_score": smoothed_score,
        "raw_chunk_score": chunk_score,
        "risk_level": risk_level,
        "action_taken": action,
        "is_anomaly": is_anomaly,
        "status_message": status_message,
        "model_breakdown": {
            "isolation_forest_score": if_score,
            "random_forest_prob": rf_prob,
        },
        "features": features,
        "baseline_comparison": {
            "baseline_dwell": model_bundle["baseline_stats"]["dwell_mean"],
            "current_dwell": features["dwell_mean"],
            "baseline_flight": model_bundle["baseline_stats"]["flight_mean"],
            "current_flight": features["flight_mean"],
            "baseline_speed": model_bundle["baseline_stats"]["speed_kpm"],
            "current_speed": features["speed_kpm"]
        }
    }


def retrain_user_from_enrollment(username: str) -> Dict[str, Any]:
    """
    Retrains a user's biometric ML pipeline directly from their stored calibration passages in SQLite,
    or from their saved genuine baseline vectors in the model bundle.
    Refits IsolationForest + RandomForest with clean background exclusion boundaries.
    """
    import core.database as db
    conn = db.get_db()
    rows = conn.execute(
        "SELECT raw_timings_json FROM enrollment_samples WHERE username = ? ORDER BY sample_index ASC",
        (username,)
    ).fetchall()
    conn.close()

    if rows:
        import json
        raw_passages = []
        for r in rows:
            txt = r["raw_timings_json"]
            try:
                raw_passages.append(json.loads(txt))
            except Exception:
                raw_passages.append(eval(txt))
        train_res = train_user_models(username, raw_passages)
    else:
        # Fallback to model bundle's genuine vectors
        model_bundle = load_user_model(username)
        if not model_bundle or "genuine_vectors" not in model_bundle:
            raise ValueError(f"No stored enrollment calibration passages or model bundle found for '{username}'.")

        raw_stored_vectors = model_bundle["genuine_vectors"]
        # Filter for genuine uncorrupted vectors (pause_ratio <= 1.0)
        valid_indices = np.where(raw_stored_vectors[:, 19] <= 1.0)[0]
        if len(valid_indices) > 0:
            X_orig = raw_stored_vectors[valid_indices]
        else:
            X_orig = raw_stored_vectors

        X_genuine_aug = augment_genuine_vectors(X_orig, target_count=250)
        scaler = StandardScaler()
        X_genuine_scaled = scaler.fit_transform(X_genuine_aug)

        iso_forest = IsolationForest(
            n_estimators=100,
            contamination=0.02,
            random_state=42,
            max_samples="auto"
        )
        iso_forest.fit(X_genuine_scaled)

        raw_scores = iso_forest.decision_function(X_genuine_scaled)
        score_p10 = float(np.percentile(raw_scores, 10))
        score_p50 = float(np.median(raw_scores))
        score_p90 = float(np.percentile(raw_scores, 90))

        X_imposters = generate_synthetic_imposters(X_genuine_aug, n_samples=max(200, len(X_genuine_aug) * 2))
        X_imposters_scaled = scaler.transform(X_imposters)

        X_train_rf = np.vstack([X_genuine_scaled, X_imposters_scaled])
        y_train_rf = np.hstack([np.ones(len(X_genuine_scaled)), np.zeros(len(X_imposters_scaled))])

        rf_classifier = RandomForestClassifier(
            n_estimators=100,
            max_depth=6,
            random_state=42,
            class_weight="balanced"
        )
        rf_classifier.fit(X_train_rf, y_train_rf)

        dwell_mean_overall = float(np.mean(X_orig[:, 0]))
        flight_mean_overall = float(np.mean(X_orig[:, 6]))
        speed_mean_overall = float(np.mean(X_orig[:, 18]))

        model_bundle.update({
            "scaler": scaler,
            "isolation_forest": iso_forest,
            "random_forest": rf_classifier,
            "genuine_vectors": X_genuine_aug,
            "calibration": {
                "p10": score_p10,
                "p50": score_p50,
                "p90": score_p90,
                "min_raw": float(np.min(raw_scores)),
                "max_raw": float(np.max(raw_scores)),
            },
            "baseline_stats": {
                "dwell_mean": round(dwell_mean_overall, 2),
                "flight_mean": round(flight_mean_overall, 2),
                "speed_kpm": round(speed_mean_overall, 2),
                "sample_count": len(X_genuine_aug)
            }
        })

        model_path = os.path.join(MODELS_DIR, f"{username}_model.joblib")
        joblib.dump(model_bundle, model_path)
        _MODEL_CACHE[username] = model_bundle

        train_res = {
            "model_path": model_path,
            "baseline_stats": model_bundle["baseline_stats"],
            "calibration": model_bundle["calibration"],
            "sample_count": len(X_genuine_aug),
            "model_version": model_bundle.get("model_version", "v1.0")
        }

    baseline = train_res["baseline_stats"]
    db.save_user(
        username=username,
        total_samples=train_res["sample_count"],
        avg_dwell=baseline["dwell_mean"],
        avg_flight=baseline["flight_mean"],
        avg_speed=baseline["speed_kpm"],
        model_path=train_res["model_path"]
    )
    return train_res


def retrain_all_enrolled_users() -> Dict[str, Any]:
    """
    Retrains all users who have stored calibration samples in the SQLite database.
    """
    import core.database as db
    conn = db.get_db()
    rows = conn.execute("SELECT DISTINCT username FROM enrollment_samples").fetchall()
    conn.close()

    results = {}
    for r in rows:
        u = r["username"]
        try:
            results[u] = retrain_user_from_enrollment(u)
        except Exception as e:
            results[u] = {"error": str(e)}
    return results
