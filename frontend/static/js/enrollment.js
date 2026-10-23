/**
 * KeyStro - Enrollment & Calibration Flow
 * Strict character-by-character validation, typo blocking, green/red live feedback,
 * and per-user biometric baseline calibration.
 */

/**
 * Initializes the 3-passage enrollment calibration flow.
 */
function initEnrollmentFlow() {
    const enrollmentInput = document.getElementById('enrollmentInput');
    const enrollSubmitBtn = document.getElementById('enrollSubmitPassageBtn');
    const enrollUsername = document.getElementById('enrollUsername');
    const enrollKeyCount = document.getElementById('enrollKeyCount');
    const summaryBox = document.getElementById('enrollmentSummaryBox');
    const switchActiveBtn = document.getElementById('switchActiveToEnrolledBtn');

    if (!enrollmentInput) return;

    // Set initial prompt & baseline validation state
    updateEnrollmentPrompt();
    updateEnrollmentTypingValidation();

    // Recorder attached to enrollment input (collects raw timing intervals)
    State.enrollmentRecorder = new KeystrokeRecorder({
        chunkSize: 999, // Collect all keystrokes for the entire passage
        onKeystroke: () => {
            const count = State.enrollmentRecorder.getRecordedData().length;
            if (enrollKeyCount) enrollKeyCount.textContent = count;
        }
    });
    State.enrollmentRecorder.attach(enrollmentInput);

    // Disable pasting so biometric rhythm is accurately captured from physical keys
    enrollmentInput.addEventListener('paste', (e) => {
        e.preventDefault();
        alert('Pasting is disabled during biometric calibration. Please type the passage on your keyboard.');
    });

    // Enter key submits passage if accurately complete
    enrollmentInput.addEventListener('keydown', (e) => {
        if (e.key === 'Enter') {
            e.preventDefault();
            if (!enrollSubmitBtn.disabled) {
                enrollSubmitBtn.click();
            } else {
                const banner = document.getElementById('enrollFeedback');
                banner?.classList.add('shake-feedback');
                setTimeout(() => banner?.classList.remove('shake-feedback'), 450);
            }
        }
    });

    // Real-time character-by-character validation: wrong typing is NEVER considered right!
    enrollmentInput.addEventListener('input', () => {
        updateEnrollmentTypingValidation();
    });

    // Randomize text button handler
    document.getElementById('randomizePromptBtn')?.addEventListener('click', () => {
        const current = State.enrollment.passages[State.enrollment.currentStep];
        const fresh = getRandomPrompt([current]);
        State.enrollment.passages[State.enrollment.currentStep] = fresh;

        enrollmentInput.value = '';
        State.enrollmentRecorder.reset();
        if (enrollKeyCount) enrollKeyCount.textContent = '0';
        updateEnrollmentPrompt();
        updateEnrollmentTypingValidation();
        enrollmentInput.focus();
    });

    // Submit Passage Button
    enrollSubmitBtn?.addEventListener('click', async () => {
        const username = enrollUsername.value.trim();
        if (!username) {
            alert('Please enter a username for this profile.');
            enrollUsername.focus();
            return;
        }

        const target = State.enrollment.passages[State.enrollment.currentStep] || '';
        const typed = enrollmentInput.value;

        // Strict verification: text MUST match target exactly without uncorrected typos
        if (typed.trim() !== target.trim()) {
            alert('Please type the passage accurately without typos before submitting.');
            enrollmentInput.focus();
            return;
        }

        const events = State.enrollmentRecorder.getRecordedData();
        if (events.length < 25) {
            alert('Please type more of the passage to capture your rhythm accurately.');
            return;
        }

        State.enrollment.collectedPassages.push(events);
        State.enrollment.currentStep++;

        // Update stepper indicators
        updateStepper(State.enrollment.currentStep);

        // Clear for next passage
        enrollmentInput.value = '';
        State.enrollmentRecorder.reset();
        if (enrollKeyCount) enrollKeyCount.textContent = '0';
        enrollSubmitBtn.disabled = true;

        if (State.enrollment.currentStep < State.enrollment.passages.length) {
            // Next passage
            updateEnrollmentPrompt();
            updateEnrollmentTypingValidation();
            enrollSubmitBtn.innerHTML = `Submit Passage ${State.enrollment.currentStep + 1} &rarr;`;
            enrollmentInput.focus();
        } else {
            // All passages complete -> Submit to /api/enroll
            enrollSubmitBtn.innerHTML = 'Training AI Models...';
            await completeEnrollment(username);
        }
    });

    switchActiveBtn?.addEventListener('click', () => {
        // Switch to workspace tab
        document.querySelector('.tab-btn[data-tab="workspacePane"]')?.click();
    });
}

/**
 * Strict character-by-character typing validator.
 * Compares typed input with target passage and dynamically renders:
 * - Green for matching prefix characters
 * - Bright Red with wavy underline for mistyped characters / typos
 * - Muted Grey for untyped remaining text
 * - Blocks passage submission unless 100% accurate and complete
 */
function updateEnrollmentTypingValidation() {
    const enrollmentInput = document.getElementById('enrollmentInput');
    const enrollSubmitBtn = document.getElementById('enrollSubmitPassageBtn');
    const promptTyped = document.getElementById('promptTyped');
    const promptError = document.getElementById('promptError');
    const promptRemaining = document.getElementById('promptRemaining');
    const promptBox = document.getElementById('enrollmentPromptBox');
    const feedbackBanner = document.getElementById('enrollFeedback');
    const feedbackText = document.getElementById('enrollFeedbackText');
    const feedbackIcon = feedbackBanner?.querySelector('.feedback-icon');
    const accuracyBadge = document.getElementById('enrollAccuracyBadge');
    const progressRatio = document.getElementById('enrollProgressRatio');
    const passageStatus = document.getElementById('enrollPassageStatus');

    if (!enrollmentInput) return;

    const target = State.enrollment.passages[State.enrollment.currentStep] || '';
    const typed = enrollmentInput.value;
    const targetLen = target.length;
    const typedLen = typed.length;

    // 1. Find index of first mismatch
    let mismatchIndex = -1;
    const minLen = Math.min(typedLen, targetLen);
    for (let i = 0; i < minLen; i++) {
        if (typed[i] !== target[i]) {
            mismatchIndex = i;
            break;
        }
    }

    // Flag extra characters typed beyond target length
    if (mismatchIndex === -1 && typedLen > targetLen) {
        mismatchIndex = targetLen;
    }

    const hasError = (mismatchIndex !== -1);
    const isCompleted = (!hasError && typedLen === targetLen && targetLen > 0);

    // 2. Render target prompt breakdown (Green = Correct, Red = Typo, Grey = Remaining)
    if (promptTyped && promptRemaining) {
        if (!hasError) {
            promptTyped.textContent = target.slice(0, typedLen);
            if (promptError) promptError.textContent = '';
            promptRemaining.textContent = target.slice(typedLen);
        } else {
            promptTyped.textContent = target.slice(0, mismatchIndex);

            if (promptError) {
                if (typedLen <= targetLen) {
                    promptError.textContent = target.slice(mismatchIndex, typedLen);
                } else {
                    const extraChars = typed.slice(targetLen);
                    promptError.textContent = target.slice(mismatchIndex, targetLen) + ` [${extraChars}]`;
                }
            }

            const remainingStart = Math.min(typedLen, targetLen);
            promptRemaining.textContent = target.slice(remainingStart);
        }
    }

    // 3. Compute real-time accuracy percentage
    let accuracyPct = 100;
    if (typedLen > 0) {
        if (hasError) {
            const errorChars = typedLen - mismatchIndex;
            accuracyPct = Math.max(0, Math.round(((typedLen - errorChars) / typedLen) * 100));
        } else {
            accuracyPct = 100;
        }
    }

    // 4. Update HUD progress & accuracy badges
    if (progressRatio) {
        progressRatio.textContent = `${Math.min(typedLen, targetLen)} / ${targetLen} chars`;
    }

    if (accuracyBadge) {
        accuracyBadge.textContent = `${accuracyPct}% Accuracy`;
        accuracyBadge.className = 'accuracy-badge';
        if (accuracyPct === 100) {
            accuracyBadge.classList.add('accuracy-perfect');
        } else if (accuracyPct >= 80) {
            accuracyBadge.classList.add('accuracy-warning');
        } else {
            accuracyBadge.classList.add('accuracy-danger');
        }
    }

    // 5. Update UI feedback banner and styles
    enrollmentInput.classList.remove('has-error', 'is-complete');
    promptBox?.classList.remove('prompt-box-error', 'prompt-box-success');
    feedbackBanner?.classList.remove('feedback-error', 'feedback-success', 'feedback-idle');

    if (typedLen === 0) {
        feedbackBanner?.classList.add('feedback-idle');
        if (feedbackIcon) feedbackIcon.textContent = '⌨';
        if (feedbackText) feedbackText.textContent = 'Type the exact passage above to calibrate your rhythm profile.';
        if (passageStatus) {
            passageStatus.textContent = 'Awaiting typing...';
            passageStatus.style.color = 'var(--text-muted)';
        }
        if (enrollSubmitBtn) enrollSubmitBtn.disabled = true;
    } else if (hasError) {
        // TYPO / WRONG INPUT DETECTED
        enrollmentInput.classList.add('has-error');
        promptBox?.classList.add('prompt-box-error');
        feedbackBanner?.classList.add('feedback-error');

        const expectedChar = mismatchIndex < targetLen ? `"${target[mismatchIndex]}"` : 'end of passage';
        const typedChar = mismatchIndex < typedLen ? `"${typed[mismatchIndex]}"` : 'extra input';

        if (feedbackIcon) feedbackIcon.textContent = '⚠';
        if (feedbackText) {
            feedbackText.innerHTML = `<strong>Typo detected at char ${mismatchIndex + 1}!</strong> Expected <code>${expectedChar}</code>, received <code>${typedChar}</code>. Press <strong>Backspace</strong> to fix.`;
        }
        if (passageStatus) {
            passageStatus.textContent = 'Typo detected - fix before submitting';
            passageStatus.style.color = 'var(--danger-red)';
        }

        // WRONG TYPING IS NEVER ACCEPTED AS RIGHT! SUBMISSION STRICTLY DISABLED!
        if (enrollSubmitBtn) enrollSubmitBtn.disabled = true;
    } else if (isCompleted) {
        // 100% ACCURATE AND COMPLETE
        enrollmentInput.classList.add('is-complete');
        promptBox?.classList.add('prompt-box-success');
        feedbackBanner?.classList.add('feedback-success');

        if (feedbackIcon) feedbackIcon.textContent = '✓';
        if (feedbackText) {
            feedbackText.innerHTML = `<strong>Passage completed accurately (100%)!</strong> Click submit below or press <strong>Enter</strong> to continue.`;
        }
        if (passageStatus) {
            passageStatus.textContent = 'Passage 100% complete & verified';
            passageStatus.style.color = 'var(--secure-green)';
        }

        // Enable submission now that the passage is typed accurately
        if (enrollSubmitBtn) enrollSubmitBtn.disabled = false;
    } else {
        // TYPING IN PROGRESS - 100% ACCURATE SO FAR
        if (feedbackIcon) feedbackIcon.textContent = '✓';
        if (feedbackText) {
            feedbackText.textContent = `Typing accurately matches baseline passage. (${targetLen - typedLen} characters remaining)`;
        }
        if (passageStatus) {
            passageStatus.textContent = `In progress (${typedLen}/${targetLen} chars)`;
            passageStatus.style.color = 'var(--accent-cyan)';
        }

        // Keep disabled until passage is completed
        if (enrollSubmitBtn) enrollSubmitBtn.disabled = true;
    }
}

function updateEnrollmentPrompt() {
    const currentPassage = State.enrollment.passages[State.enrollment.currentStep] || '';
    const promptTyped = document.getElementById('promptTyped');
    const promptError = document.getElementById('promptError');
    const promptRemaining = document.getElementById('promptRemaining');
    const stepIndicator = document.getElementById('promptStepIndicator');

    if (stepIndicator) {
        stepIndicator.textContent = `Passage ${State.enrollment.currentStep + 1} of 3`;
    }

    if (promptTyped) promptTyped.textContent = '';
    if (promptError) promptError.textContent = '';
    if (promptRemaining) promptRemaining.textContent = currentPassage;
}

function updateStepper(step) {
    for (let i = 1; i <= 3; i++) {
        const el = document.getElementById(`step${i}`);
        if (!el) continue;
        if (i < step + 1) {
            el.className = 'step-item completed';
        } else if (i === step + 1) {
            el.className = 'step-item active';
        } else {
            el.className = 'step-item';
        }
    }
    const step4 = document.getElementById('step4');
    if (step4 && step >= 3) {
        step4.className = 'step-item completed';
    }
}

async function completeEnrollment(username) {
    try {
        const payload = {
            username: username,
            passages: State.enrollment.collectedPassages
        };

        const res = await fetch('/api/enroll', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(payload)
        });

        const data = await res.json();

        if (data.success) {
            // Reset passages with fresh random set for the next enrollment
            State.enrollment.passages = generateRandomPassages(3);
            State.enrollment.currentStep = 0;
            State.enrollment.collectedPassages = [];

            // Show summary
            const summaryBox = document.getElementById('enrollmentSummaryBox');
            if (summaryBox) {
                summaryBox.style.display = 'block';
                document.getElementById('summaryDwell').textContent = `${data.baseline.dwell_mean} ms`;
                document.getElementById('summaryFlight').textContent = `${data.baseline.flight_mean} ms`;
                document.getElementById('summarySpeed').textContent = `${data.baseline.speed_kpm} KPM`;
            }

            // Reload user dropdown and switch to newly enrolled user
            await loadUsers(username);

            document.getElementById('enrollSubmitPassageBtn').textContent = 'Enrollment Complete';
        } else {
            alert(data.error || 'Enrollment failed.');
        }
    } catch (e) {
        alert('Server communication error during enrollment.');
    }
}
