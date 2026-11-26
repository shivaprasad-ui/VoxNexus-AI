from database import connect
def review(speaker):
    with connect() as c:
        n=c.execute("SELECT COUNT(*) FROM incidents WHERE speaker=? AND created >= datetime('now','-1 day')",(speaker,)).fetchone()[0]
    return {'recent_incidents':n,'human_review_recommended':n>=3}
