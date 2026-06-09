"""Tests for Optional[bool] semantics on 4 AI-controlled RenderPlan fields.

P2 — RenderPlan Boolean Ambiguity Fix.

Validates three-state semantics: absent key → None, explicit false → False,
explicit true → True. None means "AI didn't mention it — inherit legacy
default." True/False means "AI explicitly set this."
"""
import json

import pytest

from app.domain.render_plan import RenderPlan


# ── emphasis_pass ─────────────────────────────────────────────────────────────

def test_emphasis_pass_absent_gives_none():
    plan = RenderPlan.from_json('{"clips": []}')
    assert plan.subtitle_policy.emphasis_pass is None


def test_emphasis_pass_explicit_false():
    plan = RenderPlan.from_json('{"subtitle_policy": {"emphasis_pass": false}}')
    assert plan.subtitle_policy.emphasis_pass is False


def test_emphasis_pass_explicit_true():
    plan = RenderPlan.from_json('{"subtitle_policy": {"emphasis_pass": true}}')
    assert plan.subtitle_policy.emphasis_pass is True


def test_emphasis_pass_json_null_gives_none():
    plan = RenderPlan.from_json('{"subtitle_policy": {"emphasis_pass": null}}')
    assert plan.subtitle_policy.emphasis_pass is None


# ── motion_aware_crop ─────────────────────────────────────────────────────────

def test_motion_aware_crop_absent_gives_none():
    plan = RenderPlan.from_json('{"clips": []}')
    assert plan.camera_strategy.motion_aware_crop is None


def test_motion_aware_crop_explicit_true():
    plan = RenderPlan.from_json('{"camera_strategy": {"motion_aware_crop": true}}')
    assert plan.camera_strategy.motion_aware_crop is True


def test_motion_aware_crop_explicit_false():
    plan = RenderPlan.from_json('{"camera_strategy": {"motion_aware_crop": false}}')
    assert plan.camera_strategy.motion_aware_crop is False


# ── voice_enabled ─────────────────────────────────────────────────────────────

def test_voice_enabled_absent_gives_none():
    plan = RenderPlan.from_json('{"clips": []}')
    assert plan.audio_plan.voice_enabled is None


def test_voice_enabled_explicit_true():
    plan = RenderPlan.from_json('{"audio_plan": {"voice_enabled": true}}')
    assert plan.audio_plan.voice_enabled is True


def test_voice_enabled_explicit_false():
    plan = RenderPlan.from_json('{"audio_plan": {"voice_enabled": false}}')
    assert plan.audio_plan.voice_enabled is False


# ── bgm_enabled ───────────────────────────────────────────────────────────────

def test_bgm_enabled_absent_gives_none():
    plan = RenderPlan.from_json('{"clips": []}')
    assert plan.audio_plan.bgm_enabled is None


def test_bgm_enabled_explicit_true():
    plan = RenderPlan.from_json('{"audio_plan": {"bgm_enabled": true}}')
    assert plan.audio_plan.bgm_enabled is True


def test_bgm_enabled_explicit_false():
    plan = RenderPlan.from_json('{"audio_plan": {"bgm_enabled": false}}')
    assert plan.audio_plan.bgm_enabled is False


# ── string coercion (robustness) ──────────────────────────────────────────────

def test_emphasis_pass_string_true_coerced():
    plan = RenderPlan.from_json('{"subtitle_policy": {"emphasis_pass": "true"}}')
    assert plan.subtitle_policy.emphasis_pass is True


def test_emphasis_pass_string_false_coerced():
    plan = RenderPlan.from_json('{"subtitle_policy": {"emphasis_pass": "false"}}')
    assert plan.subtitle_policy.emphasis_pass is False


def test_emphasis_pass_unknown_string_gives_none():
    plan = RenderPlan.from_json('{"subtitle_policy": {"emphasis_pass": "maybe"}}')
    assert plan.subtitle_policy.emphasis_pass is None


# ── roundtrip ─────────────────────────────────────────────────────────────────

def test_roundtrip_none_fields():
    plan = RenderPlan.from_json('{"clips": []}')
    reloaded = RenderPlan.from_json(plan.to_json())
    assert reloaded.subtitle_policy.emphasis_pass is None
    assert reloaded.camera_strategy.motion_aware_crop is None
    assert reloaded.audio_plan.voice_enabled is None
    assert reloaded.audio_plan.bgm_enabled is None


def test_roundtrip_false_fields():
    raw = json.dumps({
        "subtitle_policy": {"emphasis_pass": False},
        "camera_strategy": {"motion_aware_crop": False},
        "audio_plan": {"voice_enabled": False, "bgm_enabled": False},
    })
    plan = RenderPlan.from_json(raw)
    reloaded = RenderPlan.from_json(plan.to_json())
    assert reloaded.subtitle_policy.emphasis_pass is False
    assert reloaded.camera_strategy.motion_aware_crop is False
    assert reloaded.audio_plan.voice_enabled is False
    assert reloaded.audio_plan.bgm_enabled is False
