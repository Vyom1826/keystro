/**
 * KeyStro - Typing Calibration & Testing Prompts Pool
 * Provides diverse, technical cybersecurity sentences for random prompt generation.
 */

const RANDOM_PROMPT_POOL = [
    "Security zero trust architecture verifies user identity dynamically throughout the session.",
    "Continuous keystroke authentication protects active cloud sessions without interruption.",
    "Behavioral biometrics evaluate typing rhythm flight latency and key dwell durations.",
    "Adaptive multi factor authentication triggers verification when anomaly scores spike.",
    "The encryption keys are refreshed every thirty seconds to prevent replay attacks.",
    "Network packets travel through secure encrypted tunnels across distributed data centers.",
    "Biometric keystroke timing dynamics represent a unique behavioral fingerprint for every person.",
    "Machine learning classifiers detect anomalous keystroke latency patterns in milliseconds.",
    "Cloud infrastructure monitoring prevents unauthorized privilege escalation and session hijacking.",
    "Cryptographic signatures guarantee message integrity and tamper-proof audit trails.",
    "The automated firewall blocked suspicious brute force attempts from an unfamiliar subnet.",
    "Neural network embeddings project complex typing rhythms into multidimensional metric spaces.",
    "High velocity financial transactions require continuous behavioral risk assessment.",
    "Zero day vulnerability patches were deployed across all isolated Kubernetes clusters.",
    "Digital identity governance combines behavioral biometrics with context-aware access policies.",
    "Distributed consensus algorithms ensure data consistency across multiple global cloud nodes.",
    "Latency measurements between key release and next key press reveal distinct cognitive habits.",
    "Software engineers commit verified code snippets to secure microservice repositories daily.",
    "Real-time telemetry streams display dwell intervals and inter-key latency distributions.",
    "The quantum-resistant cryptographic algorithm secures confidential corporate transmissions.",
    "Anomalous session activity triggers immediate step-up multi factor authentication challenges.",
    "Behavioral profiling isolates malicious automated bots from legitimate corporate personnel.",
    "Secure socket layer protocols establish mutual authentication across all distributed endpoints.",
    "Key stroke duration and transition latencies fluctuate naturally with operator fatigue.",
    "Privileged access management enforces least privilege principles across production clusters.",
    "Decentralized identity networks validate cryptographically verifiable credentials securely.",
    "Real-time telemetry analytics calculate equal error rates and false rejection probabilities.",
    "The neural anomaly detector evaluates rolling typing chunks to detect session hijackers.",
    "Continuous behavioral verification operates completely transparently in the background.",
    "Modern cloud native microservices communicate via mutual transport layer security tunnels."
];

/**
 * Returns a random prompt from the pool, optionally excluding already chosen sentences.
 * @param {string[]} exclude
 * @returns {string}
 */
function getRandomPrompt(exclude = []) {
    const available = RANDOM_PROMPT_POOL.filter(p => !exclude.includes(p));
    const pool = available.length > 0 ? available : RANDOM_PROMPT_POOL;
    return pool[Math.floor(Math.random() * pool.length)];
}

/**
 * Generates an array of unique random passages.
 * @param {number} count
 * @returns {string[]}
 */
function generateRandomPassages(count = 3) {
    const selected = [];
    for (let i = 0; i < count; i++) {
        selected.push(getRandomPrompt(selected));
    }
    return selected;
}
