/**
 * KeyStro - Real-Time Telemetry Stream & Identity Confidence HUD
 * Renders Chart.js live latency streams and animated SVG risk gauge meters.
 */

/**
 * Initializes the Chart.js real-time telemetry stream chart.
 */
function initTelemetryChart() {
    const ctx = document.getElementById('telemetryChart');
    if (!ctx) return;

    const maxPoints = 20;
    const initialLabels = Array.from({ length: maxPoints }, (_, i) => `${i + 1}`);

    State.telemetryChart = new Chart(ctx, {
        type: 'line',
        data: {
            labels: initialLabels,
            datasets: [
                {
                    label: 'Dwell Time (ms)',
                    data: Array(maxPoints).fill(90),
                    borderColor: '#06b6d4',
                    backgroundColor: 'rgba(6, 182, 212, 0.1)',
                    borderWidth: 2,
                    tension: 0.35,
                    fill: false,
                    pointRadius: 2
                },
                {
                    label: 'Flight Latency (ms)',
                    data: Array(maxPoints).fill(110),
                    borderColor: '#3b82f6',
                    backgroundColor: 'rgba(59, 130, 246, 0.1)',
                    borderWidth: 2,
                    tension: 0.35,
                    fill: false,
                    pointRadius: 2
                }
            ]
        },
        options: {
            responsive: true,
            maintainAspectRatio: false,
            animation: false,
            scales: {
                x: {
                    display: false,
                    grid: { display: false }
                },
                y: {
                    beginAtZero: false,
                    min: 10,
                    max: 450,
                    grid: { color: 'rgba(0, 0, 0, 0.06)' },
                    ticks: {
                        color: '#64748b',
                        font: { size: 10, family: 'monospace' }
                    }
                }
            },
            plugins: {
                legend: {
                    position: 'top',
                    labels: {
                        boxWidth: 12,
                        color: '#475569',
                        font: { size: 11 }
                    }
                },
                tooltip: {
                    enabled: true,
                    callbacks: {
                        label: (ctx) => ` ${ctx.dataset.label}: ${Math.round(ctx.parsed.y)} ms`
                    }
                }
            }
        }
    });
}

/**
 * Pushes new dwell and flight intervals onto the live telemetry stream.
 * @param {number} dwell
 * @param {number} flight
 */
function updateTelemetryChart(dwell, flight) {
    if (!State.telemetryChart) return;

    const datasets = State.telemetryChart.data.datasets;
    // Dwell
    datasets[0].data.shift();
    datasets[0].data.push(Math.round(dwell));
    // Flight
    datasets[1].data.shift();
    datasets[1].data.push(Math.round(flight));

    State.telemetryChart.update();
}

/**
 * Updates the SVG circular identity gauge, readout %, and risk level banner.
 * @param {number} score - Confidence score in [0.0, 1.0]
 * @param {string} riskLevel - 'LOW' | 'MEDIUM' | 'HIGH'
 * @param {string} actionTaken - 'allowed' | 'warned' | 'locked'
 * @param {string} [statusMessage]
 */
function updateConfidenceDisplay(score, riskLevel, actionTaken, statusMessage = null) {
    const scorePercent = Math.round(score * 100);
    const gaugeValueText = document.getElementById('gaugeValueText');
    const gaugeFillPath = document.getElementById('gaugeFillPath');
    const riskBanner = document.getElementById('riskLevelBanner');
    const riskDesc = document.getElementById('riskStatusDesc');
    const statusBadge = document.getElementById('sessionStatusBadge');
    const statusText = document.getElementById('sessionStatusText');

    if (!gaugeValueText || !gaugeFillPath) return;

    gaugeValueText.textContent = `${scorePercent}%`;

    // SVG arc stroke-dasharray is 251.2; offset maps from 251.2 (0%) down to 0 (100%)
    const maxOffset = 251.2;
    const targetOffset = maxOffset - (score * maxOffset);
    gaugeFillPath.style.strokeDashoffset = targetOffset;

    // Palette & states according to hackathon specifications
    if (score >= 0.70) {
        // Genuine User -> Low Risk
        gaugeValueText.style.color = 'var(--secure-green)';
        gaugeFillPath.style.stroke = 'var(--secure-green)';

        if (riskBanner) {
            riskBanner.textContent = 'LOW RISK • GENUINE OPERATOR';
            riskBanner.style.background = 'rgba(16, 185, 129, 0.15)';
            riskBanner.style.color = 'var(--secure-green)';
            riskBanner.style.borderColor = 'rgba(16, 185, 129, 0.3)';
        }

        if (riskDesc) {
            riskDesc.textContent = statusMessage || 'Active typing rhythm closely matches enrolled behavioral biometric baseline.';
        }

        if (statusBadge && statusText) {
            statusBadge.className = 'session-badge status-secure';
            statusText.innerHTML = 'ACTIVE &bull; VERIFIED';
        }
    } else if (score >= 0.40) {
        // Uncertain / Fatigue -> Medium Risk
        gaugeValueText.style.color = 'var(--warning-amber)';
        gaugeFillPath.style.stroke = 'var(--warning-amber)';

        if (riskBanner) {
            riskBanner.textContent = 'MEDIUM RISK • CADENCE DRIFT';
            riskBanner.style.background = 'rgba(245, 158, 11, 0.15)';
            riskBanner.style.color = 'var(--warning-amber)';
            riskBanner.style.borderColor = 'rgba(245, 158, 11, 0.3)';
        }

        if (riskDesc) {
            riskDesc.textContent = statusMessage || 'Typing rhythm variations detected (fatigue or hesitation). Elevated monitoring active.';
        }

        if (statusBadge && statusText) {
            statusBadge.className = 'session-badge status-warning';
            statusText.innerHTML = 'WARNING &bull; ELEVATED RISK';
        }
    } else {
        // Anomaly / Imposter -> High Risk
        gaugeValueText.style.color = 'var(--danger-red)';
        gaugeFillPath.style.stroke = 'var(--danger-red)';

        if (riskBanner) {
            riskBanner.textContent = 'HIGH RISK • ANOMALY DETECTED';
            riskBanner.style.background = 'rgba(239, 68, 68, 0.2)';
            riskBanner.style.color = 'var(--danger-red)';
            riskBanner.style.borderColor = 'rgba(239, 68, 68, 0.4)';
        }

        if (riskDesc) {
            riskDesc.textContent = statusMessage || 'Severe divergence in dwell time and flight latency. Potential unauthorized session takeover.';
        }

        if (statusBadge && statusText) {
            statusBadge.className = 'session-badge status-locked';
            statusText.innerHTML = 'LOCKED &bull; MFA CHALLENGE';
        }
    }
}
