"""
KeyStro Keystroke Feature Extractor
Processes privacy-first keystroke timing arrays into normalized statistical feature vectors.
Raw characters are never parsed, transmitted, or stored.
"""

import numpy as np
from typing import List, Dict, Any, Tuple

# Canonical feature ordering used across ML models and transformers
FEATURE_COLUMNS = [
    "dwell_mean",
    "dwell_std",
    "dwell_median",
    "dwell_min",
    "dwell_max",
    "dwell_iqr",
    "flight_mean",
    "flight_std",
    "flight_median",
    "flight_min",
    "flight_max",
    "flight_iqr",
    "ikl_mean",
    "ikl_std",
    "ikl_median",
    "ikl_min",
    "ikl_max",
    "ikl_iqr",
    "speed_kpm",
    "pause_ratio",
    "ft_dt_ratio",
    "cadence_cv",
]


def parse_raw_keystrokes(events: List[Any]) -> Tuple[np.ndarray, np.ndarray, np.ndarray, float]:
    """
    Parses a sequence of keystroke timing records into:
    - dwell_times: np.ndarray (ms)
    - flight_times: np.ndarray (ms)
    - ikl_times: np.ndarray (ms) (inter-key latency)
    - total_duration_ms: float

    Accepts formats:
    1. List of dicts with {"down": t_down, "up": t_up}
    2. List of dicts with {"dwell": d, "flight": f, "latency": l}
    3. List of tuples/lists: [(t_down, t_up), ...]
    """
    if not events or len(events) < 2:
        return np.array([100.0]), np.array([150.0]), np.array([250.0]), 1000.0

    dwell_list = []
    flight_list = []
    ikl_list = []
    total_duration = 1000.0

    # Format 2: Pre-calculated interval dicts
    if isinstance(events[0], dict) and "dwell" in events[0]:
        for item in events:
            dwell_list.append(float(item.get("dwell", 100.0)))
            if "flight" in item and item["flight"] is not None:
                flight_list.append(float(item["flight"]))
            if "latency" in item and item["latency"] is not None:
                ikl_list.append(float(item["latency"]))
        if not flight_list:
            flight_list = [max(10.0, ikl - d) for d, ikl in zip(dwell_list[1:], ikl_list)]
        if not ikl_list:
            ikl_list = [d + f for d, f in zip(dwell_list[:-1], flight_list)]
        total_duration = float(sum(ikl_list)) if ikl_list else 1000.0

    # Format 1 & 3: Timestamps pairs (down, up)
    else:
        parsed_pairs = []
        for item in events:
            if isinstance(item, dict):
                t_down = float(item.get("down", 0))
                t_up = float(item.get("up", t_down + 100))
            elif isinstance(item, (list, tuple)) and len(item) >= 2:
                t_down = float(item[0])
                t_up = float(item[1])
            else:
                continue
            parsed_pairs.append((t_down, t_up))

        if len(parsed_pairs) < 2:
            return np.array([100.0]), np.array([150.0]), np.array([250.0]), 1000.0

        for i in range(len(parsed_pairs)):
            t_down, t_up = parsed_pairs[i]
            # Dwell time = t_up - t_down
            dt = max(10.0, min(1500.0, t_up - t_down))
            dwell_list.append(dt)

            if i > 0:
                prev_down, prev_up = parsed_pairs[i - 1]
                # Flight time: clip extreme cognitive pauses to 1100ms so thinking doesn't corrupt rhythmic metrics
                ft = np.clip(t_down - prev_up, -120.0, 1100.0)
                flight_list.append(ft)

                # Inter-Key Latency: capped for active burst tracking
                ikl = max(15.0, min(1500.0, t_down - prev_down))
                ikl_list.append(ikl)

        total_duration = max(500.0, parsed_pairs[-1][1] - parsed_pairs[0][0])

    dwell_arr = np.array(dwell_list, dtype=np.float64)
    flight_arr = np.array(flight_list if flight_list else [150.0], dtype=np.float64)
    ikl_arr = np.array(ikl_list if ikl_list else [250.0], dtype=np.float64)

    return dwell_arr, flight_arr, ikl_arr, total_duration


def compute_distribution_stats(arr: np.ndarray, prefix: str) -> Dict[str, float]:
    """Computes summary statistics: mean, std, median, min, max, and IQR."""
    if len(arr) == 0:
        return {
            f"{prefix}_mean": 0.0,
            f"{prefix}_std": 0.0,
            f"{prefix}_median": 0.0,
            f"{prefix}_min": 0.0,
            f"{prefix}_max": 0.0,
            f"{prefix}_iqr": 0.0,
        }

    q75, q25 = np.percentile(arr, [75, 25])
    iqr = float(q75 - q25)
    mean_val = float(np.mean(arr))
    std_val = float(np.std(arr))
    med_val = float(np.median(arr))
    min_val = float(np.min(arr))
    max_val = float(np.max(arr))

    return {
        f"{prefix}_mean": round(mean_val, 2),
        f"{prefix}_std": round(std_val, 2),
        f"{prefix}_median": round(med_val, 2),
        f"{prefix}_min": round(min_val, 2),
        f"{prefix}_max": round(max_val, 2),
        f"{prefix}_iqr": round(iqr, 2),
    }


def extract_features(raw_events: List[Any]) -> Dict[str, float]:
    """
    Transforms raw keystroke events into a canonical feature dictionary.
    """
    dwell_arr, flight_arr, ikl_arr, total_duration_ms = parse_raw_keystrokes(raw_events)

    features: Dict[str, float] = {}

    # Dwell statistics
    features.update(compute_distribution_stats(dwell_arr, "dwell"))

    # Flight statistics
    features.update(compute_distribution_stats(flight_arr, "flight"))

    # Inter-Key Latency statistics
    features.update(compute_distribution_stats(ikl_arr, "ikl"))

    # Typing speed based on active typing bursts (ignoring idle reading time > 1.4s)
    num_keys = max(1, len(dwell_arr))
    active_duration_ms = float(sum(min(1400.0, k) for k in ikl_arr)) if len(ikl_arr) > 0 else total_duration_ms
    speed_kpm = (num_keys / (active_duration_ms / 60000.0)) if active_duration_ms > 0 else 0.0
    features["speed_kpm"] = round(min(1200.0, max(20.0, float(speed_kpm))), 2)

    # Pause ratio: fraction of flight times > 350ms (cognitive pause / hesitation)
    pause_count = int(np.sum(flight_arr > 350.0))
    features["pause_ratio"] = round(float(pause_count / max(1, len(flight_arr))), 4)

    # Ratio of flight time to dwell time
    mean_dt = max(1.0, features["dwell_mean"])
    mean_ft = max(0.0, features["flight_mean"])
    features["ft_dt_ratio"] = round(float(mean_ft / mean_dt), 3)

    # Cadence consistency (Coefficient of variation: std / mean)
    mean_ikl = max(1.0, features["ikl_mean"])
    std_ikl = features["ikl_std"]
    features["cadence_cv"] = round(float(std_ikl / mean_ikl), 3)

    return features


def feature_dict_to_vector(features: Dict[str, float]) -> np.ndarray:
    """Converts a feature dict into a 1D numpy array aligned with FEATURE_COLUMNS."""
    vector = [features.get(col, 0.0) for col in FEATURE_COLUMNS]
    return np.array(vector, dtype=np.float64)


def create_rolling_windows(events: List[Any], window_size: int = 15, step: int = 5) -> List[Dict[str, float]]:
    """
    Slices raw keystroke event streams into overlapping rolling windows
    to generate multiple feature vectors for training or evaluation.
    """
    if len(events) < window_size:
        return [extract_features(events)]

    windows = []
    for start in range(0, len(events) - window_size + 1, step):
        window_events = events[start : start + window_size]
        windows.append(extract_features(window_events))

    # Catch tail events if leftover
    if len(events) >= window_size and (len(events) - window_size) % step != 0:
        windows.append(extract_features(events[-window_size:]))

    return windows
