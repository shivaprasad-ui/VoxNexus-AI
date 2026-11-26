from callguard import analyze

SCAM = [
    "This is your bank manager. Send me the OTP right now.",
    "I am calling from the RBI. Your account will be blocked, share your PIN.",
    "Don't tell anyone, just approve the payment immediately.",
    "Police cyber cell here. Transfer the money urgently or face arrest.",
    "Your KYC is pending, tell me the CVV to avoid suspension.",
]
SCAM.append("I need to transfer money to the account, I need to do it fast. I need to do it now.")
NORMAL = [
    "Hi, I'd like to check my account balance please.",
    "Can you help me update my address?",
    "I want to know my last five transactions.",
    "What are your branch timings tomorrow?",
    "My OTP hasn't arrived yet, can you resend it?",
    "I'd like to transfer money to my sister.",
]
NORMAL.append("I have a quick question about my balance.")

def flagged(t):
    return analyze(t)["level"] in ("MEDIUM", "HIGH", "CRITICAL")

caught = sum(flagged(t) for t in SCAM)
false_alarms = sum(flagged(t) for t in NORMAL)
for t in SCAM + NORMAL:
    r = analyze(t)
    print(r["level"].ljust(8), r["heard"], "|", t)
print(f"\nScam lines flagged: {caught}/{len(SCAM)}")
print(f"Normal lines wrongly flagged: {false_alarms}/{len(NORMAL)}")

import callguard
s = {"status": "VERIFIED", "trust_score": 100, "events": []}
for t in ["Hi, I want to check my balance.",
          "I need to transfer money to the account, do it fast.",
          "This is your bank manager, send me the OTP right now."]:
    r = analyze(t)
    print(callguard.apply_penalty("T1", s, r["heard"]), r["level"])

otp_session = {"status": "VERIFIED", "trust_score": 100, "events": []}
otp_result = callguard.apply_penalty("T2", otp_session, analyze("Please share your OTP.")["heard"])
assert otp_result["trust"] == 85, "An OTP-only signal must reduce trust from 100 to 85."
import trust_engine
otp_session["last_identity_check"] = None
assert trust_engine.authorize(otp_session, "transfer_money")[0] == "STEP_UP"
print("OTP-only penalty:", otp_result)