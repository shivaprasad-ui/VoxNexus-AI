SENSITIVITY = {"check_balance": 1, "update_profile": 2, "transfer_money": 3}

NEXT_STEP = {
    "ALLOW": "Proceed. Scores are evidence, not proof.",
    "EXTRA_CHECK": "Ask for a second confirmation, such as an OTP or a call back on a number you already know.",
    "BLOCK": "Do not proceed. Contact the person on a trusted number before acting.",
}


def decide(risk_level, action):
    sensitivity = SENSITIVITY.get(action, 3)
    if risk_level == "HIGH":
        decision = "BLOCK"
    elif risk_level == "MEDIUM":
        decision = "EXTRA_CHECK" if sensitivity >= 2 else "ALLOW"
    else:
        decision = "ALLOW"
    return decision, NEXT_STEP[decision]
