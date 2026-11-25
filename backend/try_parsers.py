from parsers import parse_aletheia, parse_eidos
from risk_engine import assess

a = parse_aletheia({"result": {"label": "genuine", "is_synthetic": False, "score": 0.0088, "threshold": 0.62}})
e = parse_eidos({"result": {"decision": "match", "similarity": 0.999, "threshold": 0.53}})
print(a["fake"], e["match"], assess(a["fake"], e["match"]))