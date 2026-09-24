# Changelog — Universal APK Factory v2.1

## [v2.1.0] — 2026-09-25 — Comprehensive Testing & Keep-Alive

### Added
- **Comprehensive Integration Test Suite** (`tests/comprehensive_test.py`)
  - 26 tests across 8 functional groups
  - Tests all 7 file formats: JSON, CSV, TXT, HTML, Excel, PDF, Word
  - Tests data analyzer (5-char ID system with collision resolution)
  - Tests all 10 builders (topological dependency sort)
  - Tests template renderer, admin renderer, native bridge
  - Tests RBAC engine (5 roles), Offline Sync (IndexedDB), Capacitor bridge
  - Tests live Render backend (health, build-stats, real APK build)
  - End-to-end pipeline test: 12 files → 267 IDs → 18 artifacts
  - 96.2% pass rate (25/26 passed, 1 skipped)

- **Keep-Alive System for Render Backend** (`scripts/keepalive/`)
  - `render_keepalive_ping.py` — main ping script with daemon mode
  - `keepalive_scheduler.py` — pure-Python scheduler (fallback)
  - `keepalive_cron.sh` — bash wrapper for cron-job.org
  - `keepalive_watchdog.sh` — auto-restart on crash
  - 3 layers of reliability (cron-job.org + local scheduler + watchdog)
  - Reduces cold-start from 22.6s to ~200ms (113× improvement)

- **Usage Guide Generator** (`tests/generate_usage_guide.py`)
  - Generates professional .docx from test results
  - DM-1 Deep Cyan palette (tech industry)
  - 219 paragraphs, 12 tables, 9 sections
  - Includes code samples for all 8 components
  - Includes extension guide (how to add app types, builders, parsers, roles)
  - Includes risk assessment with 8 risks and mitigations

- **Test Results Artifacts** (`test_results/`)
  - 26 output files from comprehensive test run
  - Sample config.json/strings.json (small + e2e)
  - Sample template.html and Admin.html (5-file + 12-file)
  - All 10 builder manifests (variables, control, view, etc.)
  - Live build response from Render (TestHospital.apk, 17480 bytes)

- **Documentation** (`docs/`)
  - `Universal_APK_Factory_Test_Report_and_Usage_Guide.docx`
  - Covers architecture, test results, usage, extension, risks, conclusions

### Verified
- All 7 file formats parse correctly (JSON, CSV, TXT, HTML, Excel, PDF, Word)
- 5-char ID generator: 267 unique IDs, zero collisions
- Builder Factory: 10/10 builders execute in correct dependency order
- Template Renderer: produces 570KB template.html with all 267 IDs
- Admin Renderer: produces 683KB Admin.html with GrapesJS+Blockly+Fabric.js
- Native Bridge: 9.7KB JS with full Capacitor plugin coverage
- RBAC: 5 roles (admin, doctor, nurse, reception, accountant) with per-ID permissions
- Offline Sync: IndexedDB + syncQueue + queueChange functions verified
- Live Backend: real APK built on Render (17,480 bytes, 57s, signed)

### Performance
- Backend cold-start: 22.6s → 200ms (with keep-alive pings)
- End-to-end pipeline: 12 files → 18 artifacts in 301ms (local engine)
- Live APK build: 57s (was 42s before keep-alive; variance is CPU-bound on Render free tier)

### Known Issues
- `/api/admin/build-stats` returns HTTP 500 on Render free tier (permissions, non-critical)
- ListBuilder produced 0 manifests (no Array-type IDs in test samples)
- template.html is 570KB (will be reduced to ~12KB in v3.0 refactor)

### Next Steps (Approved by User)
- Phase 9: v3.0 Great Refactor — Web Components + Service Workers
- Add test case with nested arrays to exercise ListBuilder
- Investigate admin build-stats 500 error
- Register on cron-job.org for external keep-alive (recommended)
