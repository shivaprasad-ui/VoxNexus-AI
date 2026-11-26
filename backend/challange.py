import re, time, secrets, difflib

TTL = 90
MATCH_NEEDED = 0.8

ADJ = ["blue", "green", "silver", "golden", "quiet", "brave", "red", "small"]
NOUN = ["train", "river", "garden", "window", "bridge", "market", "mountain", "lantern"]
VERB = ["arrives", "crosses", "waits", "opens", "moves", "stops"]
NUM = ["two", "three", "four", "five", "six", "seven", "eight", "nine"]
DIGITS = {"0": "zero", "1": "one", "2": "two", "3": "three", "4": "four",
          "5": "five", "6": "six", "7": "seven", "8": "eight", "9": "nine"}

CHALLENGES = {}   # txn_id -> challenge dict


def _words(text):
    text = text.lower()
    out = []
    for w in re.findall(r"[a-z0-9]+", text):
        out.append(DIGITS.get(w, w))
    return out


def matches(spoken, phrase):
    target = _words(phrase)
    heard = _words(spoken)
    if not target or not heard:
        return False, 0.0
    sm = difflib.SequenceMatcher(None, target, heard)
    hit = sum(b.size for b in sm.get_matching_blocks())
    score = hit / len(target)
    return score >= MATCH_NEEDED, score


def make_phrase():
    c = secrets.choice
    return "The %s %s %s at %s near gate %s." % (
        c(ADJ), c(NOUN), c(VERB), c(NUM), c(NUM))


def issue(sid, txn_id):
    ch = {"id": "C-" + secrets.token_hex(3), "sid": sid, "txn": txn_id,
          "phrase": make_phrase(), "issued": time.time(),
          "passed": False, "tries": 0}
    CHALLENGES[txn_id] = ch
    return {"challenge_id": ch["id"], "phrase": ch["phrase"], "expires_in": TTL}


def record_result(sid, challenge_id, spoken, voice_ok):
    ch = next((c for c in CHALLENGES.values() if c["id"] == challenge_id), None)
    if ch is None or ch["sid"] != sid:
        return {"passed": False, "reason": "Unknown challenge."}
    if time.time() - ch["issued"] > TTL:
        return {"passed": False, "reason": "Challenge expired. Ask for a new one."}
    if ch["passed"]:
        return {"passed": True, "reason": "Already passed."}
    ch["tries"] += 1
    ok, score = matches(spoken, ch["phrase"])
    passed = bool(ok and voice_ok)
    ch["passed"] = passed
    if passed:
        reason = "Phrase matched and voice check passed."
    elif not ok:
        reason = "Spoken words did not match the phrase (%d%%)." % int(score * 100)
    else:
        reason = "Phrase matched but the voice check did not pass."
    return {"passed": passed, "phrase_match": round(score, 2), "reason": reason}


def is_passed(txn_id, sid):
    ch = CHALLENGES.get(txn_id)
    return bool(ch and ch["sid"] == sid and ch["passed"])