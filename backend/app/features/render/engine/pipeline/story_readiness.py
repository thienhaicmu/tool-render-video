"""
story_readiness.py — GĐ4b: Production Readiness Validator cho Story render.

Một cổng TỔNG HỢP chạy sau khi plan đã resolve (assets + styling) và TRƯỚC khi tốn
tài nguyên (ảnh/TTS/encode): 8 nhóm tiêu chí, mỗi tiêu chí trả pass | warn | fail.

  FAIL (chặn render — chỉ những lỗi chắc chắn hỏng sản phẩm):
    nội dung rỗng / không có visual / thư mục xuất không ghi được / đĩa cạn (<1GB)
  WARN (render tiếp, hiển thị ở /plan + monitor):
    nhân vật nói thiếu asset, asset chờ duyệt, background slug hỏng, visual quá đông,
    hook quá dài, TTS engine trả phí thiếu key (còn fallback edge/piper),
    thời lượng lệch target, đĩa thấp (<5GB)

Pure + defensive: không I/O ngoài các probe được yêu cầu (output_dir/disk chỉ khi
truyền vào); mọi lỗi nội bộ degrade thành warn "readiness check error". Gate render
bằng STORY_READINESS_GATE (default on — nhưng FAIL-set đã tối thiểu nên gate chỉ
chặn đúng thứ chắc chắn chết).
"""
from __future__ import annotations

import logging
import os
import shutil
from pathlib import Path
from typing import Optional

logger = logging.getLogger("app.render.story_readiness")

PASS, WARN, FAIL = "pass", "warn", "fail"

_MIN_FREE_GB_FAIL = float(os.getenv("STORY_MIN_FREE_GB_FAIL", "1") or 1)
_MIN_FREE_GB_WARN = float(os.getenv("STORY_MIN_FREE_GB_WARN", "5") or 5)
_HOOK_MAX_CHARS = 60


def gate_enabled() -> bool:
    return os.getenv("STORY_READINESS_GATE", "1") == "1"


def _c(checks: list, cid: str, level: str, msg: str) -> None:
    checks.append({"id": cid, "level": level, "msg": msg})


def evaluate_readiness(plan, *, target_sec: int = 0,
                       output_dir: "Optional[Path]" = None) -> dict:
    """→ ``{ready, checks[], fails[], warns[]}``. Never raises."""
    checks: list = []
    try:
        # 1. content coverage
        beats = list(getattr(plan, "timeline", []) or [])
        if not beats or plan.is_empty():
            _c(checks, "content", FAIL, "timeline rỗng — không có gì để render")
        elif plan.image_count() <= 0:
            _c(checks, "content", FAIL, "không có visual nào")
        else:
            _c(checks, "content", PASS, f"{len(beats)} beat, {plan.image_count()} visual")

        # 2. scene continuity (post-normalize dangling refs must be zero)
        vis_ids = {v.id for v in plan.visuals}
        set_ids = {s.id for s in plan.settings}
        dangling = [b.id for b in beats if b.visual_id not in vis_ids]
        orphan_setting = [v.id for v in plan.visuals
                          if v.setting_id and v.setting_id not in set_ids]
        if dangling:
            _c(checks, "continuity", FAIL, f"beat trỏ visual không tồn tại: {dangling[:5]}")
        elif orphan_setting:
            _c(checks, "continuity", WARN, f"visual trỏ setting không tồn tại: {orphan_setting[:5]}")
        else:
            _c(checks, "continuity", PASS, "mọi tham chiếu beat→visual→setting hợp lệ")

        # 3. character identity (GĐ3 asset_status)
        st = dict(getattr(plan.render, "asset_status", None) or {})
        speaking = {b.primary_speaker() for b in beats if b.primary_speaker()}
        miss_speak = sorted(c for c in speaking if st.get(c) == "missing")
        approval = sorted(c for c, v in st.items() if v == "needs_approval")
        if miss_speak:
            _c(checks, "identity", WARN,
               f"nhân vật NÓI thiếu asset (render không overlay): {miss_speak[:5]}")
        elif approval:
            _c(checks, "identity", WARN, f"asset chờ duyệt: {approval[:5]}")
        else:
            _c(checks, "identity", PASS, "mọi nhân vật nói đều có asset")

        # 4. background resolution (slug đã gán phải tồn tại; thiếu → procedural fallback)
        try:
            from app.db.story_asset_repo import get_by_slug
            bad_bg = [s.id for s in plan.settings
                      if (getattr(s, "asset", "") or "").strip()
                      and not get_by_slug(s.asset, "background")]
        except Exception:
            bad_bg = []
        if bad_bg:
            _c(checks, "background", WARN,
               f"setting có slug kho không tồn tại (dùng nền procedural): {bad_bg[:5]}")
        else:
            _c(checks, "background", PASS, "background hợp lệ")

        # 5. composition
        crowded = [v.id for v in plan.visuals if len(getattr(v, "character_ids", []) or []) > 3]
        long_hooks = [b.id for b in beats
                      if b.hook and len((b.hook_text or "").strip()) > _HOOK_MAX_CHARS]
        if crowded or long_hooks:
            bits = []
            if crowded:
                bits.append(f"visual >3 nhân vật: {crowded[:3]}")
            if long_hooks:
                bits.append(f"hook >{_HOOK_MAX_CHARS} ký tự: {long_hooks[:3]}")
            _c(checks, "composition", WARN, "; ".join(bits))
        else:
            _c(checks, "composition", PASS, "bố cục trong giới hạn")

        # 6. TTS coverage (paid engine cần key; thiếu → còn fallback edge/piper)
        try:
            from app.features.render.engine.audio.tts import resolve_story_tts_engine
            eng = resolve_story_tts_engine(getattr(plan, "language", "") or "vi")
            key_env = {"elevenlabs": ("ELEVENLABS_API_KEY", "ELEVENLABS_API_KEYS"),
                       "gemini": ("GEMINI_API_KEY", "GEMINI_API_KEYS")}.get(eng, ())
            has_key = (not key_env) or any((os.getenv(k, "") or "").strip() for k in key_env)
            if has_key:
                _c(checks, "tts", PASS, f"engine {eng} sẵn sàng")
            else:
                _c(checks, "tts", WARN,
                   f"engine {eng} thiếu API key — sẽ rơi về edge/piper (chất giọng khác)")
        except Exception:
            _c(checks, "tts", WARN, "không kiểm được TTS engine")

        # 7. duration vs target
        if target_sec and target_sec > 0:
            est = plan.estimated_total_sec()
            if est < target_sec * 0.9:
                _c(checks, "duration", WARN,
                   f"ước tính ~{est:.0f}s < 90% target {target_sec}s")
            elif est > target_sec * 1.5:
                _c(checks, "duration", WARN,
                   f"ước tính ~{est:.0f}s vượt xa target {target_sec}s")
            else:
                _c(checks, "duration", PASS, f"~{est:.0f}s / target {target_sec}s")
        else:
            _c(checks, "duration", PASS, "không đặt target")

        # 8. storage/resources (chỉ khi render thật — /plan truyền output_dir=None)
        if output_dir is not None:
            try:
                out = Path(output_dir)
                out.mkdir(parents=True, exist_ok=True)
                probe = out / ".readiness_probe"
                probe.write_text("ok", encoding="utf-8")
                probe.unlink(missing_ok=True)
                free_gb = shutil.disk_usage(str(out)).free / (1024 ** 3)
                if free_gb < _MIN_FREE_GB_FAIL:
                    _c(checks, "storage", FAIL, f"đĩa còn {free_gb:.1f}GB (<{_MIN_FREE_GB_FAIL}GB)")
                elif free_gb < _MIN_FREE_GB_WARN:
                    _c(checks, "storage", WARN, f"đĩa còn {free_gb:.1f}GB")
                else:
                    _c(checks, "storage", PASS, f"đĩa còn {free_gb:.0f}GB")
            except Exception as exc:
                _c(checks, "storage", FAIL, f"thư mục xuất không ghi được: {exc}")
    except Exception as exc:                    # belt-and-suspenders — never raise
        logger.warning("story_readiness: evaluate error %s", exc)
        _c(checks, "internal", WARN, "readiness check error (bỏ qua)")

    fails = [c for c in checks if c["level"] == FAIL]
    warns = [c for c in checks if c["level"] == WARN]
    return {"ready": not fails, "checks": checks,
            "fails": [c["msg"] for c in fails], "warns": [c["msg"] for c in warns]}


__all__ = ["evaluate_readiness", "gate_enabled", "PASS", "WARN", "FAIL"]
