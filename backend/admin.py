"""Admin API. Every route needs an admin login."""
import os
import time
from typing import Optional

from fastapi import APIRouter, Depends, Form, HTTPException
from fastapi.responses import FileResponse

import audit
import detectif
import schema
import session_manager
from auth import require_admin
from common import api_call, db
from customer import PENDING_DIR

router = APIRouter(prefix="/api/admin")
STATUSES = ("PENDING", "APPROVED", "REJECTED")


def _path(eid):
    return os.path.join(PENDING_DIR, "%d.wav" % int(eid))


@router.get("/enrollments")
def list_enrollments(status: str = "PENDING", a: dict = Depends(require_admin)):
    if status not in STATUSES:
        raise HTTPException(400, "Unknown status.")
    with db() as c:
        rows = c.execute(
            "SELECT e.id, e.customer_id, u.full_name, e.speaker_id, e.status, e.created_at "
            "FROM voice_enrollments e JOIN users u ON u.id = e.customer_id "
            "WHERE e.status = ? ORDER BY e.id DESC LIMIT 100", (status,)).fetchall()
    return [dict(r) for r in rows]


@router.get("/enrollments/{eid}/audio")
def enrollment_audio(eid: int, a: dict = Depends(require_admin)):
    p = _path(eid)
    if not os.path.exists(p):
        raise HTTPException(404, "Recording no longer available.")
    return FileResponse(p, media_type="audio/wav", headers={"Cache-Control": "no-store"})


@router.post("/enrollments/{eid}/decide")
def decide_enrollment(eid: int, decision: str = Form(...), reason: str = Form(""),
                      a: dict = Depends(require_admin)):
    if decision not in ("APPROVED", "REJECTED"):
        raise HTTPException(400, "Decision must be APPROVED or REJECTED.")
    reason = reason.strip()[:300]
    if decision == "REJECTED" and not reason:
        raise HTTPException(400, "A reason is required to reject.")
    with db() as c:
        row = c.execute("SELECT * FROM voice_enrollments WHERE id = ?", (eid,)).fetchone()
    if row is None:
        raise HTTPException(404, "Unknown enrollment.")
    if row["status"] != "PENDING":
        raise HTTPException(409, "Already decided.")
    p = _path(eid)
    if decision == "APPROVED":
        if not os.path.exists(p):
            raise HTTPException(410, "Recording is missing. Ask the customer to enroll again.")
        with open(p, "rb") as f:
            data = f.read()
        api_call(detectif.enroll, row["speaker_id"], (row["speaker_id"] + ".wav", data, "audio/wav"))
    with db() as c:
        cur = c.execute(
            "UPDATE voice_enrollments SET status = ?, reviewed_by = ?, reviewed_at = ? "
            "WHERE id = ? AND status = 'PENDING'", (decision, a["id"], time.time(), eid))
        if cur.rowcount != 1:
            raise HTTPException(409, "Already decided.")
        if decision == "APPROVED":
            c.execute("UPDATE users SET speaker_id = ? WHERE id = ? AND speaker_id IS NULL",
                      (row["speaker_id"], row["customer_id"]))
    try:
        os.remove(p)
    except OSError:
        pass
    schema.log_event("ENROLL_" + decision, row["customer_id"], severity="info",
                     detail="by %s: %s" % (a["id"], reason or "voice sample reviewed"))
    return {"id": eid, "status": decision}


@router.get("/audit")
def audit_view(sid: Optional[str] = None, a: dict = Depends(require_admin)):
    return audit.read(sid)


@router.get("/incident/{sid}")
def incident(sid: str, a: dict = Depends(require_admin)):
    import incident_report
    try:
        s = session_manager.get(sid)
    except KeyError:
        raise HTTPException(404, "Unknown session (sessions are lost when the server restarts).")
    return incident_report.generate(s)


@router.get("/fraud/{speaker_id}")
def fraud(speaker_id: str, a: dict = Depends(require_admin)):
    import fraud_intelligence
    return fraud_intelligence.review(speaker_id)
