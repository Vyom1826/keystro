# KeyStro 🛡️
### *Your Typing, Your Identity, Your Security*
**AI-Powered Continuous Keystroke Authentication System**  
*Team TRISHUL*

---

## 📌 Executive Overview

Traditional identity authentication is static, verifying credentials (passwords, PINs, or SMS OTPs) solely at initial login. If a user walks away or an attacker takes over an authenticated enterprise or banking session, conventional systems remain oblivious.

**KeyStro** introduces a continuous behavioral biometric security layer. By monitoring how a user types rather than what they type, KeyStro detects unauthorized session takeovers in real-time, preventing unauthorized access without interrupting genuine workflows.

```
       [ Client-Side Typing Events ]
                    │  (keydown / keyup timestamps)
                    ▼
       [ Privacy-First Sanitizer ]  <--- ZERO characters or raw text stored
                    │  (dwell time, flight latency, cadence)
                    ▼
       [ Rolling Chunk Aggregator ] (12-15 keystrokes)
                    │  (mean, std, median, min, max, iqr, kpm)
                    ▼
     ┌───────────────────────────────────────┐
     │      Hybrid Machine Learning Core     │
     │  ┌─────────────────┐ ┌──────────────┐ │
     │  │ IsolationForest │ │ RandomForest │ │
     │  │ (Anomaly Scorer)│ │ (Classifier) │ │
     │  └─────────────────┘ └──────────────┘ │
     └───────────────────┬───────────────────┘
                         ▼
             [ Confidence Score: 0.0 - 1.0 ]
            ┌────────────┼─────────────┐
            ▼            ▼             ▼
       Score > 0.70  0.40 - 0.70   Score < 0.40
        [ Genuine ]  [ Warning ]   [ Anomaly ]
         (Active)    (Cadence)     (Session Locked)
                                          │
                                          ▼
                                   [ Adaptive MFA ]
                                   (OTP Challenge)
```

---

## 🔒 Privacy-First Guarantee

KeyStro adheres strictly to zero-trust privacy principles:
- **No Keylogging**: Key values, characters, words, and passwords are never inspected, buffered, or transmitted.
- **Timing Tuples Only**: The client extracts anonymized timing intervals:
  - **Dwell Time ($DT$)**: Duration a key remains depressed ($t_{\text{up}} - t_{\text{down}}$).
  - **Flight Time ($FT$)**: Duration between releasing a key and pressing the next ($t_{\text{down}}^{(n)} - t_{\text{up}}^{(n-1)}$).
  - **Inter-Key Latency ($IKL$)**: Time between consecutive keydowns ($t_{\text{down}}^{(n)} - t_{\text{down}}^{(n-1)}$).
  - **Typing Cadence ($KPM$)**: Keystrokes per minute cadence.

---

## 🧠 Machine Learning Engine Architecture

KeyStro employs a **dual-mode hybrid strategy** combining unsupervised anomaly detection with supervised discriminative boundaries:

1. **Baseline Anomaly Detector (`IsolationForest`)**:
   - Fitted on the enrolled user's unique typing distribution during 3 calibration passages.
   - Computes isolation path lengths across 22 statistical timing features.
   - Calibrated through a logistic sigmoid mapping centered around the training 10th percentile ($p_{10}$).

2. **Discriminative Classifier (`RandomForestClassifier`)**:
   - Trains against synthetic background imposter distributions (e.g., hunt-and-peck typists, robotic bot bursts, erratic fatigue).
   - Generates calibrated posterior probability $P(\text{genuine} \mid \vec{x})$.

3. **Composite Scoring & Adaptive Thresholds**:
   - $\text{Score} = 0.45 \cdot S_{\text{IF}} + 0.55 \cdot P_{\text{RF}}$
   - Continuous verification applies an **Adaptive Exponential Moving Average (EMA)** to filter out natural typos while triggering immediate lockdown upon severe anomalies:
     - **$\ge 0.70$ (Low Risk / Genuine)**: Seamless access continues.
     - **$0.40 - 0.70$ (Medium Risk / Drift)**: Warning status; elevated monitoring.
     - **$< 0.40$ (High Risk / Anomaly Detected)**: Session immediately locked; Adaptive MFA Challenge triggered.

---

## 📁 Clean Architecture & Structure

```
keystro/
├── frontend/                      # 🎨 Complete Frontend Application
│   ├── static/
│   │   ├── css/
│   │   │   └── style.css          # Cybersecurity dashboard styling & HUD gauges
│   │   └── js/
│   │       ├── app.js             # Application coordinator & session lifecycle
│   │       ├── enrollment.js      # 3-step biometric calibration & typo detection
│   │       ├── keystroke_recorder.js # High-resolution timing recorder engine
│   │       ├── prompts.js         # Dynamic prompt banks
│   │       ├── telemetry.js       # Live telemetry HUD & Chart.js stream
│   │       └── workspace.js       # Active monitored sandbox & imposter injector
│   └── templates/
│       └── index.html             # Single-page Security Operations Center UI
│
├── backend/                       # 🧠 Complete Backend API & ML Services
│   ├── app.py                     # Flask application factory & blueprint registration
│   ├── seed_data.py               # Pre-populates synthetic baseline profiles
│   ├── test_suite.py              # Automated 11-stage verification suite
│   ├── core/                      # Core biometric engine & persistence
│   │   ├── database.py            # SQLite schema, sessions, and telemetry persistence
│   │   ├── feature_extractor.py   # Extracts 22-dimensional timing dynamics vectors
│   │   └── model_pipeline.py      # Dual-mode IsolationForest + RandomForest pipeline
│   └── routes/                    # Modular REST API Blueprints
│       ├── session_routes.py      # /api/start-session, /api/verify-session, /api/verify-otp
│       ├── enroll_routes.py       # /api/enroll, /api/users
│       └── analytics_routes.py    # /api/metrics, /api/health
│
├── models/                        # 📦 Trained Biometric Machine Learning Bundles
│   ├── Vyom Singhal_model.joblib  # User profile model bundles (.joblib)
│   ├── alice_swift_model.joblib
│   ├── bob_deliberate_model.joblib
│   ├── charlie_analyst_model.joblib
│   └── ...
│
├── app.py                         # Root entrypoint launcher (`python app.py`)
├── requirements.txt               # Production Python dependencies
├── README.md                      # System documentation & setup guide
└── keystro.db                     # Local SQLite database
```

---

## 🚀 Quickstart Guide

### 1. Prerequisites
- Python 3.10, 3.11, 3.12, or 3.13
- Modern web browser (Chrome, Firefox, Edge, Safari)

### 2. Installation
Open your terminal in the `keystro` directory:

```bash
# Optional: Create and activate a virtual environment
python -m venv venv
# Windows:
.\venv\Scripts\activate
# Linux/macOS:
source venv/bin/activate

# Install dependencies
pip install -r requirements.txt
```

### 3. Seed Out-of-the-Box Demo Profiles
Run the seed script to generate synthetic user profiles and baseline telemetry:

```bash
python seed_data.py
```

### 4. Run the Automated Test Suite
Verify that all ML pipelines, API endpoints, and adaptive MFA flows pass:

```bash
python test_suite.py
```

### 5. Launch the KeyStro Application Server
Start the Flask application:

```bash
python app.py
```
Open your browser and navigate to:
```
http://127.0.0.1:5000
```

---

## 🎮 How to Demo KeyStro

### 1. Test Active Continuous Authentication
1. On the **Active Workspace & HUD** tab, select **Alice (High-Speed Software Engineer)**.
2. Click inside the **Workspace Editor** and type smoothly and quickly.
3. Observe the **Confidence Score Gauge**: it remains high in the **Green Zone (80% - 95%)**, and the telemetry stream plots live Dwell and Flight times.

### 2. Simulate an Imposter Session Hijack
1. Toggle the **Imposter Attack Simulator** switch ON, or click **"&times; Inject Imposter Attack Burst"**.
2. Type into the editor or observe the injected burst:
   - Notice the dramatic divergence in dwell time (> 250ms) and flight latency (> 400ms).
   - The Confidence Gauge drops sharply into the **Red Zone (< 40%)**.
   - **Session Locks**: Input is immediately disabled and the **Adaptive MFA Modal** pops up.
3. Enter the simulated 6-digit verification code shown on the screen and click **"Verify & Unlock"** to restore seamless access.

### 3. Enroll Your Own Biometric Profile
1. Click the **User Enrollment & Calibration** tab.
2. Enter your username (e.g., `your_name`).
3. Type the 3 calibration passages naturally.
4. Upon completing passage 3, KeyStro trains your personal `IsolationForest` and `RandomForest` models and computes your baseline statistics.
5. Click **"Switch to Active Workspace Now"** to test your personal typing biometric in real-time!

### 4. Security Analytics & Audit Trail
1. Switch to the **Security Analytics & Logs** tab.
2. Review real-time FAR (False Acceptance Rate), FRR (False Rejection Rate), and the complete telemetry audit trail of every typing block evaluated.

---

## 📡 REST API Reference

| Endpoint | Method | Description |
| :--- | :--- | :--- |
| `/api/health` | `GET` | Service status and version check |
| `/api/users` | `GET` | Returns list of enrolled users and baseline stats |
| `/api/start-session` | `POST` | Initializes an active continuous session for a user |
| `/api/verify-session` | `POST` | Continuously evaluates keystroke timing chunks against the user model |
| `/api/verify-otp` | `POST` | Verifies Adaptive MFA challenge code to unlock a session |
| `/api/enroll` | `POST` | Submits calibration passages and trains a new user model |
| `/api/metrics` | `GET` | Computes FAR, FRR, EER, and retrieves audit trail logs |
| `/api/reset` | `POST` | Resets sessions and logs for demo recreation |

---

## 🏆 TRISHUL Hackathon Details
- **Project**: KeyStro
- **Tagline**: *Your Typing, Your Identity, Your Security*
- **Track**: AI-Powered Keystroke Authentication
- **Event**: Code Yudh Hackathon
- **Institution**: Department of Computer Science & Engineering, Chandigarh University
