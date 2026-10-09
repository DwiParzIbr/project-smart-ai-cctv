// Native Web Audio API Alert Sound Synthesizer
let audioCtx = null;
let soundEnabled = true;

function getAudioContext() {
    if (!audioCtx) {
        const AudioContext = window.AudioContext || window.webkitAudioContext;
        audioCtx = new AudioContext();
    }
    if (audioCtx.state === 'suspended') {
        audioCtx.resume();
    }
    return audioCtx;
}

function playSecurityAlarm() {
    if (!soundEnabled) return;

    try {
        const ctx = getAudioContext();
        const now = ctx.currentTime;

        // Two-tone emergency siren
        const osc = ctx.createOscillator();
        const gain = ctx.createGain();

        osc.type = 'sawtooth';
        // Tone 1
        osc.frequency.setValueAtTime(880, now);
        // Tone 2
        osc.frequency.setValueAtTime(587.33, now + 0.15);
        osc.frequency.setValueAtTime(880, now + 0.30);
        osc.frequency.setValueAtTime(587.33, now + 0.45);

        gain.gain.setValueAtTime(0.3, now);
        gain.gain.exponentialRampToValueAtTime(0.01, now + 0.6);

        osc.connect(gain);
        gain.connect(ctx.destination);

        osc.start(now);
        osc.stop(now + 0.6);
    } catch (e) {
        console.warn("[AlertSound] AudioContext autoplay blocked or unsupported:", e);
    }
}

function toggleSound() {
    soundEnabled = !soundEnabled;
    const btn = document.getElementById("soundToggleBtn");
    if (btn) {
        btn.innerHTML = soundEnabled ? '🔔 Suara: ON' : '🔕 Suara: OFF';
        btn.className = soundEnabled 
            ? 'px-3 py-1.5 rounded-lg text-xs font-semibold bg-emerald-600/30 text-emerald-400 border border-emerald-500/40 hover:bg-emerald-600/50 transition' 
            : 'px-3 py-1.5 rounded-lg text-xs font-semibold bg-red-600/30 text-red-400 border border-red-500/40 hover:bg-red-600/50 transition';
    }
    // Prime audio context on user interaction
    getAudioContext();
}
