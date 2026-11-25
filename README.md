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
3. `uvicorn main:app --port 8001`
4. Open http://127.0.0.1:8001/docs
5. Monitoring script: `python sentinel.py <session_id> a.wav b.wav`

## Results (small test, not an accuracy claim)
| Clip | Aletheia score (threshold 0.62) | Outcome |
|---|---|---|
| Real recording of a consenting teammate | 0.0115 | Real, VERIFIED |
| Windows text-to-speech clip | 0.9939 | Synthetic, session SUSPENDED |

The Eidos match was tested only with the same recording used for enrollment, so the similarity of 0.999 is not evidence of accuracy. Enrollment used a repeated clip. Wrong-person behaviour: [add if tested].

## Limitations
- Tested on a few clips. The fake was old text-to-speech, not a modern voice clone.
- Monitor mode only detects synthetic voices. It would not catch a different real person taking over the line.
- Sessions are held in memory and lost on restart. The audit log is a local file.
- A score is evidence, not proof. A blocked session should lead to calling back on a trusted number.

## Roadmap (not built)
Random-phrase voice challenge, live audio streaming, a database, an agent interface.

## Ethics
Only voices of consenting team members were used. No real person was cloned.