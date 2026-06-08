"""Quality intelligence models for post-render assessment.

Plain dataclasses — no external dependencies.
Never raises; all methods are defensively coded.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime


# ---------------------------------------------------------------------------
# Scoring penalty table
# ---------------------------------------------------------------------------
_SEVERITY_PENALTY: dict[str, float] = {
    "critical": 100.0,
    "error": 25.0,
    "warning": 10.0,
    "info": 2.0,
}

_ALLOWED_SEVERITIES = frozenset(_SEVERITY_PENALTY)


@dataclass
class QualityIssue:
    """A single quality issue detected in a rendered output."""

    code: str
    severity: str  # "info" | "warning" | "error" | "critical"
    message: str
    confidence: float  # clamped to [0.0, 1.0]
    part_no: int | None = None
    evidence: dict = field(default_factory=dict)
    recommended_action: str | None = None

    def __post_init__(self) -> None:
        # Clamp confidence to [0.0, 1.0]
        try:
            self.confidence = max(0.0, min(1.0, float(self.confidence)))
        except Exception:
            self.confidence = 0.5
        # Normalise severity
        if self.severity not in _ALLOWED_SEVERITIES:
            self.severity = "warning"

    def to_dict(self) -> dict:
        try:
            return {
                "code": str(self.code),
                "severity": str(self.severity),
                "message": str(self.message),
                "confidence": float(self.confidence),
                "part_no": self.part_no,
                "evidence": dict(self.evidence) if self.evidence else {},
                "recommended_action": self.recommended_action,
            }
        except Exception:
            return {
                "code": str(self.code or "unknown"),
                "severity": "warning",
                "message": str(self.message or ""),
                "confidence": 0.5,
                "part_no": None,
                "evidence": {},
                "recommended_action": None,
            }


@dataclass
class QualityReport:
    """Aggregate quality report for a single rendered part."""

    job_id: str | None = None
    part_no: int | None = None
    score: float = 100.0  # clamped to [0.0, 100.0]
    issues: list[QualityIssue] = field(default_factory=list)
    metrics: dict = field(default_factory=dict)
    ai_trace_refs: list[str] = field(default_factory=list)
    created_at: str = field(default_factory=lambda: datetime.utcnow().isoformat())

    def __post_init__(self) -> None:
        try:
            self.score = max(0.0, min(100.0, float(self.score)))
        except Exception:
            self.score = 100.0

    def add_issue(self, issue: QualityIssue) -> None:
        """Append issue and deduct its penalty from score (clamped to [0, 100])."""
        try:
            self.issues.append(issue)
            penalty = _SEVERITY_PENALTY.get(issue.severity, 10.0)
            self.score = max(0.0, min(100.0, self.score - penalty))
        except Exception:
            pass

    def to_dict(self) -> dict:
        try:
            return {
                "job_id": self.job_id,
                "part_no": self.part_no,
                "score": float(self.score),
                "issues": [i.to_dict() for i in (self.issues or [])],
                "metrics": dict(self.metrics) if self.metrics else {},
                "ai_trace_refs": list(self.ai_trace_refs) if self.ai_trace_refs else [],
                "created_at": str(self.created_at),
            }
        except Exception:
            return {
                "job_id": self.job_id,
                "part_no": self.part_no,
                "score": float(self.score),
                "issues": [],
                "metrics": {},
                "ai_trace_refs": [],
                "created_at": str(self.created_at),
            }
