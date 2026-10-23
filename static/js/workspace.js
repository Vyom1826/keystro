/**
 * KeyStro - Active Monitored Workspace & Imposter Simulator
 * Controls the typing sandbox, imposter attack injector, and instant HUD stats.
 */

let lastEditorWordCount = 0;

/**
 * Initializes the keystroke recorder attached to the monitored workspace editor.
 */
function initWorkspaceRecorder() {
    const workspaceInput = document.getElementById('workspaceInput');
    if (!workspaceInput) return;

    // Track word count from live typing
    workspaceInput.addEventListener('input', () => {
        const text = (workspaceInput.value || '').trim();
        const currentWords = text ? text.split(/\s+/).filter(Boolean).length : 0;
        State.currentEditorWords = currentWords;
    });

    State.recorder = new KeystrokeRecorder({
        chunkSize: 15,
        onKeystroke: (timing, instant) => {
            // Live HUD instant stats
            const speedEl = document.getElementById('hudSpeed');
            const dwellEl = document.getElementById('hudDwell');
            const flightEl = document.getElementById('hudFlight');

            if (speedEl) speedEl.textContent = `${instant.kpm} KPM`;
            if (dwellEl) dwellEl.textContent = `${instant.avgDwell} ms`;
            if (flightEl) flightEl.textContent = `${instant.avgFlight} ms`;

            // Push to real-time latency chart
            updateTelemetryChart(timing.dwell, timing.flight);
        },
        onChunkReady: (chunk, isImposter) => {
            if (!State.isLocked && State.sessionId) {
                const text = (workspaceInput.value || '').trim();
                const currentWords = text ? text.split(/\s+/).filter(Boolean).length : 0;
                const wordsInChunk = Math.max(1, Math.min(6, currentWords - lastEditorWordCount || 2));
                lastEditorWordCount = currentWords;

                verifyKeystrokeChunk(chunk, isImposter, wordsInChunk);
            }
        }
    });

    State.recorder.attach(workspaceInput);

    // Clear Editor Button
    document.getElementById('clearWorkspaceBtn')?.addEventListener('click', () => {
        workspaceInput.value = '';
        lastEditorWordCount = 0;
        State.recorder.reset();
    });
}

/**
 * Initializes the Imposter Mode toggle and quick burst simulation buttons.
 */
function initImposterControls() {
    const toggle = document.getElementById('imposterToggle');
    const profileSelect = document.getElementById('imposterProfile');
    const injectGenuineBtn = document.getElementById('injectGenuineBtn');
    const inject200WordsBtn = document.getElementById('inject200WordsBtn');
    const injectImposterBtn = document.getElementById('injectImposterBtn');
    const loadRandomTextBtn = document.getElementById('loadRandomTextBtn');

    toggle?.addEventListener('change', (e) => {
        const active = e.target.checked;
        const profile = profileSelect?.value || 'slow_heavy';
        State.recorder?.setImposterMode(active, profile);
    });

    profileSelect?.addEventListener('change', (e) => {
        const active = toggle?.checked || false;
        State.recorder?.setImposterMode(active, e.target.value);
    });

    // Quick burst: Genuine typing simulation
    injectGenuineBtn?.addEventListener('click', async () => {
        if (!State.sessionId || State.isLocked) return;
        injectGenuineBtn.disabled = true;
        injectGenuineBtn.textContent = 'Transmitting genuine cadence...';

        const syntheticGenuine = generateSyntheticChunk(State.currentUser, false);
        await verifyKeystrokeChunk(syntheticGenuine, false, 3);

        injectGenuineBtn.disabled = false;
        injectGenuineBtn.innerHTML = '&plus; Inject Genuine Typing Burst';
    });

    // Fast-Forward: 200 Words Continuous Learning & Model Retraining
    inject200WordsBtn?.addEventListener('click', async () => {
        if (!State.sessionId || State.isLocked) return;
        inject200WordsBtn.disabled = true;
        inject200WordsBtn.textContent = 'Retraining ahead on 200 words...';

        try {
            const res = await fetch('/api/adapt-model', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({
                    session_id: State.sessionId,
                    username: State.currentUser,
                    word_count: 200
                })
            });
            const data = await res.json();
            if (data.success) {
                if (data.continuous_learning) {
                    handleContinuousLearningUpdate(data.continuous_learning, data.adaptation);
                }
                if (data.adaptation) {
                    showAdaptationBanner(data.adaptation);
                }
            }
        } catch (err) {
            console.error('Failed to train ahead:', err);
        } finally {
            inject200WordsBtn.disabled = false;
            inject200WordsBtn.innerHTML = '⚡ Fast-Forward 200 Words (Train Ahead)';
        }
    });

    // Quick burst: Imposter attack simulation
    injectImposterBtn?.addEventListener('click', async () => {
        if (!State.sessionId || State.isLocked) return;
        injectImposterBtn.disabled = true;
        injectImposterBtn.textContent = 'Simulating attack burst...';

        const syntheticImposter = generateSyntheticChunk(State.currentUser, true);
        await verifyKeystrokeChunk(syntheticImposter, true);

        injectImposterBtn.disabled = false;
        injectImposterBtn.innerHTML = '&times; Inject Imposter Attack Burst';
    });

    // Load random prompt into active workspace editor
    loadRandomTextBtn?.addEventListener('click', () => {
        const workspaceInput = document.getElementById('workspaceInput');
        if (workspaceInput) {
            const randomSentence = getRandomPrompt();
            workspaceInput.value = randomSentence;
            workspaceInput.focus();
            State.recorder?.reset();
        }
    });

    // Retrain Model Button
    const retrainModelBtn = document.getElementById('retrainModelBtn');
    retrainModelBtn?.addEventListener('click', async () => {
        if (!State.currentUser) {
            alert('Please select an active user profile first.');
            return;
        }
        retrainModelBtn.disabled = true;
        retrainModelBtn.textContent = '🔄 Retraining Model...';

        try {
            const res = await fetch('/api/retrain-model', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ username: State.currentUser })
            });
            const data = await res.json();
            if (data.success) {
                const dwell = data.baseline?.dwell_mean ?? data.baseline?.avg_dwell ?? '--';
                const flight = data.baseline?.flight_mean ?? data.baseline?.avg_flight ?? '--';
                const samples = data.baseline?.sample_count ?? data.sample_count ?? '';
                alert(`✅ Model successfully retrained for ${State.currentUser}!\nBaseline: Dwell ${dwell}ms, Flight ${flight}ms (${samples} training samples).`);
                if (typeof loadUsers === 'function') {
                    await loadUsers();
                }
                if (typeof selectUser === 'function') {
                    selectUser(State.currentUser);
                }
            } else {
                alert(`Retrain failed: ${data.error || 'Unknown error'}`);
            }
        } catch (err) {
            console.error('Error retraining model:', err);
            alert('Network error while requesting model retrain.');
        } finally {
            retrainModelBtn.disabled = false;
            retrainModelBtn.innerHTML = '🔄 Retrain Model';
        }
    });
}

/**
 * Generates synthetic keystroke timing intervals with specific dwell/flight baselines.
 * @param {number} dwellBase
 * @param {number} flightBase
 * @returns {Array<{down: number, up: number}>}
 */
function generateSyntheticChunkWithParams(dwellBase, flightBase) {
    const events = [];
    let curTime = performance.now();
    for (let i = 0; i < 15; i++) {
        const dt = Math.max(20, dwellBase + (Math.random() * 20 - 10));
        const ft = Math.max(15, flightBase + (Math.random() * 30 - 15));
        const tDown = curTime;
        const tUp = tDown + dt;
        events.push({
            down: Math.round(tDown * 10) / 10,
            up: Math.round(tUp * 10) / 10
        });
        curTime = tUp + ft;
    }
    return events;
}

/**
 * Generates a synthetic burst for a user or imposter.
 * @param {string} username
 * @param {boolean} isImposter
 * @returns {Array<{down: number, up: number}>}
 */
function generateSyntheticChunk(username, isImposter) {
    if (isImposter) {
        return generateSyntheticChunkWithParams(280.0, 420.0);
    }
    const foundUser = State.usersList.find(u => u.username === username);
    if (foundUser && foundUser.avg_dwell && foundUser.avg_flight) {
        return generateSyntheticChunkWithParams(foundUser.avg_dwell, foundUser.avg_flight);
    }
    return generateSyntheticChunkWithParams(85.0, 80.0);
}
