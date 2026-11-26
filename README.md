# VoxNexus AI
A trust layer for voice. It checks whether a voice is real (DetectifAI Aletheia) and whether it is the registered person (Eidos), then decides whether a sensitive action is allowed.

Track 3: The Trust Layer. Ananth AI Hackathon 2K26.

## Why
A cloned voice can match the right person and still be fake. Identity alone is not enough, so both checks are used.

## How it works
- A session starts UNVERIFIED with trust 0. Nothing sensitive is allowed.
- A full check (Aletheia, then Eidos) on a real, matching voice gives trust 100 and unlocks actions.
- Monitor mode (Aletheia only) can only lower trust. A synthetic voice suspends the session at once.
- A firewall combines role permissions and trust and logs every decision to an audit log.
- Cost cascade: Aletheia runs first, and Eidos is skipped if the voice is fake.

## Run
1. `cd backend`, create a venv, `pip install -r requirements.txt`
2. Create `backend/.env` with `DETECTIF_API_KEY=your_key`
3. Run `python seed_users.py`; it prompts for passwords for the local demo accounts. Do not reuse real banking passwords.
4. If `cust1` and `cust2` already have consented voice profiles enrolled in DetectifAI, run `python mark_enrolled.py cust1 cust2`. Otherwise sign in and submit an enrollment for admin review.
5. Run the no-credits checks: `python test_auth.py` and `python test_portal.py`
6. Start the server with `uvicorn main:app --port 8001`, then open http://127.0.0.1:8001/login

The customer and admin portal pages are available after login. API documentation is at http://127.0.0.1:8001/docs.

## Results (small test, not an accuracy claim)
| Clip | Aletheia score (threshold 0.62) | Outcome |
|---|---|---|
| Real recording of a consenting teammate | 0.0115 | Real, VERIFIED |
| Windows text-to-speech clip | 0.9939 | Synthetic, session SUSPENDED |

The Eidos match was tested only with the same recording used for enrollment, so the similarity of 0.999 is not evidence of accuracy. Enrollment used a repeated clip. Wrong-person behaviour: [add if tested].

## Limitations
- Tested on a few clips. The fake was old text-to-speech, not a modern voice clone.
- The 4th live-call check re-verifies identity, but it has not been tested with a real different speaker taking over the call.
- Active sessions remain in memory and cannot resume after a server restart, although session and security-event records are mirrored to SQLite.
- Large transfers are blocked pending a separate admin-approval page; the current portal does not provide authenticated transaction approval.
- Call transcripts and challenge speech recognition still come from the browser. The ML Call Guard score is experimental.
- A score is evidence, not proof. A blocked session should lead to calling back on a trusted number.

## Next steps
Authenticated transaction approval with an atomic balance ledger, server-side transcription, service-failure handling, and rate limiting.

## Ethics
Only voices of consenting team members were used. No real person was cloned.