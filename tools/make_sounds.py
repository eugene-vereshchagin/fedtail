"""Make fedtail's own sound sets: plain synthesis, no samples of anyone's — so the files are
ours (GPL-3, like the code) and can be made again from this script.

    python3 tools/make_sounds.py            # write every set into fedtail/data/
    python3 tools/make_sounds.py --check    # do the files in the repository match? (a test)

Sets (frontends/soundpack.py says what each event is):

    themes/qip-retro/sounds/  bright "pip-pip" blips and a knock at the door when online
    themes/mra/sounds/        round bubbly "blop"s, a little xylophone
    themes/psi/sounds/        soft sine chimes in major thirds
    themes/point/sounds/      dry wooden ticks, the quietest of the messengers
    sounds/fallback/          what the "desktop" source plays without canberra-gtk-play

Everything is mono, 16-bit, 48 kHz WAV (the sound server's own rate: no clock switch of
the card, USB headsets included): Windows plays WAV by itself, every Linux player
too. Deterministic (noise from a fixed seed), so --check can compare bytes.
"""

from __future__ import annotations

import io
import math
import random
import struct
import sys
import wave
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DATA = ROOT / "fedtail" / "data"
RATE = 48000  # the rate PipeWire runs at: no switch of the device clock to play a chime


# ---- building blocks: each returns a list of floats (-1..1) -----------------------

def silence(sec):
    return [0.0] * int(sec * RATE)


def env(n, attack=0.005, decay=None, release=0.02):
    """An envelope n samples long: a quick rise, then an exponential fall (decay:
    the time to fall by e) or a plateau, and a short release to zero."""
    a = max(1, int(attack * RATE))
    r = max(1, int(release * RATE))
    out = []
    for i in range(n):
        v = min(1.0, i / a)
        if decay:
            v *= math.exp(-max(0, i - a) / (decay * RATE))
        if i > n - r:
            v *= (n - i) / r
        out.append(v)
    return out


def tone(freq, sec, *, to=None, decay=None, harmonics=(1.0,), attack=0.005, vibrato=0.0):
    """A tone gliding from freq to `to` (Hz), made of the given harmonic amplitudes."""
    n = int(sec * RATE)
    e = env(n, attack, decay)
    out, phase = [], 0.0
    for i in range(n):
        f = freq if to is None else freq * (to / freq) ** (i / n)
        if vibrato:
            f *= 1 + vibrato * math.sin(2 * math.pi * 6 * i / RATE)
        phase += 2 * math.pi * f / RATE
        s = sum(a * math.sin(k * phase) for k, a in enumerate(harmonics, 1))
        out.append(s * e[i])
    return out


def bell(freq, sec, *, ratio=1.4, index=2.5, decay=0.25):
    """An FM bell: the overtones fade faster than the note."""
    n = int(sec * RATE)
    e = env(n, 0.002, decay)
    out = []
    for i in range(n):
        t = i / RATE
        mod = index * math.exp(-t / (decay * 0.6)) * math.sin(2 * math.pi * freq * ratio * t)
        out.append(math.sin(2 * math.pi * freq * t + mod) * e[i])
    return out


def knock(sec=0.12, low=170, seed=1):
    """A knock on wood: a low thump and a short burst of filtered noise."""
    rnd = random.Random(seed)
    n = int(sec * RATE)
    thump = tone(low, sec, to=low * 0.8, decay=0.035, attack=0.001)
    out, prev = [], 0.0
    for i in range(n):
        prev = 0.75 * prev + 0.25 * (rnd.random() * 2 - 1)  # a crude low-pass
        out.append(thump[i] * 0.9 + prev * math.exp(-i / (0.012 * RATE)) * 1.6)
    return out


def tick(freq=1400, sec=0.07, seed=2):
    """A dry wooden tick: a very short tone with a click on top."""
    rnd = random.Random(seed)
    body = tone(freq, sec, decay=0.012, attack=0.0005, harmonics=(1.0, 0.0, 0.35))
    return [b + (rnd.random() * 2 - 1) * 0.5 * math.exp(-i / (0.0015 * RATE))
            for i, b in enumerate(body)]


def seq(*parts):
    """Parts one after another: a part is samples, or (offset seconds, samples) to start
    it at that moment (overlapping what is there)."""
    out = []
    pos = 0
    for p in parts:
        if isinstance(p, tuple):
            at, samples = int(p[0] * RATE), p[1]
        else:
            at, samples = pos, p
        end = at + len(samples)
        if end > len(out):
            out += [0.0] * (end - len(out))
        for i, s in enumerate(samples):
            out[at + i] += s
        pos = max(pos, end) if not isinstance(p, tuple) else pos
    return out


def gain(samples, peak):
    top = max((abs(s) for s in samples), default=0) or 1.0
    return [s * peak / top for s in samples]


def wav_bytes(samples):
    buf = io.BytesIO()
    with wave.open(buf, "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(RATE)
        w.writeframes(b"".join(struct.pack("<h", max(-32767, min(32767, round(s * 32767))))
                               for s in samples))
    return buf.getvalue()


# ---- the sets ---------------------------------------------------------------------

SQUARISH = (1.0, 0.0, 0.3, 0.0, 0.12)  # odd harmonics, softened: an old messenger's blip


def qip():
    def blip(f, sec=0.07):
        return tone(f, sec, harmonics=SQUARISH, decay=0.05)
    return {
        "message": seq(blip(880), silence(0.03), blip(1320)),
        "mention": seq(blip(660), silence(0.025), blip(880), silence(0.025), blip(1320)),
        "reply": seq(blip(1320), silence(0.03), blip(990), silence(0.03), blip(1320, 0.1)),
        "direct": seq(bell(1047, 0.35, decay=0.12), (0.16, bell(784, 0.5, decay=0.2))),
        "thread": blip(990, 0.09),
        "request": tone(500, 0.28, to=1500, harmonics=SQUARISH, decay=0.2),
        "activity": tone(1760, 0.05, harmonics=SQUARISH, decay=0.02),
        "online": seq(knock(), silence(0.09), knock(seed=3)),
        "sent": tone(1500, 0.12, to=620, decay=0.08),
    }, 0.6


def agent():
    def blop(f0, f1, sec=0.11):
        return tone(f0, sec, to=f1, decay=0.05, harmonics=(1.0, 0.25))
    def xylo(f, sec=0.25):
        return tone(f, sec, decay=0.06, attack=0.001, harmonics=(1.0, 0.0, 0.0, 0.3))
    return {
        "message": seq(blop(380, 900), silence(0.02), blop(420, 1000)),
        "mention": seq(xylo(1175), (0.09, xylo(1568)), (0.18, xylo(2093, 0.35))),
        "reply": seq(xylo(1568), (0.1, xylo(1175, 0.35))),
        "direct": seq(blop(300, 700, 0.14), silence(0.03), xylo(1568), (0.3, xylo(2093, 0.4))),
        "thread": blop(450, 1000, 0.12),
        "request": seq(xylo(784), (0.1, xylo(988)), (0.2, xylo(1175, 0.35))),
        "activity": blop(600, 1200, 0.07),
        "online": seq(xylo(523), (0.11, xylo(659)), (0.22, xylo(784)), (0.33, xylo(1047, 0.4))),
        "sent": blop(1100, 350, 0.13),
    }, 0.6


def psi():
    def chime(f, sec=0.6):
        return tone(f, sec, decay=0.22, attack=0.004, harmonics=(1.0, 0.18, 0.05))
    return {
        "message": seq(chime(784), (0.12, chime(988, 0.7))),
        "mention": seq(chime(784), (0.1, chime(988)), (0.2, chime(1175, 0.8))),
        "reply": seq(chime(988), (0.13, chime(784, 0.7))),
        "direct": seq(chime(659), (0.12, chime(831)), (0.24, chime(988)), (0.36, chime(1319, 0.9))),
        "thread": chime(880, 0.5),
        "request": seq(chime(587), (0.15, chime(880, 0.7))),
        "activity": chime(1319, 0.3),
        "online": seq(chime(523), (0.14, chime(659)), (0.28, chime(784, 0.8))),
        "sent": chime(1047, 0.25),
    }, 0.5


def point():
    return {
        "message": seq(tick(1300), silence(0.05), tick(1700, seed=3)),
        "mention": seq(tick(1300), silence(0.04), tick(1700, seed=3), silence(0.04),
                       tick(2100, seed=4)),
        "reply": seq(tick(1700, seed=5), silence(0.05), tick(1300, seed=6)),
        "direct": seq(tick(1100, seed=7), silence(0.04), tick(1500, seed=8), silence(0.1),
                      tick(1100, seed=9), silence(0.04), tick(1500, seed=10)),
        "thread": tick(1500, seed=11),
        "request": seq(tick(900, seed=12), silence(0.06), tick(1300, seed=13)),
        "activity": tick(2200, 0.05, seed=14),
        "online": seq(tick(800, seed=15), silence(0.08), tick(1200, seed=16), silence(0.08),
                      tick(1600, seed=17)),
        "sent": tick(1900, 0.05, seed=18),
    }, 0.55


def fallback():
    def soft(f, sec=0.45):
        return tone(f, sec, decay=0.16, attack=0.01, harmonics=(1.0, 0.1))
    return {
        "message": seq(soft(740), (0.1, soft(988, 0.5))),
        "mention": seq(soft(740), (0.09, soft(988)), (0.18, soft(1109, 0.55))),
        "activity": soft(1109, 0.3),
    }, 0.35


SETS = {
    DATA / "themes" / "qip-retro" / "sounds": qip,
    DATA / "themes" / "mra" / "sounds": agent,
    DATA / "themes" / "psi" / "sounds": psi,
    DATA / "themes" / "point" / "sounds": point,
    DATA / "sounds" / "fallback": fallback,
}


def build():
    """{path: bytes} of every file."""
    out = {}
    for folder, make in SETS.items():
        sounds, peak = make()
        for event, samples in sounds.items():
            out[folder / f"{event}.wav"] = wav_bytes(gain(samples, peak))
    return out


def _frames(data):
    with wave.open(io.BytesIO(data)) as w:
        raw = w.readframes(w.getnframes())
    return struct.unpack(f"<{len(raw) // 2}h", raw)


def same(a, b, tolerance=4):
    """The same sound, give or take the last bits (math.sin differs a little between
    C libraries, so the bytes may too)."""
    fa, fb = _frames(a), _frames(b)
    return len(fa) == len(fb) and all(abs(x - y) <= tolerance for x, y in zip(fa, fb, strict=True))


def stale(files=None):
    """The files that are missing or differ from what build() makes."""
    files = files or build()
    return [str(p.relative_to(ROOT)) for p, b in files.items()
            if not p.is_file() or not same(p.read_bytes(), b)]


def main(argv):
    files = build()
    if "--check" in argv:
        bad = stale(files)
        if bad:
            print("stale or missing (run tools/make_sounds.py):\n  " + "\n  ".join(bad))
            return 1
        return 0
    for p, b in files.items():
        p.parent.mkdir(parents=True, exist_ok=True)
        if not p.is_file() or p.read_bytes() != b:
            p.write_bytes(b)
            print("wrote", p.relative_to(ROOT))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
