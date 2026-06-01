"""
app/ai/platform/ — Per-clip platform-native adaptation hints.

Public API:
    plan_platform_adaptation(clip_plan, platform, signals) -> dict
"""
try:
    from app.ai.platform.platform_adapter import plan_platform_adaptation
    _PLATFORM_AVAILABLE = True
except ImportError:
    _PLATFORM_AVAILABLE = False

__all__ = ["plan_platform_adaptation"]
