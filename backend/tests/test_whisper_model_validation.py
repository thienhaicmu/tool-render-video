"""Sprint L-A — WhisperModelPayload validation tests.

1. Valid model name accepted (200).
2. Invalid model name rejected (422).
3. Empty string rejected (422).
"""
from __future__ import annotations

from unittest.mock import patch

from fastapi.testclient import TestClient


def _client():
    from app.main import app
    return TestClient(app)


def test_valid_whisper_model_accepted():
    with patch("app.db.creator_repo.upsert_whisper_model_for_channel"), \
         patch("app.db.creator_repo.get_whisper_model_for_channel", return_value="small"):
        resp = _client().put("/api/settings/whisper/vn", json={"whisper_model": "small"})
    assert resp.status_code == 200


def test_invalid_whisper_model_rejected():
    resp = _client().put("/api/settings/whisper/vn", json={"whisper_model": "gpt-4o-audio"})
    assert resp.status_code == 422


def test_empty_whisper_model_rejected():
    resp = _client().put("/api/settings/whisper/vn", json={"whisper_model": ""})
    assert resp.status_code == 422
