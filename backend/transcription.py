import tempfile,os
from functools import lru_cache
@lru_cache(maxsize=1)
def model():
    from faster_whisper import WhisperModel
    return WhisperModel('tiny.en',device='cpu',compute_type='int8')
def transcribe(data):
    with tempfile.NamedTemporaryFile(suffix='.wav',delete=False) as f:
        f.write(data); path=f.name
    try:
        segments,_=model().transcribe(path,language='en')
        return ' '.join(s.text for s in segments).strip()
    finally: os.unlink(path)
