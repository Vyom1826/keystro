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
    initAlertSettingsModal();
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
// Real-Time Risk Notification & Alert Settings Handler
// -------------------------------------------------------------
function initAlertSettingsModal() {
    const modal = document.getElementById('alertSettingsModal');
    const openBtn = document.getElementById('openAlertSettingsBtn');
    const closeBtn = document.getElementById('closeAlertSettingsBtn');
    const closeXBtn = document.getElementById('closeAlertModalBtn');
    const saveBtn = document.getElementById('saveAlertSettingsBtn');
    const testBtn = document.getElementById('sendTestAlertBtn');
    const refreshLogsBtn = document.getElementById('refreshAlertLogsBtn');
    const statusBanner = document.getElementById('alertSettingsStatus');
    const activeBadge = document.getElementById('alertActiveBadge');

    if (!modal) return;

    // Load settings from backend
    async function fetchAlertSettings() {
        try {
            const res = await fetch('/api/alerts/settings');
            const data = await res.json();
            if (data.success && data.settings) {
                const s = data.settings;
                const minRiskEl = document.getElementById('settingsMinRisk');
                const cooldownEl = document.getElementById('settingsCooldown');
                const emailEnabledEl = document.getElementById('settingsEmailEnabled');
                const alertEmailEl = document.getElementById('settingsAlertEmail');
                const smtpHostEl = document.getElementById('settingsSmtpHost');
                const smtpPortEl = document.getElementById('settingsSmtpPort');
                const smtpUserEl = document.getElementById('settingsSmtpUser');
                const smtpPassEl = document.getElementById('settingsSmtpPass');

                const smsEnabledEl = document.getElementById('settingsSmsEnabled');
                const alertPhoneEl = document.getElementById('settingsAlertPhone');
                const twilioSidEl = document.getElementById('settingsTwilioSid');
                const twilioTokenEl = document.getElementById('settingsTwilioToken');
                const twilioFromEl = document.getElementById('settingsTwilioFrom');

                if (minRiskEl) minRiskEl.value = s.min_risk_level || 'MEDIUM';
                if (cooldownEl) cooldownEl.value = s.cooldown_seconds || 60;
                if (emailEnabledEl) emailEnabledEl.checked = Boolean(s.email_enabled);
                if (alertEmailEl) alertEmailEl.value = s.alert_email || '';
                if (smtpHostEl) smtpHostEl.value = s.smtp_host || 'smtp.gmail.com';
                if (smtpPortEl) smtpPortEl.value = s.smtp_port || 587;
                if (smtpUserEl) smtpUserEl.value = s.smtp_user || '';
                if (smtpPassEl) smtpPassEl.value = s.smtp_pass || '';

                if (smsEnabledEl) smsEnabledEl.checked = Boolean(s.sms_enabled);
                if (alertPhoneEl) alertPhoneEl.value = s.alert_phone || '';
                if (twilioSidEl) twilioSidEl.value = s.twilio_sid || '';
                if (twilioTokenEl) twilioTokenEl.value = s.twilio_token || '';
                if (twilioFromEl) twilioFromEl.value = s.twilio_from || '';

                if (activeBadge) {
                    const isConfigured = (s.email_enabled && s.alert_email) || (s.sms_enabled && s.alert_phone);
                    activeBadge.style.background = isConfigured ? '#10b981' : '#f59e0b';
                    activeBadge.title = isConfigured ? 'Alert notifications active' : 'Alert destinations not configured';
                }
            }
        } catch (e) {
            console.error('Failed to load alert settings:', e);
        }
    }

    // Load recent alert logs
    async function fetchAlertLogs() {
        const feed = document.getElementById('recentAlertsFeed');
        if (!feed) return;
        try {
            const res = await fetch('/api/alerts/logs');
            const data = await res.json();
            if (data.success && data.logs) {
                if (data.logs.length === 0) {
                    feed.innerHTML = '<div style="color: var(--text-muted); text-align: center; padding: 0.5rem;">No alerts dispatched yet.</div>';
                    return;
                }
                feed.innerHTML = data.logs.map((log) => {
                    const timeStr = log.timestamp ? log.timestamp.split('T')[1].split('.')[0] : '--:--:--';
                    const icon = log.channel === 'sms' ? '📱' : '📧';
                    let statusColor = '#10b981';
                    if (log.status === 'simulated') statusColor = '#3b82f6';
                    if (log.status === 'failed') statusColor = '#ef4444';

                    return `
                        <div style="display: flex; align-items: center; justify-content: space-between; border-bottom: 1px solid #f1f5f9; padding: 0.3rem 0;">
                            <div>
                                <span style="margin-right: 0.3rem;">${icon}</span>
                                <strong>[${log.risk_level}]</strong>
                                <span style="color: var(--text-primary); margin-left: 0.2rem;">${log.recipient}</span>
                                <span style="color: var(--text-muted); font-size: 0.7rem; margin-left: 0.3rem;">(${log.username})</span>
                            </div>
                            <div style="display: flex; align-items: center; gap: 0.5rem;">
                                <span style="background: ${statusColor}15; color: ${statusColor}; border: 1px solid ${statusColor}40; border-radius: 3px; padding: 0.1rem 0.4rem; font-weight: 600; font-size: 0.65rem; text-transform: uppercase;">${log.status}</span>
                                <span style="color: var(--text-muted); font-size: 0.65rem;">${timeStr}</span>
                            </div>
                        </div>
                    `;
                }).join('');
            }
        } catch (e) {
            console.error('Failed to load alert logs:', e);
        }
    }

    // Open Modal
    openBtn?.addEventListener('click', async () => {
        modal.classList.add('active');
        if (statusBanner) statusBanner.style.display = 'none';
        await fetchAlertSettings();
        await fetchAlertLogs();
    });

    // Close Modal
    function closeModal() {
        modal.classList.remove('active');
    }
    closeBtn?.addEventListener('click', closeModal);
    closeXBtn?.addEventListener('click', closeModal);

    // Save Settings
    saveBtn?.addEventListener('click', async () => {
        saveBtn.disabled = true;
        saveBtn.textContent = 'Saving...';
        try {
            const payload = {
                min_risk_level: document.getElementById('settingsMinRisk')?.value || 'MEDIUM',
                cooldown_seconds: parseInt(document.getElementById('settingsCooldown')?.value || '60', 10),
                email_enabled: document.getElementById('settingsEmailEnabled')?.checked ? 1 : 0,
                alert_email: document.getElementById('settingsAlertEmail')?.value.trim() || '',
                smtp_host: document.getElementById('settingsSmtpHost')?.value.trim() || 'smtp.gmail.com',
                smtp_port: parseInt(document.getElementById('settingsSmtpPort')?.value || '587', 10),
                smtp_user: document.getElementById('settingsSmtpUser')?.value.trim() || '',
                smtp_pass: document.getElementById('settingsSmtpPass')?.value.trim() || '',
                sms_enabled: document.getElementById('settingsSmsEnabled')?.checked ? 1 : 0,
                alert_phone: document.getElementById('settingsAlertPhone')?.value.trim() || '',
                twilio_sid: document.getElementById('settingsTwilioSid')?.value.trim() || '',
                twilio_token: document.getElementById('settingsTwilioToken')?.value.trim() || '',
                twilio_from: document.getElementById('settingsTwilioFrom')?.value.trim() || ''
            };

            const res = await fetch('/api/alerts/settings', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify(payload)
            });
            const data = await res.json();
            if (data.success) {
                if (statusBanner) {
                    statusBanner.style.display = 'block';
                    statusBanner.style.background = '#ecfdf5';
                    statusBanner.style.color = '#065f46';
                    statusBanner.style.border = '1px solid #a7f3d0';
                    statusBanner.textContent = '✅ Alert settings successfully saved!';
                }
                await fetchAlertSettings();
            } else if (statusBanner) {
                statusBanner.style.display = 'block';
                statusBanner.style.background = '#fef2f2';
                statusBanner.style.color = '#991b1b';
                statusBanner.style.border = '1px solid #fecaca';
                statusBanner.textContent = `Error: ${data.message || 'Failed to save settings'}`;
            }
        } catch (e) {
            if (statusBanner) {
                statusBanner.style.display = 'block';
                statusBanner.style.background = '#fef2f2';
                statusBanner.style.color = '#991b1b';
                statusBanner.style.border = '1px solid #fecaca';
                statusBanner.textContent = 'Network error saving settings.';
            }
        } finally {
            saveBtn.disabled = false;
            saveBtn.textContent = 'Save Settings';
        }
    });

    // Send Test Alert
    testBtn?.addEventListener('click', async () => {
        testBtn.disabled = true;
        testBtn.textContent = '⚡ Dispatching Test...';
        if (statusBanner) {
            statusBanner.style.display = 'block';
            statusBanner.style.background = '#eff6ff';
            statusBanner.style.color = '#1e40af';
            statusBanner.style.border = '1px solid #bfdbfe';
            statusBanner.textContent = 'Transmitting test alerts across configured channels...';
        }

        try {
            const payload = {
                email_enabled: document.getElementById('settingsEmailEnabled')?.checked ? 1 : 0,
                alert_email: document.getElementById('settingsAlertEmail')?.value.trim() || '',
                smtp_host: document.getElementById('settingsSmtpHost')?.value.trim() || 'smtp.gmail.com',
                smtp_port: parseInt(document.getElementById('settingsSmtpPort')?.value || '587', 10),
                smtp_user: document.getElementById('settingsSmtpUser')?.value.trim() || '',
                smtp_pass: document.getElementById('settingsSmtpPass')?.value.trim() || '',
                sms_enabled: document.getElementById('settingsSmsEnabled')?.checked ? 1 : 0,
                alert_phone: document.getElementById('settingsAlertPhone')?.value.trim() || '',
                twilio_sid: document.getElementById('settingsTwilioSid')?.value.trim() || '',
                twilio_token: document.getElementById('settingsTwilioToken')?.value.trim() || '',
                twilio_from: document.getElementById('settingsTwilioFrom')?.value.trim() || ''
            };

            const res = await fetch('/api/alerts/test', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify(payload)
            });
            const data = await res.json();
            if (data.success && data.results) {
                const emMsg = data.results.email?.message || 'Email: Skipped';
                const smsMsg = data.results.sms?.message || 'SMS: Skipped';
                if (statusBanner) {
                    statusBanner.style.background = '#f0fdf4';
                    statusBanner.style.color = '#166534';
                    statusBanner.style.border = '1px solid #bbf7d0';
                    statusBanner.innerHTML = `<strong>Test Alerts Dispatched:</strong><br>📧 ${emMsg}<br>📱 ${smsMsg}`;
                }
                await fetchAlertLogs();
            } else if (statusBanner) {
                statusBanner.textContent = `Test failed: ${data.message || 'Unknown error'}`;
            }
        } catch (e) {
            if (statusBanner) {
                statusBanner.textContent = 'Server communication error testing alerts.';
            }
        } finally {
            testBtn.disabled = false;
            testBtn.textContent = '⚡ Send Test Alert (SMS & Email)';
        }
    });

    refreshLogsBtn?.addEventListener('click', fetchAlertLogs);

    // Initial silent check on page load to set badge color
    fetchAlertSettings();
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
