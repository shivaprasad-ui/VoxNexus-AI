import firewall
def evaluate(s,action):
    decision,reason=firewall.enforce(s['session_id'],s,action)
    return {'decision':decision,'reason':reason,'executed':False}
