"""Tests for app.features.render.engine.motion (MotionCropConfig + render_motion_aware_crop)."""
import dataclasses
from unittest.mock import MagicMock, patch

import pytest

from app.features.render.engine.motion import MotionCropConfig, render_motion_aware_crop
from app.features.render.engine.motion.config import _apply_content_type_to_cfg


# ---------------------------------------------------------------------------
# MotionCropConfig defaults
# ---------------------------------------------------------------------------

def test_motion_crop_config_default_instantiation():
    cfg = MotionCropConfig()
    assert isinstance(cfg, MotionCropConfig)


def test_motion_crop_config_has_scale_x_percent():
    cfg = MotionCropConfig()
    assert hasattr(cfg, "scale_x_percent")
    assert isinstance(cfg.scale_x_percent, float)


def test_motion_crop_config_has_scale_y_percent():
    cfg = MotionCropConfig()
    assert hasattr(cfg, "scale_y_percent")
    assert isinstance(cfg.scale_y_percent, float)


def test_motion_crop_config_default_output_dimensions():
    cfg = MotionCropConfig()
    assert cfg.output_width == 1080
    assert cfg.output_height == 1440


def test_motion_crop_config_default_reframe_mode():
    cfg = MotionCropConfig()
    assert cfg.reframe_mode == "subject"


def test_motion_crop_config_default_scale_y_percent():
    cfg = MotionCropConfig()
    assert cfg.scale_y_percent == pytest.approx(106.0)


def test_motion_crop_config_is_dataclass():
    assert dataclasses.is_dataclass(MotionCropConfig)


def test_motion_crop_config_custom_values():
    cfg = MotionCropConfig(output_width=720, output_height=1280)
    assert cfg.output_width == 720
    assert cfg.output_height == 1280


# ---------------------------------------------------------------------------
# _apply_content_type_to_cfg
# ---------------------------------------------------------------------------

def test_apply_content_type_interview_reduces_detect_interval():
    cfg = MotionCropConfig(subject_detect_interval=16)
    updated = _apply_content_type_to_cfg(cfg, "interview")
    assert updated.subject_detect_interval < cfg.subject_detect_interval


def test_apply_content_type_montage_increases_pan_speed():
    cfg = MotionCropConfig(max_pan_speed_ratio=0.010)
    updated = _apply_content_type_to_cfg(cfg, "montage")
    assert updated.max_pan_speed_ratio > cfg.max_pan_speed_ratio


def test_apply_content_type_unknown_falls_back_to_vlog():
    cfg = MotionCropConfig()
    vlog_cfg = _apply_content_type_to_cfg(cfg, "vlog")
    unknown_cfg = _apply_content_type_to_cfg(cfg, "unknown_type_xyz")
    assert vlog_cfg.subject_detect_interval == unknown_cfg.subject_detect_interval


def test_apply_content_type_returns_new_instance():
    cfg = MotionCropConfig()
    updated = _apply_content_type_to_cfg(cfg, "interview")
    assert updated is not cfg


# ---------------------------------------------------------------------------
# render_motion_aware_crop — callable check (real execution mocked)
# ---------------------------------------------------------------------------

def test_render_motion_aware_crop_is_callable():
    assert callable(render_motion_aware_crop)


def test_render_motion_aware_crop_raises_without_real_video():
    """Without a real video file, the function should raise (not silently succeed)."""
    with pytest.raises(Exception):
        render_motion_aware_crop(
            input_path="/nonexistent/fake_video.mp4",
            output_path="/tmp/out.mp4",
        )
