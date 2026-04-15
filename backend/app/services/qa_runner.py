import json
import re
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any
import urllib.error
import urllib.request

from app.core.config import APP_DATA_DIR, CHANNELS_DIR, LOGS_DIR, REPORTS_DIR

PROJECT_ROOT = Path(__file__).resolve().parents[3]
WORKFLOW_CHECKLIST_PATH = PROJECT_ROOT / "doc" / "workflow-checklist.md"
QA_REPORT_DIR = REPORTS_DIR / "qa"


@dataclass
class StepResult:
    id: str
    name: str
    category: str
    severity: str
    status: str
    reason: str
    expected: str
    observed: str
    evidence: str
    likely_module: str
    patch_target: list[str]


def _now() -> str:
    return datetime.utcnow().isoformat() + "Z"


def _http_get(url: str, timeout: int = 6) -> tuple[int | None, str]:
    try:
        with urllib.request.urlopen(url, timeout=timeout) as r:
            return r.status, r.read().decode("utf-8", errors="replace")
    except urllib.error.HTTPError as e:
        return e.code, e.read().decode("utf-8", errors="replace")
    except Exception as e:
        return None, str(e)


def _http_post_json(url: str, payload: dict[str, Any], timeout: int = 10) -> tuple[int | None, str]:
    data = json.dumps(payload).encode("utf-8")
    req = urllib.request.Request(url, data=data, method="POST")
    req.add_header("Content-Type", "application/json")
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            return resp.status, resp.read().decode("utf-8", errors="replace")
    except urllib.error.HTTPError as e:
        return e.code, e.read().decode("utf-8", errors="replace")
    except Exception as e:
        return None, str(e)


def _service_url() -> str:
    import os

    host = str(os.getenv("HOST", "127.0.0.1")).strip() or "127.0.0.1"
    port = str(os.getenv("PORT", "8000")).strip() or "8000"
    return f"http://{host}:{port}"


def _read_text(path: Path) -> str:
    return path.read_text(encoding="utf-8", errors="replace") if path.exists() else ""


def _read_recent_logs(max_files: int = 8, max_bytes: int = 200_000) -> list[tuple[str, list[str]]]:
    candidates: list[Path] = []
    for root in [LOGS_DIR, CHANNELS_DIR]:
        if root.exists():
            candidates.extend([p for p in root.rglob("*.log") if p.is_file()])
    candidates = sorted(candidates, key=lambda p: p.stat().st_mtime, reverse=True)[:max_files]

    out: list[tuple[str, list[str]]] = []
    for p in candidates:
        try:
            size = p.stat().st_size
            start = max(0, size - max_bytes)
            with p.open("rb") as f:
                if start:
                    f.seek(start)
                    f.readline()
                data = f.read().decode("utf-8", errors="replace")
            out.append((str(p), data.splitlines()))
        except Exception:
            continue
    return out


def _has_structured_log(recent_logs: list[tuple[str, list[str]]]) -> tuple[bool, str]:
    for src, lines in recent_logs:
        for ln in reversed(lines[-400:]):
            s = ln.strip()
            if not s.startswith("{"):
                continue
            try:
                obj = json.loads(s)
            except Exception:
                continue
            if isinstance(obj, dict) and (obj.get("level") or obj.get("event") or obj.get("message")):
                return True, f"structured entry found in {src}"
    return False, "no parseable JSON log entry found in recent logs"


def _error_code_quality(recent_logs: list[tuple[str, list[str]]]) -> tuple[bool, str]:
    seen_error = 0
    with_code = 0
    for _src, lines in recent_logs:
        for ln in lines[-500:]:
            s = ln.strip()
            if s.startswith("{"):
                try:
                    obj = json.loads(s)
                except Exception:
                    obj = None
                if isinstance(obj, dict):
                    level = str(obj.get("level") or "").upper()
                    msg = str(obj.get("message") or "")
                    if level in {"ERROR", "CRITICAL", "FATAL"} or "error" in msg.lower():
                        seen_error += 1
                        if str(obj.get("error_code") or "").strip():
                            with_code += 1
            elif re.search(r"\b(ERROR|Exception|Traceback|Failed)\b", s, re.IGNORECASE):
                seen_error += 1
    if seen_error == 0:
        return True, "no recent error entries to grade"
    if with_code > 0:
        return True, f"error_code present in {with_code}/{seen_error} recent error entries"
    return False, "recent error entries found but no structured error_code detected"


def _extract_mode(command_text: str) -> tuple[str, str]:
    tokens = [t.strip().lower() for t in (command_text or "").split() if t.strip()]
    mode = "default"
    view = "both"
    for t in tokens[1:]:
        if t in {"quick", "full", "ui"}:
            mode = t
        if t in {"qa", "dev"}:
            view = t
    return mode, view


def parse_workflow_checklist(path: Path = WORKFLOW_CHECKLIST_PATH) -> list[dict[str, Any]]:
    if not path.exists():
        return []

    lines = path.read_text(encoding="utf-8", errors="replace").splitlines()
    phase = ""
    current: dict[str, Any] | None = None
    current_list_key = ""
    steps: list[dict[str, Any]] = []

    list_fields = {"expected_events", "expected_states", "validation_rules", "failure_conditions", "patch_targets"}

    def _finish_step() -> None:
        nonlocal current
        if not current:
            return
        for k in list_fields:
            v = current.get(k)
            if isinstance(v, str):
                current[k] = [x.strip().strip("`") for x in v.split(",") if x.strip()]
            elif not isinstance(v, list):
                current[k] = []
        current.setdefault("developer_notes", "")
        current.setdefault("qa_notes", "")
        current.setdefault("severity", "major")
        current.setdefault("category", "general")
        current["phase"] = phase
        steps.append(current)
        current = None

    for raw in lines:
        line = raw.rstrip()
        if line.startswith("## Phase:"):
            _finish_step()
            phase = line.split(":", 1)[1].strip()
            current_list_key = ""
            continue

        if line.startswith("### Step "):
            _finish_step()
            current_list_key = ""
            body = line[len("### Step ") :].strip()
            m = re.match(r"^([A-Za-z0-9_\-]+)\s*-\s*(.+)$", body)
            if m:
                sid, name = m.group(1).strip(), m.group(2).strip()
            else:
                sid, name = body.replace(" ", "_").upper(), body
            current = {"id": sid, "name": name}
            continue

        if current is None:
            continue

        if re.match(r"^\s*-\s+[a-zA-Z_][a-zA-Z0-9_]*\s*:", line):
            content = re.sub(r"^\s*-\s+", "", line)
            key, val = content.split(":", 1)
            key = key.strip()
            val = val.strip()
            if key in list_fields:
                if val:
                    current[key] = [x.strip().strip("`") for x in val.split(",") if x.strip()]
                    current_list_key = ""
                else:
                    current[key] = []
                    current_list_key = key
            else:
                current[key] = val
                current_list_key = ""
            continue

        if current_list_key and re.match(r"^\s{2,}-\s+", line):
            item = re.sub(r"^\s{2,}-\s+", "", line).strip()
            if item:
                current.setdefault(current_list_key, []).append(item.strip("`"))

    _finish_step()
    return steps


def _default_patch_targets(category: str) -> list[str]:
    mapping = {
        "app_lifecycle": ["backend/app/main.py"],
        "profile_system": ["backend/app/services/upload_engine.py", "backend/app/routes/channels.py"],
        "login": ["backend/app/services/upload_engine.py", "backend/app/routes/upload.py"],
        "proxy": ["backend/app/services/upload_engine.py", "backend/app/routes/upload.py"],
        "scheduling": ["backend/app/routes/upload.py", "backend/app/services/upload_engine.py"],
        "video_pipeline": ["backend/app/routes/render.py", "backend/app/services/downloader.py"],
        "upload_ui": ["backend/app/services/upload_engine.py"],
        "upload": ["backend/app/services/upload_engine.py", "backend/app/routes/upload.py"],
        "logging": ["backend/app/services/dev_commands.py"],
    }
    return mapping.get(category, ["backend/app/services/dev_commands.py"])


def _evaluate_rule(rule: str, ctx: dict[str, Any]) -> tuple[bool | None, str, str]:
    service_url = ctx["service_url"]

    if rule == "health_endpoint_200":
        st, body = _http_get(service_url + "/health", timeout=4)
        return st == 200, "GET /health == 200", f"status={st} body={body[:120]}"

    if rule == "warmup_status_endpoint_200":
        if not ctx.get("backend_running"):
            return None, "GET /api/warmup/status == 200", "skipped: backend unavailable"
        st, body = _http_get(service_url + "/api/warmup/status", timeout=5)
        return st == 200, "GET /api/warmup/status == 200", f"status={st} body={body[:200]}"

    if rule.startswith("directory_exists:"):
        key = rule.split(":", 1)[1].strip()
        path = ctx.get("paths", {}).get(key)
        ok = bool(path and Path(path).exists())
        return ok, f"directory exists: {key}", str(path)

    if rule.startswith("directory_writable:"):
        key = rule.split(":", 1)[1].strip()
        path = ctx.get("paths", {}).get(key)
        if not path:
            return False, f"directory writable: {key}", "path missing"
        p = Path(path)
        try:
            p.mkdir(parents=True, exist_ok=True)
            probe = p / ".qa_write_probe"
            probe.write_text("ok", encoding="utf-8")
            probe.unlink(missing_ok=True)
            return True, f"directory writable: {key}", str(p)
        except Exception as e:
            return False, f"directory writable: {key}", str(e)

    if rule.startswith("openapi_has_paths:"):
        if not ctx.get("backend_running"):
            return None, "openapi contains required paths", "skipped: backend unavailable"
        needed = [x.strip() for x in rule.split(":", 1)[1].split(",") if x.strip()]
        if "openapi_paths" not in ctx:
            st, body = _http_get(service_url + "/openapi.json", timeout=6)
            if st != 200:
                ctx["openapi_paths"] = set()
                ctx["openapi_error"] = f"status={st}"
            else:
                try:
                    obj = json.loads(body)
                    ctx["openapi_paths"] = set((obj.get("paths") or {}).keys())
                except Exception:
                    ctx["openapi_paths"] = set()
                    ctx["openapi_error"] = "invalid-json"
        paths: set[str] = ctx.get("openapi_paths", set())
        missing = [p for p in needed if p not in paths]
        return len(missing) == 0, f"openapi has paths: {needed}", f"missing={missing}"

    if rule == "render_invalid_youtube_returns_400":
        if not ctx.get("backend_running"):
            return None, "invalid youtube url rejected with 400", "skipped: backend unavailable"
        payload = {
            "source": "youtube",
            "url": "invalid_url",
            "output": str(APP_DATA_DIR / "qa_invalid_youtube.mp4"),
        }
        st, body = _http_post_json(service_url + "/api/render/quick-process", payload, timeout=12)
        return st == 400, "POST quick-process invalid youtube -> 400", f"status={st} body={body[:180]}"

    if rule == "render_missing_local_returns_400_or_404":
        if not ctx.get("backend_running"):
            return None, "missing local file rejected", "skipped: backend unavailable"
        payload = {
            "source": "local",
            "path": str(APP_DATA_DIR / "definitely_missing_input.mp4"),
            "output": str(APP_DATA_DIR / "qa_missing_local_output.mp4"),
        }
        st, body = _http_post_json(service_url + "/api/render/quick-process", payload, timeout=12)
        return st in {400, 404}, "POST quick-process missing local -> 400/404", f"status={st} body={body[:180]}"

    if rule.startswith("source_contains:"):
        try:
            rest = rule.split(":", 1)[1]
            file_rel, needle = rest.split("|", 1)
            target = PROJECT_ROOT / file_rel.strip()
            txt = _read_text(target)
            ok = needle in txt
            return ok, f"source contains '{needle}' in {file_rel.strip()}", str(target)
        except Exception as e:
            return False, "source contains rule", f"invalid rule: {e}"

    if rule == "logs_have_structured_entries":
        ok, msg = _has_structured_log(ctx["recent_logs"])
        return ok, "recent logs include structured JSON entries", msg

    if rule == "error_entries_have_error_code":
        ok, msg = _error_code_quality(ctx["recent_logs"])
        return ok, "error entries include error_code", msg

    return None, f"unsupported rule: {rule}", "skipped unsupported rule"


def _step_scope_filter(steps: list[dict[str, Any]], mode: str) -> list[dict[str, Any]]:
    if mode == "quick":
        return [s for s in steps if str(s.get("severity", "")).lower() == "critical"]
    if mode == "ui":
        return [s for s in steps if str(s.get("category", "")).lower() in {"upload_ui", "upload", "login", "proxy"}]
    return steps


def _evaluate_step(step: dict[str, Any], ctx: dict[str, Any]) -> StepResult:
    sid = str(step.get("id") or "UNKNOWN")
    name = str(step.get("name") or sid)
    category = str(step.get("category") or "general")
    severity = str(step.get("severity") or "major").lower()
    rules = [str(x).strip() for x in (step.get("validation_rules") or []) if str(x).strip()]

    if not rules:
        return StepResult(
            id=sid,
            name=name,
            category=category,
            severity=severity,
            status="skipped",
            reason="No validation rules",
            expected="N/A",
            observed="N/A",
            evidence="",
            likely_module=category,
            patch_target=_default_patch_targets(category),
        )

    blocking_failures: list[str] = []
    skipped = 0
    evidences: list[str] = []
    expected_all: list[str] = []

    for rule in rules:
        ok, expected, observed = _evaluate_rule(rule, ctx)
        expected_all.append(expected)
        evidences.append(f"{rule}: {observed}")
        if ok is None:
            skipped += 1
            continue
        if not ok:
            blocking_failures.append(f"{rule}: {observed}")

    if blocking_failures:
        status = "fail"
        reason = blocking_failures[0]
    elif skipped == len(rules):
        status = "skipped"
        reason = "All rules skipped due to unmet preconditions"
    else:
        status = "pass"
        reason = "All runnable validations passed"

    expected_events = ", ".join(step.get("expected_events") or [])
    expected_states = ", ".join(step.get("expected_states") or [])
    expected = f"events=[{expected_events}] states=[{expected_states}] rules={len(rules)}"

    observed = reason
    evidence = " | ".join(evidences[:4])
    likely_module = " -> ".join([x for x in [category, sid] if x])

    return StepResult(
        id=sid,
        name=name,
        category=category,
        severity=severity,
        status=status,
        reason=reason,
        expected=expected,
        observed=observed,
        evidence=evidence,
        likely_module=likely_module,
        patch_target=_default_patch_targets(category),
    )


def _to_qa_view(results: list[StepResult]) -> dict[str, Any]:
    total = len(results)
    passed = [r for r in results if r.status == "pass"]
    failed = [r for r in results if r.status == "fail"]
    skipped = [r for r in results if r.status == "skipped"]
    return {
        "total_steps": total,
        "passed": len(passed),
        "failed": len(failed),
        "skipped": len(skipped),
        "failed_steps": [
            {
                "step": f"{r.id} - {r.name}",
                "severity": r.severity,
                "reason": r.reason,
                "suggested_next_action": "/error" if r.severity in {"critical", "major"} else "/test qa",
            }
            for r in failed
        ],
    }


def _to_dev_view(results: list[StepResult]) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    for r in results:
        if r.status != "fail":
            continue
        out.append(
            {
                "step_id": r.id,
                "step_name": r.name,
                "category": r.category,
                "severity": r.severity,
                "failure_reason": r.reason,
                "expected": r.expected,
                "observed": r.observed,
                "relevant_evidence": r.evidence,
                "likely_module_or_area": r.likely_module,
                "likely_root_cause": r.reason,
                "suggested_patch_target": r.patch_target,
            }
        )
    return out


def _write_reports(mode: str, qa: dict[str, Any], dev: list[dict[str, Any]], results: list[StepResult]) -> dict[str, str]:
    QA_REPORT_DIR.mkdir(parents=True, exist_ok=True)
    json_path = QA_REPORT_DIR / "latest-report.json"
    md_path = QA_REPORT_DIR / "latest-report.md"

    payload = {
        "timestamp": _now(),
        "mode": mode,
        "qa": qa,
        "developer": dev,
        "steps": [r.__dict__ for r in results],
    }
    json_path.write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")

    lines = [
        "# QA Report",
        "",
        f"- Timestamp: {payload['timestamp']}",
        f"- Mode: {mode}",
        f"- Total: {qa['total_steps']}",
        f"- Passed: {qa['passed']}",
        f"- Failed: {qa['failed']}",
        f"- Skipped: {qa['skipped']}",
        "",
        "## Failed Steps",
    ]
    if not qa["failed_steps"]:
        lines.append("- None")
    else:
        for f in qa["failed_steps"]:
            lines.append(f"- {f['step']} ({f['severity']}): {f['reason']}")
    md_path.write_text("\n".join(lines) + "\n", encoding="utf-8")

    return {"json": str(json_path), "markdown": str(md_path)}


def run_test_command(command_text: str) -> dict[str, Any]:
    mode, view = _extract_mode(command_text)
    steps = parse_workflow_checklist()
    if not steps:
        return {
            "command": "/test",
            "status": "fail",
            "Summary": "workflow checklist not found or empty",
            "QA View": {"total_steps": 0, "passed": 0, "failed": 0, "skipped": 0, "failed_steps": []},
            "Developer View": [],
            "Suggested next fixes": ["Create doc/workflow-checklist.md"],
        }

    service_url = _service_url()
    health_status, _ = _http_get(service_url + "/health", timeout=4)
    backend_running = health_status == 200

    ctx = {
        "service_url": service_url,
        "backend_running": backend_running,
        "paths": {
            "APP_DATA_DIR": str(APP_DATA_DIR),
            "CHANNELS_DIR": str(CHANNELS_DIR),
            "LOGS_DIR": str(LOGS_DIR),
            "REPORTS_DIR": str(REPORTS_DIR),
        },
        "recent_logs": _read_recent_logs(),
    }

    scoped_steps = _step_scope_filter(steps, mode)
    results = [_evaluate_step(step, ctx) for step in scoped_steps]

    qa_view = _to_qa_view(results)
    dev_view = _to_dev_view(results)
    report_files = _write_reports(mode, qa_view, dev_view, results)

    failed_critical = any(r.status == "fail" and r.severity == "critical" for r in results)
    failed_any = any(r.status == "fail" for r in results)
    status = "fail" if failed_critical else ("partial" if failed_any else "ok")

    out: dict[str, Any] = {
        "command": "/test",
        "mode": mode,
        "status": status,
        "Summary": f"Workflow validation completed: {qa_view['passed']} passed, {qa_view['failed']} failed, {qa_view['skipped']} skipped.",
        "Test command(s) used": [f"{command_text.strip() or '/test'}", "GET /health", "GET /openapi.json (conditional)", "POST /api/render/quick-process (validation)"] ,
        "Report files": report_files,
        "Suggested next fixes": ["Run /error" if qa_view["failed"] else "Run /test full for deeper checks"],
    }

    if view in {"both", "qa"}:
        out["QA View"] = qa_view
    if view in {"both", "dev"}:
        out["Developer View"] = dev_view

    return out
