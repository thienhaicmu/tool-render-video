"""Pin hành vi cổng RENDER_FUSE_CUT.

Mặc định BẬT — được bật sau khi smoke-check 2026-07 vá 3 lỗi đường fuse
(guard phụ đề nhận full SRT làm nguồn; forward reframe_mode qua cfg;
re-export helper tracker trong motion/__init__) và chạy lại A/B sạch.

Bốn cổng an toàn của ``_fuse_safe_active`` phải luôn ép đường legacy
(cut_video + render_part_smart) bất kể mặc định BẬT:
  1. force_accurate_cut — cần semantics re-encode của cut_video.
  2. resume_from_last — resume đọc raw_part trên đĩa để quyết định re-cut.
  3. thiếu full_srt — fallback Whisper per-part cần raw_part làm input.
  4. RenderPlan chỉ định tracker — đường fuse không mang crop_cfg_override.

Kill switch ``RENDER_FUSE_CUT=0`` phải tắt fuse tức thời (rollback không
cần sửa code).
"""
from types import SimpleNamespace

from app.features.render.engine.stages.part_cut import _fuse_safe_active


def _ctx(resume: bool = False, full_srt: bool = True, tracker: str = ""):
    plan = None
    if tracker:
        plan = SimpleNamespace(camera_strategy=SimpleNamespace(tracker=tracker))
    return SimpleNamespace(
        payload=SimpleNamespace(resume_from_last=resume),
        full_srt_available=full_srt,
        render_plan=plan,
    )


def test_fuse_default_on(monkeypatch):
    monkeypatch.delenv("RENDER_FUSE_CUT", raising=False)
    assert _fuse_safe_active(_ctx(), force_accurate_cut=False) is True


def test_fuse_kill_switch_env_zero(monkeypatch):
    monkeypatch.setenv("RENDER_FUSE_CUT", "0")
    assert _fuse_safe_active(_ctx(), force_accurate_cut=False) is False


def test_fuse_excluded_on_accurate_cut(monkeypatch):
    monkeypatch.setenv("RENDER_FUSE_CUT", "1")
    assert _fuse_safe_active(_ctx(), force_accurate_cut=True) is False


def test_fuse_excluded_on_resume(monkeypatch):
    monkeypatch.setenv("RENDER_FUSE_CUT", "1")
    assert _fuse_safe_active(_ctx(resume=True), force_accurate_cut=False) is False


def test_fuse_excluded_without_full_srt(monkeypatch):
    monkeypatch.setenv("RENDER_FUSE_CUT", "1")
    assert _fuse_safe_active(_ctx(full_srt=False), force_accurate_cut=False) is False


def test_fuse_excluded_on_explicit_tracker(monkeypatch):
    monkeypatch.setenv("RENDER_FUSE_CUT", "1")
    assert _fuse_safe_active(_ctx(tracker="csrt"), force_accurate_cut=False) is False


# ── Fix D1 (smoke-check 2026-07): guard phụ đề nhận full SRT làm nguồn ──────
# Guard trong prepare_part_assets chỉ được tắt phụ đề khi CẢ raw_part lẫn
# full SRT đều bất khả dụng. Pin ở mức source (cùng pattern các test guard
# hiện có của part_asset_planner) vì hàm 600-LOC không có seam unit-test.

def test_subtitle_guard_considers_full_srt_source():
    from pathlib import Path
    import app.features.render.engine.stages.part_asset_planner as pap

    src = Path(pap.__file__).read_text(encoding="utf-8")
    assert "not raw_part.exists() and not _full_srt_usable" in src, (
        "guard phụ đề trong part_asset_planner phải kiểm cả full SRT — "
        "thiếu nó thì đường fuse (raw_part không tồn tại) mất phụ đề âm thầm"
    )


# ── Fix D2 (smoke-check 2026-07): nhánh motion fused forward reframe_mode ──

def test_fused_motion_branch_forwards_reframe_cfg(monkeypatch, tmp_path):
    import app.features.render.engine.motion as motion_pkg
    from app.features.render.engine.encoder.clip_renderer import render_part_from_source

    captured: dict = {}

    def _stub_crop(**kwargs):
        captured.update(kwargs)
        return None

    monkeypatch.setattr(motion_pkg, "render_motion_aware_crop", _stub_crop)
    render_part_from_source(
        str(tmp_path / "src.mp4"), str(tmp_path / "out.mp4"),
        1.0, 5.0, None, None,
        motion_aware_crop=True,
        reframe_mode="center",
        video_codec="h264",
        encoder_mode="cpu",
    )
    cfg = captured.get("cfg")
    assert cfg is not None, "nhánh motion fused phải truyền cfg xuống render_motion_aware_crop"
    assert cfg.reframe_mode == "center", (
        f"reframe_mode của plan bị bỏ qua (nhận '{getattr(cfg, 'reframe_mode', None)}' thay vì 'center')"
    )
