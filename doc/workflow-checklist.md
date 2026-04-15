# Workflow Checklist (Source of Truth)

This checklist is the canonical input for the AUTO QA runner used by `/test`.

## Phase: App Lifecycle

### Step APP_START - Backend startup and health
- category: app_lifecycle
- severity: critical
- expected_events: app.startup, health.ok
- expected_states: backend_running
- validation_rules:
  - health_endpoint_200
- failure_conditions:
  - backend_unreachable
- qa_notes: App must respond before any workflow checks continue.
- developer_notes: Check startup logs, port conflicts, and runtime exceptions.

### Step APP_READY - Warmup/status endpoint readiness
- category: app_lifecycle
- severity: major
- expected_events: warmup.status
- expected_states: app_ready
- validation_rules:
  - warmup_status_endpoint_200
- failure_conditions:
  - warmup_route_unavailable
- qa_notes: System should report warmup status without crashing.
- developer_notes: Validate `/api/warmup/status` route wiring and startup sequence.

## Phase: Profile And Login

### Step PROFILE_STORAGE - Profile/channel storage readiness
- category: profile_system
- severity: critical
- expected_events: profile.ensure
- expected_states: channels_dir_available
- validation_rules:
  - directory_exists:CHANNELS_DIR
  - directory_writable:CHANNELS_DIR
- failure_conditions:
  - missing_or_read_only_profile_storage
- qa_notes: Profile base storage must exist and be writable.
- developer_notes: Verify configured `CHANNELS_DIR` resolution and permissions.

### Step LOGIN_API - Login endpoints available
- category: login
- severity: critical
- expected_events: login.check, login.start
- expected_states: login_flow_available
- validation_rules:
  - openapi_has_paths:/api/upload/login/check,/api/upload/login/start
- failure_conditions:
  - login_endpoints_missing
- qa_notes: Login workflow cannot proceed without login endpoints.
- developer_notes: Check upload router registration and route prefixes.

## Phase: Proxy And Scheduling

### Step PROXY_CONFIG - Proxy config endpoints and persistence path
- category: proxy
- severity: major
- expected_events: proxy.config.save
- expected_states: proxy_settings_available
- validation_rules:
  - openapi_has_paths:/api/upload/config/save,/api/upload/settings/{channel_code}
  - directory_exists:CHANNELS_DIR
- failure_conditions:
  - proxy_config_unavailable
- qa_notes: Proxy setup UI requires backend save/load support.
- developer_notes: Validate upload settings schema and persistence behavior.

### Step SCHEDULING_API - Scheduling endpoints available
- category: scheduling
- severity: major
- expected_events: upload.schedule
- expected_states: schedule_flow_available
- validation_rules:
  - openapi_has_paths:/api/upload/schedule,/api/upload/schedule/start
- failure_conditions:
  - scheduling_endpoints_missing
- qa_notes: Scheduling flow must be callable by UI.
- developer_notes: Validate route contracts and run-state retrieval endpoints.

## Phase: Video Pipeline

### Step VIDEO_LOCAL_GUARD - Local source missing-file handling
- category: video_pipeline
- severity: critical
- expected_events: render.quick_process
- expected_states: local_file_validation
- validation_rules:
  - render_missing_local_returns_400_or_404
- failure_conditions:
  - missing_local_file_not_rejected
- qa_notes: Missing local input must fail clearly.
- developer_notes: Ensure explicit file existence checks in quick-process route.

### Step VIDEO_YOUTUBE_GUARD - Invalid YouTube URL handling
- category: video_pipeline
- severity: critical
- expected_events: render.quick_process
- expected_states: youtube_url_validation
- validation_rules:
  - render_invalid_youtube_returns_400
- failure_conditions:
  - invalid_youtube_url_not_rejected
- qa_notes: Invalid YouTube input must fail with clear client error.
- developer_notes: Keep URL validation and error mapping deterministic.

## Phase: Upload UI Readiness

### Step UPLOAD_SELECTOR_BASELINE - Upload selector baseline exists in automation
- category: upload_ui
- severity: major
- expected_events: upload.select_file
- expected_states: file_input_selector_defined
- validation_rules:
  - source_contains:backend/app/services/upload_engine.py|input[type='file']
- failure_conditions:
  - upload_file_selector_missing
- qa_notes: Upload flow requires a known file input selector baseline.
- developer_notes: Selector fallback list should remain explicit and maintainable.

### Step UPLOAD_STATE_MACHINE - Upload run state transitions exposed
- category: upload
- severity: major
- expected_events: upload.run
- expected_states: upload_state_detection
- validation_rules:
  - source_contains:backend/app/services/upload_engine.py|"status": "running"
  - source_contains:backend/app/services/upload_engine.py|"status": "failed"
  - source_contains:backend/app/services/upload_engine.py|"status": "completed"
- failure_conditions:
  - upload_run_states_incomplete
- qa_notes: Operator needs clear running/completed/failed states.
- developer_notes: Preserve deterministic run status updates.

## Phase: Logging And Diagnostics

### Step LOG_STRUCTURED - Structured log entries available
- category: logging
- severity: major
- expected_events: any
- expected_states: structured_logging_present
- validation_rules:
  - logs_have_structured_entries
- failure_conditions:
  - no_structured_log_entries
- qa_notes: Structured logs improve triage and retest speed.
- developer_notes: Keep JSON-like error events parseable by `/error` and `/fix`.

### Step LOG_ERROR_CODE - Error entries include error_code when available
- category: logging
- severity: minor
- expected_events: error
- expected_states: error_code_quality
- validation_rules:
  - error_entries_have_error_code
- failure_conditions:
  - error_entries_missing_error_code
- qa_notes: Missing error codes reduce support/debug quality.
- developer_notes: Emit stable error_code families (DL/RN/LG/UP/etc) in failures.
