import audit
import permissions
import trust_engine


def enforce(sid, s, action):
    role = s.get("role", "customer")
    if not permissions.allowed(role, action):
        decision, reason = "BLOCK", f"Role '{role}' is not allowed to {action}."
    else:
        decision, reason = trust_engine.authorize(s, action)
    audit.log(sid, "firewall", action=action, role=role, decision=decision,
              reason=reason, trust=trust_engine.effective_score(s))
    return decision, reason