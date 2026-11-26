from pathlib import Path
from functools import lru_cache
@lru_cache(maxsize=1)
def model():
    from sklearn.pipeline import make_pipeline
    from sklearn.feature_extraction.text import TfidfVectorizer
    from sklearn.linear_model import LogisticRegression
    import csv
    with Path(__file__).with_name('intent_samples.csv').open() as f: rows=list(csv.DictReader(f))
    return make_pipeline(TfidfVectorizer(ngram_range=(1,2)),LogisticRegression()).fit([r['text'] for r in rows],[r['label'] for r in rows])
def analyze(text):
    m=model(); scores=dict(zip(m.classes_,m.predict_proba([text])[0]))
    return {'label':str(m.predict([text])[0]),'scam_score':float(scores['scam']),'experimental':True}
