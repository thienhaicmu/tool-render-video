"""Pin contract re-export của package motion (fix D3, smoke-check 2026-07).

``motion/path.py`` và ``motion/path_scene.py`` deferred-import 4 helper này
TỪ PACKAGE (để phá vòng import lúc load). Nếu ``motion/__init__.py`` không
re-export chúng, ``build_subject_path`` raise ImportError ở runtime và
tracker "subject" (reframe mặc định) âm thầm rơi về standard crop trên MỌI
đường render — QA không bắt được vì chỉ kiểm stream/duration.
"""
import importlib


def test_package_reexports_deferred_helpers():
    pkg = importlib.import_module("app.features.render.engine.motion")
    for name in (
        "_subject_to_crop_center",
        "_apply_velocity_limiter",
        "_required_lock_confirm_frames",
        "_untracked_hold_frames",
    ):
        assert hasattr(pkg, name), (
            f"motion/__init__.py thiếu re-export '{name}' — build_subject_path "
            "sẽ ImportError ở runtime và subject tracker rơi về standard crop"
        )


def test_deferred_import_in_path_module_resolves():
    # Đúng câu import mà path.py:96 thực thi lúc runtime.
    from app.features.render.engine.motion import (  # noqa: F401
        _apply_velocity_limiter,
        _required_lock_confirm_frames,
        _subject_to_crop_center,
        build_subject_path_scene,
    )
