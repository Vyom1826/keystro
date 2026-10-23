/**
 * KeyStro - Privacy-First Keystroke Timing Capture Engine
 * TRISHUL Hackathon Specification
 * 
 * STRICT PRIVACY PRINCIPLE:
 * Characters and text content are NEVER captured, buffered, or transmitted.
 * Only anonymized high-resolution timing intervals (dwell time, flight latency,
 * inter-key latency) are extracted for continuous biometric authentication.
 */

class KeystrokeRecorder {
    /**
     * @param {Object} options
     * @param {number} options.chunkSize - Number of keystrokes before emitting a verification chunk (default: 15)
     * @param {Function} options.onChunkReady - Callback when a rolling chunk of keystrokes is complete
     * @param {Function} options.onKeystroke - Callback on every individual keyup event for live HUD stream
     */
    constructor(options = {}) {
        this.chunkSize = options.chunkSize || 15;
        this.onChunkReady = options.onChunkReady || null;
        this.onKeystroke = options.onKeystroke || null;

        // Active keydown tracker: maps physical key code -> timestamp (ms)
        this.activeKeys = new Map();

        // Sequence records: array of anonymized timing tuples [{down, up, dwell, flight, latency}]
        this.recordedEvents = [];
        this.rollingBuffer = [];

        // Timing markers for sequential latencies
        this.lastKeyDownTime = null;
        this.lastKeyUpTime = null;

        // Simulation flag for imposter testing
        this.imposterMode = false;
        this.imposterProfile = 'slow_heavy'; // 'slow_heavy', 'robotic_fast', 'erratic'

        // Bound event handlers for clean attach/detach
        this._handleKeyDown = this._handleKeyDown.bind(this);
        this._handleKeyUp = this._handleKeyUp.bind(this);
        this.targetElement = null;
    }

    /**
     * Attaches listeners to a DOM element (input, textarea, or document)
     * @param {HTMLElement} element
     */
    attach(element) {
        if (this.targetElement) {
            this.detach();
        }
        this.targetElement = element;
        this.targetElement.addEventListener('keydown', this._handleKeyDown);
        this.targetElement.addEventListener('keyup', this._handleKeyUp);
    }

    /**
     * Detaches listeners
     */
    detach() {
        if (this.targetElement) {
            this.targetElement.removeEventListener('keydown', this._handleKeyDown);
            this.targetElement.removeEventListener('keyup', this._handleKeyUp);
            this.targetElement = null;
        }
        this.activeKeys.clear();
    }

    /**
     * Reset recorded buffers (e.g. starting a new passage)
     */
    reset() {
        this.activeKeys.clear();
        this.recordedEvents = [];
        this.rollingBuffer = [];
        this.lastKeyDownTime = null;
        this.lastKeyUpTime = null;
    }

    /**
     * Toggle imposter simulation mode
     * @param {boolean} active 
     * @param {string} profile - 'slow_heavy' | 'robotic_fast' | 'erratic'
     */
    setImposterMode(active, profile = 'slow_heavy') {
        this.imposterMode = active;
        this.imposterProfile = profile;
    }

    /**
     * Internal handler for keydown events
     * @private
     */
    _handleKeyDown(e) {
        // Ignore modifier keys that don't produce typing cadence alone
        if (['Alt', 'Meta', 'ContextMenu', 'CapsLock'].includes(e.key)) {
            return;
        }

        const now = performance.now();
        const code = e.code || e.keyCode;

        // Prevent repeated keydown events if key is held down
        if (this.activeKeys.has(code)) {
            return;
        }

        this.activeKeys.set(code, now);
    }

    /**
     * Internal handler for keyup events
     * @private
     */
    _handleKeyUp(e) {
        const code = e.code || e.keyCode;
        const now = performance.now();

        if (!this.activeKeys.has(code)) {
            return;
        }

        let tDown = this.activeKeys.get(code);
        let tUp = now;
        this.activeKeys.delete(code);

        // Calculate timing tuples
        let dwellTime = Math.max(15, tUp - tDown);
        let flightTime = this.lastKeyUpTime !== null ? Math.max(-80, tDown - this.lastKeyUpTime) : 100;
        let latency = this.lastKeyDownTime !== null ? Math.max(20, tDown - this.lastKeyDownTime) : dwellTime + flightTime;

        // Apply imposter perturbation if active
        if (this.imposterMode) {
            if (this.imposterProfile === 'slow_heavy') {
                dwellTime = dwellTime * 2.5 + (Math.random() * 80 + 60);
                flightTime = flightTime * 3.2 + (Math.random() * 250 + 150);
                latency = dwellTime + flightTime;
            } else if (this.imposterProfile === 'robotic_fast') {
                dwellTime = 38 + Math.random() * 8;
                flightTime = 30 + Math.random() * 10;
                latency = dwellTime + flightTime;
            } else if (this.imposterProfile === 'erratic') {
                dwellTime = Math.random() > 0.5 ? 40 : 380;
                flightTime = Math.random() > 0.4 ? 600 : 25;
                latency = dwellTime + flightTime;
            }
            tDown = (this.lastKeyUpTime || performance.now()) + flightTime;
            tUp = tDown + dwellTime;
        }

        this.lastKeyDownTime = tDown;
        this.lastKeyUpTime = tUp;

        // Create sanitized, privacy-safe record
        // Notice: NO characters or key identities are saved.
        const timingRecord = {
            down: Math.round(tDown * 10) / 10,
            up: Math.round(tUp * 10) / 10,
            dwell: Math.round(dwellTime * 10) / 10,
            flight: Math.round(flightTime * 10) / 10,
            latency: Math.round(latency * 10) / 10
        };

        this.recordedEvents.push(timingRecord);
        this.rollingBuffer.push(timingRecord);

        // Trigger individual keystroke telemetry update
        if (typeof this.onKeystroke === 'function') {
            this.onKeystroke(timingRecord, this.getInstantMetrics());
        }

        // Trigger rolling chunk when threshold reached
        if (this.rollingBuffer.length >= this.chunkSize) {
            const chunkToSend = [...this.rollingBuffer];
            // Slide window by maintaining 40% overlap for smooth continuity
            const step = Math.max(1, Math.floor(this.chunkSize * 0.6));
            this.rollingBuffer = this.rollingBuffer.slice(step);

            if (typeof this.onChunkReady === 'function') {
                this.onChunkReady(chunkToSend, this.imposterMode);
            }
        }
    }

    /**
     * Computes quick instant metrics for the live HUD
     */
    getInstantMetrics() {
        const recent = this.recordedEvents.slice(-10);
        if (recent.length === 0) {
            return { avgDwell: 0, avgFlight: 0, kpm: 0 };
        }

        const avgDwell = recent.reduce((acc, c) => acc + c.dwell, 0) / recent.length;
        const avgFlight = recent.reduce((acc, c) => acc + c.flight, 0) / recent.length;

        // Keystrokes per minute estimate over last window
        let kpm = 0;
        if (recent.length > 2) {
            const spanMs = recent[recent.length - 1].up - recent[0].down;
            if (spanMs > 0) {
                kpm = Math.round((recent.length / (spanMs / 60000)));
            }
        }

        return {
            avgDwell: Math.round(avgDwell),
            avgFlight: Math.round(avgFlight),
            kpm: Math.min(999, Math.max(0, kpm))
        };
    }

    /**
     * Returns full array of recorded events (e.g. for enrollment passages)
     */
    getRecordedData() {
        return [...this.recordedEvents];
    }
}

// Export for browser environment
if (typeof window !== 'undefined') {
    window.KeystrokeRecorder = KeystrokeRecorder;
}
