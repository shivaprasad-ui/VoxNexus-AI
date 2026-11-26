import audit
def generate(s):
    return {'session_id':s['session_id'],'status':s['status'],'trust':s['trust_score'],'events':s['events'],'audit':audit.read(s['session_id'],limit=200),'note':'Model scores are evidence, not proof.'}
