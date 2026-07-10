"""Story Mode v2 — V1: /api/jobs/{id}/story-visual/{visual_id} (live monitor
thumbnail) — resolution + path safety (offline)."""
from __future__ import annotations

import uuid
from pathlib import Path

import pytest
from fastapi import HTTPException
from fastapi.responses import FileResponse

import app.routes.jobs as jobs_mod
from app.routes.jobs import api_get_job_story_visual
from app.db.connection import init_db
from app.db.jobs_repo import upsert_job, update_story_plan
from app.domain.story_plan_v2 import StoryPlan, Visual, Beat


def setup_module(module):
    init_db()


def _seed(visual_path: str) -> str:
    jid = 'sv-' + uuid.uuid4().hex[:8]
    upsert_job(jid, 'render', 'vn', 'running', {}, {})
    plan = StoryPlan(language='vi', visuals=[Visual(id='v1', prompt='x')],
                     timeline=[Beat(id='b1', narration='hi', visual_id='v1')])
    plan.render.visual_assets = {'v1': visual_path}
    update_story_plan(jid, plan.to_json())
    return jid


def test_404_missing_job():
    with pytest.raises(HTTPException) as ei:
        api_get_job_story_visual('no-' + uuid.uuid4().hex, 'v1')
    assert ei.value.status_code == 404


def test_404_bad_visual_id():
    jid = _seed('/tmp/x.png')
    for bad in ('../etc/passwd', 'v1/../..', 'a b', ''):
        with pytest.raises(HTTPException) as ei:
            api_get_job_story_visual(jid, bad)
        assert ei.value.status_code == 404


def test_404_visual_not_in_plan():
    jid = _seed('/tmp/x.png')
    with pytest.raises(HTTPException) as ei:
        api_get_job_story_visual(jid, 'v2')  # only v1 in assets
    assert ei.value.status_code == 404


def test_200_serves_file_under_root(tmp_path, monkeypatch):
    monkeypatch.setattr(jobs_mod, 'TEMP_DIR', tmp_path)
    monkeypatch.setattr(jobs_mod, 'CACHE_DIR', tmp_path / 'cache')
    img = tmp_path / 'img_v1.png'
    img.write_bytes(b'\x89PNG_real')
    jid = _seed(str(img))
    resp = api_get_job_story_visual(jid, 'v1')
    assert isinstance(resp, FileResponse)
    assert Path(resp.path).resolve() == img.resolve()
    assert resp.media_type == 'image/png'


def test_404_when_file_missing(tmp_path, monkeypatch):
    monkeypatch.setattr(jobs_mod, 'TEMP_DIR', tmp_path)
    monkeypatch.setattr(jobs_mod, 'CACHE_DIR', tmp_path / 'cache')
    jid = _seed(str(tmp_path / 'gone.png'))  # under root but not written
    with pytest.raises(HTTPException) as ei:
        api_get_job_story_visual(jid, 'v1')
    assert ei.value.status_code == 404


def test_403_outside_allowed_roots(tmp_path, monkeypatch):
    allowed = tmp_path / 'allowed'
    allowed.mkdir()
    monkeypatch.setattr(jobs_mod, 'TEMP_DIR', allowed)
    monkeypatch.setattr(jobs_mod, 'CACHE_DIR', allowed / 'cache')
    outside = tmp_path / 'outside.png'
    outside.write_bytes(b'\x89PNG_evil')
    jid = _seed(str(outside))
    with pytest.raises(HTTPException) as ei:
        api_get_job_story_visual(jid, 'v1')
    assert ei.value.status_code == 403
