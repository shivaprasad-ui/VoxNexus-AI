"""Shared helpers: database context manager, WAV length check, DetectifAI error wrapper."""
import io
import json
import wave
from contextlib import contextmanager

import requests
from fastapi import HTTPException

import detectif
import schema

MAX_UPLOAD_BYTES = 12 * 1024 * 1024


@contextmanager
def db():
    c = schema.connect()
    try:
        yield c
    finally:
        c.close()


def check_wav_length(data: bytes, min_seconds: float = 4):
    """Validate size and length locally so bad clips never cost credits."""
    if len(data) > MAX_UPLOAD_BYTES:
        raise HTTPException(400, "File is too large.")
    try:
        with wave.open(io.BytesIO(data)) as w:
            seconds = w.getnframes() / w.getframerate()
    except Exception:
        raise HTTPException(400, "Please upload a .wav file.")
    if seconds < min_seconds or seconds > 120:
        raise HTTPException(
            400, f"Clip is {seconds:.1f}s. Please upload a clip between {min_seconds:.0f} and 120 seconds.")


def api_call(fn, *args):
    try:
        return fn(*args)
    except detectif.ApiError as error:
        try:
            response = json.loads(error.text)
            api_error = response.get("error")
            message = api_error.get("message") if isinstance(api_error, dict) else None
        except (json.JSONDecodeError, AttributeError, TypeError):
            message = None
        raise HTTPException(error.status, message if isinstance(message, str) else error.text)
    except requests.RequestException as error:
        raise HTTPException(502, f"Could not reach DetectifAI: {error}")