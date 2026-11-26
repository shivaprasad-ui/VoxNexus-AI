import csv
from pathlib import Path
import intent_engine
from callguard import analyze

TEST = [
    ("Your electricity will be cut tonight unless you pay this bill to my number", "scam"),
    ("Please keep it to yourself and move the funds to the account I give you", "scam"),
    ("I am an officer and I need your secret code to cancel the fraud", "scam"),
    ("Click this link and enter your bank login to get your refund", "scam"),
    ("Your son has been arrested and needs bail money now", "scam"),
    ("Let me connect to your computer to fix the problem", "scam"),
    ("Pay the processing fee first and the loan will be released", "scam"),
    ("Do not speak to anyone at the branch about this", "scam"),
    ("Give me the six digit number sent by SMS", "scam"),
    ("Your account is under investigation so move your savings to a safe account", "scam"),
    ("How do I find the nearest ATM", "normal"),
    ("Can you explain the charges on my account", "normal"),
    ("I want to close my fixed deposit", "normal"),
    ("Why was I charged a fee last month", "normal"),
    ("Please send me the form to add a joint holder", "normal"),
    ("Someone asked for my PIN and I refused so I want to report it", "normal"),
    ("I would like to pay my credit card bill online", "normal"),
    ("Can you help me understand this statement", "normal"),
    ("What is the minimum balance for a savings account", "normal"),
    ("I want to send money to my brother in Mumbai", "normal"),
]

train = list(csv.DictReader(Path("intent_samples.csv").open()))
print("training rows:", len(train),
      "| scam:", sum(r["label"] == "scam" for r in train),
      "| normal:", sum(r["label"] == "normal" for r in train))
overlap = {t for t, _ in TEST} & {r["text"] for r in train}
assert not overlap, "test sentence found in training data: %s" % overlap

def score(name, predict):
    tp = fn = fp = tn = 0
    for text, truth in TEST:
        p = predict(text)
        if truth == "scam":
            tp += p; fn += (not p)
        else:
            fp += p; tn += (not p)
    print("%-22s scams caught %d/10 | normal wrongly flagged %d/10" % (name, tp, fp))

score("ML (TF-IDF)", lambda t: intent_engine.analyze(t)["scam_score"] >= 0.5)
score("Rules (callguard)", lambda t: analyze(t)["pressure_score"] >= 20)
score("Either one", lambda t: intent_engine.analyze(t)["scam_score"] >= 0.5
                              or analyze(t)["pressure_score"] >= 20)

print()
for text, truth in TEST:
    print(truth.ljust(7), "ML %.2f" % intent_engine.analyze(text)["scam_score"],
          "| rules", analyze(text)["pressure_score"], "|", text)