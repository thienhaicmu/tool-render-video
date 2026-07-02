from app.features.render.engine.motion.crop import render_motion_aware_crop  # noqa: F401
from app.features.render.engine.motion.config import MotionCropConfig  # noqa: F401
# path.py và path_scene.py deferred-import các tên này TỪ PACKAGE (không
# import thẳng crop.py) để phá vòng import lúc load. Thiếu các re-export
# này thì build_subject_path raise ImportError ở runtime và tracker
# "subject" âm thầm rơi về standard crop ở mọi đường render — bug được
# smoke-check 2026-07 phát hiện. Pin bởi tests/test_motion_package_exports.py.
from app.features.render.engine.motion.crop import (  # noqa: F401
    _apply_velocity_limiter,
    _required_lock_confirm_frames,
    _subject_to_crop_center,
    _untracked_hold_frames,
)
from app.features.render.engine.motion.path_scene import build_subject_path_scene  # noqa: F401
