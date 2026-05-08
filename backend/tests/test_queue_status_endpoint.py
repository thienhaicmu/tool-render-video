"""
Guard tests for GET /api/render/queue-status (P2-1).

Tests the route function directly (no TestClient / httpx required).
"""

from unittest.mock import patch


class TestQueueStatusEndpoint:
    def _call(self, active_count=0):
        """Call the route handler directly with mocked pipeline state."""
        with patch("app.orchestration.render_pipeline._render_active_count", [active_count]):
            from app.routes.render import get_queue_status
            return get_queue_status()

    def test_returns_dict(self):
        result = self._call(0)
        assert isinstance(result, dict)

    def test_has_active_renders_key(self):
        result = self._call(0)
        assert "active_renders" in result

    def test_has_max_renders_key(self):
        result = self._call(0)
        assert "max_renders" in result

    def test_active_renders_zero_when_idle(self):
        result = self._call(0)
        assert result["active_renders"] == 0

    def test_active_renders_reflects_count(self):
        result = self._call(2)
        assert result["active_renders"] == 2

    def test_max_renders_is_positive(self):
        result = self._call(0)
        assert result["max_renders"] >= 1
