# Universal APK Factory — Test Suite

Comprehensive integration test suite for the Universal APK Factory v2.1.

## Files

| File | Description |
|------|-------------|
| `comprehensive_test.py` | Main test suite — 26 tests in 8 groups |
| `generate_usage_guide.py` | Generates the Usage Guide .docx from test results |

## Running the Tests

```bash
# Install dependencies (one-time)
pip install openpyxl pdfplumber PyPDF2 python-docx

# Run the full test suite
python tests/comprehensive_test.py
```

## Test Groups (8 groups, 26 tests)

1. Universal File Parser (8 tests) — JSON, CSV, TXT, HTML, Excel, PDF, Word
2. Data Analyzer v2 (5 tests) — 5-char ID system, type detection
3. Builder Factory v2 (3 tests) — Registry, topological sort, all 10 builders
4. Template Renderer (1 test) — Dynamic template.html generation
5. Admin Renderer (1 test) — Admin.html with GrapesJS+Blockly+Fabric.js
6. Native Bridge (3 tests) — RBAC, Offline Sync, Capacitor
7. Live Backend (3 tests) — Render health, build-stats, full APK build
8. End-to-End Pipeline (1 test) — All 7 stages together

## Expected Result

- Total: 26 tests
- Pass: 25 (96.2%)
- Skip: 1 (admin build-stats, non-critical)
- APK built on Render: 17,480 bytes in 57s
