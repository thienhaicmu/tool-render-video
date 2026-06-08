# Architecture & Workflow Audit — 2026-06-06

Branch audited: `feature/ai-workflow-upgrade` @ commit `f3b6858` ("UI mớ").

**Methodology:** Source code is the only source of truth. Existing documentation (README, CLAUDE.md, `docs/review/**`, `docs/RENDER_PIPELINE.md`, `docs/ARCHITECTURE.md`, etc.) was deliberately ignored unless explicitly cross-referenced as a finding. Every claim cites `file:line` evidence.

**Result:** 5.4 / 10. See [28_executive_summary.md](28_executive_summary.md).

---

## Phase 1 — Discover the Real System
- [01_frontend_inventory.md](01_frontend_inventory.md)
- [02_backend_inventory.md](02_backend_inventory.md)
- [03_database_inventory.md](03_database_inventory.md)

## Phase 2 — Reverse-Engineer Workflows
- [04_workflow_user.md](04_workflow_user.md)
- [05_workflow_system.md](05_workflow_system.md)
- [06_workflow_ai.md](06_workflow_ai.md)
- [07_workflow_render.md](07_workflow_render.md)

## Phase 3 — Architecture Review
- [08_architecture_review.md](08_architecture_review.md)

## Phase 4 — Code Quality Audit
- [09_dead_code_report.md](09_dead_code_report.md)
- [10_duplication_report.md](10_duplication_report.md)
- [11_bug_risk_report.md](11_bug_risk_report.md)

## Phase 5 — Tool & Feature Verification
- [12_tool_audit.md](12_tool_audit.md)

## Phase 6 — API Audit
- [13_api_catalog.md](13_api_catalog.md)

## Phase 7 — FE ↔ BE Contract Audit
- [14_contract_audit.md](14_contract_audit.md)

## Phase 8 — Database Audit
- [15_database_review.md](15_database_review.md)

## Phase 9 — Test Coverage Audit
- [16_test_audit.md](16_test_audit.md)

## Phase 10 — New Documentation Set
- [17_system_overview.md](17_system_overview.md)
- [18_architecture.md](18_architecture.md)
- [19_backend.md](19_backend.md)
- [20_frontend.md](20_frontend.md)
- [21_database.md](21_database.md)
- [22_ai_pipeline.md](22_ai_pipeline.md)
- [23_render_pipeline.md](23_render_pipeline.md)
- [24_api_reference.md](24_api_reference.md)
- [25_deployment.md](25_deployment.md)
- [26_known_issues.md](26_known_issues.md)

## Phase 11 — Future Roadmap + Executive Summary
- [27_future_roadmap.md](27_future_roadmap.md)
- [28_executive_summary.md](28_executive_summary.md)

---

## Quick navigation

- **What is this system?** → [17_system_overview.md](17_system_overview.md)
- **Where's the code?** → [19_backend.md](19_backend.md) + [20_frontend.md](20_frontend.md)
- **What's broken?** → [26_known_issues.md](26_known_issues.md)
- **What should we do first?** → [28_executive_summary.md](28_executive_summary.md) §"Top 20 actions"
- **Detailed roadmap?** → [27_future_roadmap.md](27_future_roadmap.md)

## Audit stats

| Metric | Count |
|---|---|
| Phases completed | 11 / 11 |
| Deliverables (markdown files) | 28 |
| Backend source LOC analyzed | ~40,000 |
| Frontend source LOC analyzed | ~14,000 |
| Endpoints catalogued | 70 |
| Distinct findings (HIGH severity) | 15 |
| Distinct findings (MED severity) | ~35 |
| Distinct findings (LOW severity) | ~30 |
| Architecture score | 5.4 / 10 |
