def parse_aletheia(raw):
    r = raw.get("result", {})
    fake = r.get("is_synthetic")
    if not isinstance(fake, bool):
        fake = None
    return {
        "fake": fake,
        "label": r.get("label"),
        "score": r.get("score"),
        "threshold": r.get("threshold"),   # 0.62
        "segments": r.get("segments", []),
        "raw": raw,
    }


def parse_eidos(raw):
    r = raw.get("result", {})
    d = str(r.get("decision", "")).lower()
    if d == "match":
        match = True
    elif d in ("no_match", "mismatch", "not_match", "reject", "rejected"):
        match = False
    else:
        match = None   # unseen value, so check it on the wrong-person test
    return {
        "match": match,
        "similarity": r.get("similarity"),
        "threshold": r.get("threshold"),   # 0.53
        "raw": raw,
    }