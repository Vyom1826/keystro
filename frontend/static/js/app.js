/**
 * KeyStro - Application Coordinator & Session Controller
 * Integrates KeystrokeRecorder, Chart.js telemetry, API verification,
 * session lifecycle, and Adaptive MFA challenge modals.
 */

// Global Application State
const State = {
    currentUser: null,
    sessionId: null,
    isLocked: false,
    usersList: [],
    telemetryChart: null,
    recorder: null,
    enrollmentRecorder: null,
    enrollment: {
        username: '',
        currentStep: 0,
        passages: generateRandomPassages(3),
        collectedPassages: []
    }
};

// DOM Content Loaded Handler: Initializes all subsystems in order
document.addEventListener('DOMContentLoaded', () => {
    initTabs();
    initTelemetryChart();
    initWorkspaceRecorder();
    initEnrollmentFlow();
    initImposterControls();
    initMfaModal();
    initResetButton();

    // Fetch enrolled users and start initial session
    loadUsers();
});

// -------------------------------------------------------------
// Tab Switching System
// -------------------------------------------------------------
function initTabs() {
    const tabBtns = document.querySelectorAll('.tab-btn');
    const panes = document.querySelectorAll('.tab-pane');

    tabBtns.forEach(btn => {
        btn.addEventListener('click', () => {
            const targetId = btn.getAttribute('data-tab');

            tabBtns.forEach(b => b.classList.remove('active'));
            panes.forEach(p => p.classList.remove('active'));

            btn.classList.add('active');
            const targetPane = document.getElementById(targetId);
            if (targetPane) {
                targetPane.classList.add('active');
            }

            // Lazy load analytics logs table if tab selected
            if (targetId === 'analyticsPane') {
                loadMetrics();
            }
        });
    });

    document.getElementById('refreshLogsBtn')?.addEventListener('click', loadMetrics);
}

// -------------------------------------------------------------
// User Management & Active Session Initializer
// -------------------------------------------------------------
let userSelectInitialized = false;

async function loadUsers(preferredUser = null) {
    const userSelect = document.getElementById('userSelect');
    if (!userSelect) return;

    try {
        const res = await fetch('/api/users');
        const data = await res.json();

        if (data.success && data.users.length > 0) {
            State.usersList = data.users;
            userSelect.innerHTML = '';

            data.users.forEach((u) => {
                const opt = document.createElement('option');
                opt.value = u.username;
                opt.textContent = `${u.username} (${Math.round(u.avg_speed || 300)} KPM)`;
                userSelect.appendChild(opt);
            });

            // Retain preferred or currently active user if present, else default to first
            const targetUser = preferredUser || State.currentUser;
            const userExists = data.users.some((u) => u.username === targetUser);
            const activeUser = userExists ? targetUser : data.users[0].username;

            userSelect.value = activeUser;
            startSession(activeUser);

            if (!userSelectInitialized) {
                userSelect.addEventListener('change', (e) => {
                    startSession(e.target.value);
                });
                userSelectInitialized = true;
            }
        }
    } catch (err) {
        console.error('Failed to load users:', err);
    }
}

async function startSession(username) {
    State.currentUser = username;
    State.isLocked = false;

    // Reset workspace UI
    const workspaceInput = document.getElementById('workspaceInput');
    if (workspaceInput) {
        workspaceInput.disabled = false;
        workspaceInput.value = '';
    }
    State.recorder?.reset();

    // Update portal display
    const avatarEl = document.getElementById('avatarLetter');
    const portalUserEl = document.getElementById('portalUserName');
    if (avatarEl) avatarEl.textContent = username.charAt(0).toUpperCase();
    if (portalUserEl) portalUserEl.textContent = `User: ${username} (Corporate Terminal)`;

    try {
        const res = await fetch('/api/start-session', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ username })
        });
        const data = await res.json();

        if (data.success) {
            State.sessionId = data.session_id;
            const sessionDisplay = document.getElementById('portalSessionId');
            if (sessionDisplay) sessionDisplay.textContent = `Session: ${data.session_id}`;
            updateConfidenceDisplay(0.92, 'LOW', 'allowed');

            if (data.continuous_learning) {
                handleContinuousLearningUpdate(data.continuous_learning);
            }
        }
    } catch (e) {
        console.error('Failed to start session:', e);
    }
}

// -------------------------------------------------------------
// Continuous Online Adaptation ("Train Ahead") UI Coordinator
// -------------------------------------------------------------
function handleContinuousLearningUpdate(cl, adaptationInfo = null) {
    if (!cl) return;

    const wordsCountEl = document.getElementById('clWordsCount');
    const wordsThresholdEl = document.getElementById('clWordsThreshold');
    const progressBar = document.getElementById('clProgressBar');
    const badge = document.getElementById('modelVerBadge');
    const adaptationsCountEl = document.getElementById('clAdaptationsCount');
    const card = document.getElementById('continuousLearningCard');
    const modelIndicator = document.getElementById('modelIndicator');

    if (wordsCountEl) wordsCountEl.textContent = cl.words_accumulated || 0;
    if (wordsThresholdEl) wordsThresholdEl.textContent = cl.words_threshold || 200;
    if (progressBar) progressBar.style.width = `${Math.min(100, cl.progress_percent || 0)}%`;

    if (badge && cl.model_version) {
        badge.textContent = `Model ${cl.model_version}`;
    }

    if (modelIndicator && cl.model_version) {
        modelIndicator.textContent = `Hybrid IF + RF (${cl.model_version})`;
    }

    if (adaptationsCountEl) {
        adaptationsCountEl.textContent = `Adaptations: ${cl.adaptation_count || 0}`;
    }

    if (card) {
        if (cl.rejected_from_training) {
            card.classList.remove('learning-active');
        } else {
            card.classList.add('learning-active');
        }
    }
}

function showAdaptationBanner(info) {
    const card = document.getElementById('continuousLearningCard');
    const statusText = document.getElementById('clStatusText');
    const badge = document.getElementById('modelVerBadge');

    if (card) {
        card.classList.add('adapted-pulse');
        setTimeout(() => card.classList.remove('adapted-pulse'), 1500);
    }

    if (badge) {
        badge.classList.add('badge-updated');
        setTimeout(() => badge.classList.remove('badge-updated'), 2000);
    }

    if (statusText && info) {
        const dwell = info.new_baseline ? info.new_baseline.dwell_mean : '--';
        const flight = info.new_baseline ? info.new_baseline.flight_mean : '--';
        statusText.innerHTML = `<strong style="color:var(--secure-green);">🧠 Retrained Ahead (${info.model_version})!</strong> Baseline tuned with +${info.words_adapted || 200} words (Dwell: ${dwell}ms, Flight: ${flight}ms).`;
    }
}

// -------------------------------------------------------------
// Backend Verification Communication
// -------------------------------------------------------------
async function verifyKeystrokeChunk(chunkEvents, isImposter, wordsInChunk = 2) {
    if (!State.sessionId || State.isLocked) return;

    try {
        const payload = {
            session_id: State.sessionId,
            events: chunkEvents,
            is_imposter_simulation: isImposter,
            words_in_chunk: wordsInChunk
        };

        const res = await fetch('/api/verify-session', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(payload)
        });

        const data = await res.json();

        if (res.status === 403 || data.status === 'challenged' || data.action_taken === 'locked') {
            handleSessionLock(data.challenge_otp || '729104');
            return;
        }

        if (data.success) {
            updateConfidenceDisplay(data.confidence_score, data.risk_level, data.action_taken, data.status_message);

            if (data.continuous_learning) {
                handleContinuousLearningUpdate(data.continuous_learning, data.adaptation_info);
            }

            if (data.adapted && data.adaptation_info) {
                showAdaptationBanner(data.adaptation_info);
            }
        }
    } catch (err) {
        console.error('Keystroke chunk verification error:', err);
    }
}

// -------------------------------------------------------------
// Adaptive Verification Challenge (Lock & MFA Popup)
// -------------------------------------------------------------
function handleSessionLock(challengeOtp) {
    State.isLocked = true;

    // Update HUD to Locked State
    updateConfidenceDisplay(0.24, 'HIGH', 'locked');

    const workspaceInput = document.getElementById('workspaceInput');
    if (workspaceInput) {
        workspaceInput.disabled = true;
    }

    const modal = document.getElementById('mfaModal');
    const otpDisplay = document.getElementById('simulatedOtpDisplay');
    const otpInput = document.getElementById('otpInput');

    if (modal) {
        modal.classList.add('active');
        if (otpDisplay) otpDisplay.textContent = challengeOtp;
        if (otpInput) {
            otpInput.value = '';
            otpInput.focus();
        }
    }
}

function initMfaModal() {
    const modal = document.getElementById('mfaModal');
    const verifyOtpBtn = document.getElementById('verifyOtpBtn');
    const cancelMfaBtn = document.getElementById('cancelMfaBtn');
    const otpInput = document.getElementById('otpInput');

    verifyOtpBtn?.addEventListener('click', async () => {
        const code = otpInput.value.trim();
        if (!code || code.length < 4) {
            alert('Please enter the 6-digit verification code.');
            return;
        }

        try {
            const res = await fetch('/api/verify-otp', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({
                    session_id: State.sessionId,
                    otp: code
                })
            });

            const data = await res.json();

            if (data.success) {
                // Unlock session
                State.isLocked = false;
                modal.classList.remove('active');

                const workspaceInput = document.getElementById('workspaceInput');
                if (workspaceInput) {
                    workspaceInput.disabled = false;
                    workspaceInput.focus();
                }

                // Restore Genuine Display
                updateConfidenceDisplay(0.88, 'LOW', 'allowed');
                alert('Session successfully verified and unlocked! Seamless monitoring resumed.');
            } else {
                alert(data.message || data.error || 'Invalid verification OTP. Access denied.');
            }
        } catch (e) {
            alert('Verification request failed. Check server connection.');
        }
    });

    cancelMfaBtn?.addEventListener('click', () => {
        modal.classList.remove('active');
        // Restart a new session for the current user
        if (State.currentUser) {
            startSession(State.currentUser);
        }
    });
}

// -------------------------------------------------------------
// Security Analytics & Verification Logs Loader
// -------------------------------------------------------------
async function loadMetrics() {
    try {
        const res = await fetch('/api/metrics');
        const data = await res.json();

        if (data.success) {
            const m = data.metrics;
            const evalsEl = document.getElementById('metricTotalEvals');
            const farEl = document.getElementById('metricFAR');
            const frrEl = document.getElementById('metricFRR');
            const eerEl = document.getElementById('metricEER');

            if (evalsEl) evalsEl.textContent = m.total_evaluations;
            if (farEl) farEl.textContent = `${m.far_percentage}%`;
            if (frrEl) frrEl.textContent = `${m.frr_percentage}%`;
            if (eerEl) eerEl.textContent = `${m.eer_percentage}%`;

            // Populate table
            const tbody = document.getElementById('logsTableBody');
            if (tbody && data.logs) {
                if (data.logs.length === 0) {
                    tbody.innerHTML = `<tr><td colspan="8" style="text-align:center; padding: 2rem; color: var(--text-muted);">No verification logs recorded yet.</td></tr>`;
                    return;
                }

                tbody.innerHTML = data.logs.map(log => {
                    const timeStr = log.timestamp ? log.timestamp.split('T')[1].split('.')[0] : '--:--:--';
                    const scorePercent = Math.round(log.score * 100);
                    let badgeClass = 'low';
                    if (log.risk_level === 'MEDIUM') badgeClass = 'med';
                    if (log.risk_level === 'HIGH') badgeClass = 'high';

                    let actionHtml = `<span style="font-weight:600; text-transform:uppercase;">${log.action_taken}</span>`;
                    if (log.action_taken === 'adapted') {
                        actionHtml = `<span class="badge-tag adapted">🧠 TRAINED AHEAD</span>`;
                    }

                    return `
                        <tr>
                            <td>${timeStr}</td>
                            <td>${log.username} ${log.is_imposter_simulation ? '<span style="color:#fca5a5;">(Attack Sim)</span>' : ''}</td>
                            <td><strong>${scorePercent}%</strong></td>
                            <td><span class="badge-tag ${badgeClass}">${log.risk_level}</span></td>
                            <td>${log.dwell_mean ? log.dwell_mean.toFixed(1) : '--'} ms</td>
                            <td>${log.flight_mean ? log.flight_mean.toFixed(1) : '--'} ms</td>
                            <td>${log.speed_kpm ? Math.round(log.speed_kpm) : '--'}</td>
                            <td>${actionHtml}</td>
                        </tr>
                    `;
                }).join('');
            }
        }
    } catch (e) {
        console.error('Failed to load metrics:', e);
    }
}

// -------------------------------------------------------------
// Demo Reset Handler
// -------------------------------------------------------------
function initResetButton() {
    document.getElementById('resetDemoBtn')?.addEventListener('click', async () => {
        if (!confirm('Reset verification logs and database?')) return;
        try {
            await fetch('/api/reset', { method: 'POST' });
            alert('Database reset. Re-seeding baseline profiles...');
            window.location.reload();
        } catch (e) {
            console.error('Reset failed:', e);
        }
    });
}
