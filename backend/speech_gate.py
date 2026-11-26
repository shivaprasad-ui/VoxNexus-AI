import io
import wave
from array import array


def has_speech(data: bytes, rms_thr: float = 0.02, min_active: float = 0.25) -> bool:
    """True if enough 50 ms frames of a 16-bit PCM WAV are louder than rms_thr."""
    try:
        with wave.open(io.BytesIO(data), "rb") as w:
            if w.getsampwidth() != 2:
                return True            # unknown format: don't block
            ch, rate = w.getnchannels(), w.getframerate()
            raw = w.readframes(w.getnframes())
    except Exception:
        return True                    # not a readable wav: let the normal path handle it
    samples = array("h")
    samples.frombytes(raw)
    frame = int(rate * 0.05) * ch
    if frame <= 0 or len(samples) < frame:
        return False
    active = total = 0
    for i in range(0, len(samples) - frame + 1, frame):
        chunk = samples[i:i + frame]
        rms = (sum(s * s for s in chunk) / frame) ** 0.5 / 32768.0
        active += rms > rms_thr
        total += 1
    return total > 0 and active / total >= min_active