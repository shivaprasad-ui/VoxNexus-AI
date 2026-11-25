import os

import requests
from dotenv import load_dotenv

load_dotenv()
KEY = os.getenv("DETECTIF_API_KEY")
BASE = "https://platform.detectif.ai"


class ApiError(Exception):
    def __init__(self, status, text):
        self.status = status
        self.text = text


def _post(path, audio, data=None):
    if not KEY:
        raise ApiError(500, "DETECTIF_API_KEY missing. Check .env")
    response = requests.post(
        BASE + path,
        headers={"Authorization": f"Bearer {KEY}"},
        files={"file": audio},
        data=data,
        timeout=60,
    )
    if response.status_code != 200:
        raise ApiError(response.status_code, response.text)
    return response.json()


def detect(audio):
    return _post("/v1/deepfake/detect", audio)


def enroll(speaker_id, audio):
    # CHECK DOCS: parameter name may not be "speaker_id"
    return _post("/v1/speakers/enroll", audio, {"speaker_id": speaker_id})


def verify(speaker_id, audio):
    # CHECK DOCS: parameter name may not be "speaker_id"
    return _post("/v1/speakers/verify", audio, {"speaker_id": speaker_id})
