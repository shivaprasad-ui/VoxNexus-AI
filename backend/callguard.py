import re

# ---------- scam-wording rules ----------
RULES = [
    ("urgency", 20, r"\b(urgent|urgently|immediately|right now|right away|at once|asap|hurry|within (10|ten|5|five) minutes|last chance|today only|before it'?s too late)\b|\b(do|need|send|transfer|make|finish|complete) (it|this|that|the (payment|transfer))( \w+)? (now|fast|quickly)\b"),
    ("fake authority", 25, r"\b(bank (officer|manager|executive|representative|official|staff)|rbi|reserve bank|police|cyber cell|income tax|customs|kyc|account (will be|is|has been) (blocked|frozen|suspended)|arrest)\b"),
    ("secrecy", 25, r"(don'?t tell|do not tell|keep this (a )?(secret|between us)|don'?t hang up|do not hang up)"),
    ("asks for OTP or PIN", 40, r"\b(send|share|tell|give|read|provide|confirm|what('?s| is))\b[^.?!]{0,30}\b(o ?t ?p|one time password|pin|cvv|password)\b"),
    ("asks for money", 25, r"\b(send|give|pay) me\b[^.?!]{0,20}\b(money|cash|amount|payment|rupees)\b|\bgift cards?\b|\bapprove (the )?(payment|transfer|request)\b"),
    ("rushed money move", 25, r"\b(transfer|send|pay)\b[^.?!]{0,40}\b(now|fast|quickly|immediately|urgent|urgently|asap)\b"),
    ("remote access", 25, r"\b(any ?desk|team ?viewer|quick ?support|screen ?shar(e|ing)|remote access|install (this|the|an?) app)\b"),
    ("threat", 25, r"\b(legal action|case (will be|is|has been) (filed|registered)|court notice|penalty|your (card|sim|number|account) (will be|is|has been) (blocked|closed|deactivated|disconnected))\b"),
    ("asks for personal data", 30, r"\b(send|share|tell|give|read|provide|confirm|what('?s| is))\b[^.?!]{0,30}\b(aadhaar|aadhar|pan (card|number)|card number|expiry|date of birth|mother'?s maiden)\b"),
    ("prize or refund bait", 20, r"\b(lottery|you (have )?won|prize|cashback|reward points)\b"),
    ("untraceable payment", 25, r"\b(crypto|bitcoin|wire transfer|safe account|new beneficiary)\b"),
    ("blocks verification", 25, r"\b(don'?t|do not) (call|check|verify|visit|go to)\b[^.?!]{0,25}\b(back|bank|branch|family|anyone)\b|\bno time to (verify|check)\b"),
    ("emotional emergency", 20, r"\b(emergency|accident|hospital|kidnapped|in trouble)\b[^.?!]{0,40}\b(money|send|transfer|pay|help)\b"),
]


def repeat_units(text):
    """One unit per 5 repeated words (longest run, or one word making up half the speech)."""
    words = re.findall(r"[a-z']+", text.lower())
    if len(words) < 6:
        return 0
    run = best = 1
    for a, b in zip(words, words[1:]):
        run = run + 1 if a == b else 1
        best = max(best, run)
    top = max(words.count(w) for w in set(words))
    count = max(best, top if len(words) >= 10 and top / len(words) >= 0.5 else 0)
    return count // 5


def analyze(text, voice_score=None):
    hits = [(c, w) for c, w, p in RULES if re.search(p, text, re.I)]
    units = repeat_units(text)
    if units >= 1:
        hits.append(("repetitive speech", 20))
    score = min(100, sum(w for _, w in hits))
    synthetic = voice_score is not None and voice_score >= 0.62

    if synthetic and score >= 40:
        level, msg = "CRITICAL", "Synthetic voice and pressure tactics. Hang up."
    elif synthetic:
        level, msg = "HIGH", "Synthetic voice detected. Do not act on this call."
    elif score >= 40:
        level, msg = "MEDIUM", "Pressure tactics heard. Hang up and call back on the number from your card or app."
    elif score >= 20:
        level, msg = "LOW", "Some pressure words. Stay alert."
    else:
        level, msg = "CLEAR", "No scam signals found in this text."

    return {"pressure_score": score, "heard": [c for c, _ in hits],
            "level": level, "message": msg, "voice_score": voice_score,
            "repeat_units": units}


# ---------- trust penalty ----------
PENALTY = 5              # trust lost per new pressure category
PENALTY_BY = {"asks for OTP or PIN": 15}          # per-category override, e.g. {"asks for OTP or PIN": 15}
REPEAT_STEP = 5          # trust lost per 5 repeated words
REPEAT_MAX_UNITS = 6     # repetition alone costs at most 30
SEEN = {}                # session id -> categories already charged
APPLIED_REPEAT = {}      # session id -> repeat units already charged


def _get(s, k):
    return s[k] if isinstance(s, dict) else getattr(s, k)


def _set(s, k, v):
    if isinstance(s, dict):
        s[k] = v
    else:
        setattr(s, k, v)


def apply_penalty(sid, session, heard, units=0):
    status = str(_get(session, "status")).split(".")[-1]
    trust = _get(session, "trust_score")
    if status != "VERIFIED" or trust <= 0:
        return {"penalty": 0, "new_signals": [], "trust": trust}

    seen = SEEN.setdefault(sid, set())
    new = [c for c in heard if c != "repetitive speech" and c not in seen]
    seen.update(new)
    lost = sum(PENALTY_BY.get(c, PENALTY) for c in new)
    labels = list(new)

    units = min(units, REPEAT_MAX_UNITS)
    done = APPLIED_REPEAT.get(sid, 0)
    if units > done:
        lost += REPEAT_STEP * (units - done)
        APPLIED_REPEAT[sid] = units
        labels.append("repetition x" + str(units * 5))

    lost = min(trust, lost)
    if lost <= 0:
        return {"penalty": 0, "new_signals": [], "trust": trust}
    _set(session, "trust_score", trust - lost)
    _set(session, "pressure_cap", trust - lost)
    from session_manager import log
    log(session, "CALL_GUARD", "Pressure heard: " + ", ".join(labels) + f" (-{lost} trust)")
    return {"penalty": lost, "new_signals": labels, "trust": trust - lost}


# ---------- "call was checked" flag (transfer needs it) ----------
CHECKED = set()


def mark_checked(sid, text):
    if sid and len(text.split()) >= 3:
        CHECKED.add(sid)


def is_checked(sid):
    return sid in CHECKED
