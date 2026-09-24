# Test Results — Universal APK Factory v2.1

This directory contains the output artifacts from the comprehensive integration
test suite. All files were generated on 2026-09-25 by running
`tests/comprehensive_test.py`.

## Result Summary

| Metric | Value |
|--------|-------|
| Total tests | 26 |
| Passed | 25 ✓ |
| Failed | 0 ✗ |
| Skipped | 1 ⊘ (admin build-stats endpoint, non-critical) |
| Pass rate | **96.2%** |
| APK built on Render | TestHospital.apk — 17,480 bytes |
| Build duration | 56.9 seconds |
| End-to-end pipeline | 267 IDs, 40 datasets, 431 items, 18 artifacts |

## Files

### Test Report

| File | Description |
|------|-------------|
| `test_report.json` | Machine-readable full test report |
| `raw_output.txt` | Complete test execution log |
| `build_apk_response.json` | Live Render build response |

### Sample Outputs (small dataset, 5 files)

| File | Size | Description |
|------|------|-------------|
| `test_config.json` | 66 KB | config.json from 5-file sample |
| `test_strings.json` | 417 KB | strings.json from 5-file sample |
| `test_template.html` | 342 KB | template.html from 5-file sample |
| `test_admin.html` | 406 KB | Admin.html from 5-file sample |
| `test_rbac_engine.js` | 26 KB | RBAC engine with 5 roles |

### End-to-End Outputs (all 12 sample files)

| File | Size | Description |
|------|------|-------------|
| `e2e_config.json` | 113 KB | The Map: 267 IDs, 40 datasets, 431 items |
| `e2e_strings.json` | 709 KB | The Execution Matrix: 3656 values |
| `e2e_template.html` | 573 KB | User UI with all 267 widgets |
| `e2e_Admin.html` | 683 KB | Control panel with GrapesJS+Blockly+Fabric.js |
| `e2e_native_bridge.js` | 12 KB | Capacitor bridge + RBAC + Offline Sync |
| `e2e__build_manifest.json` | 782 B | Pipeline summary: 10 builders succeeded |
| `e2e__variables.java` | 18 KB | 261 Java variable declarations |
| `e2e__variables.js` | 13 KB | 261 JavaScript variable declarations |
| `e2e__view_fragments.html` | 42 KB | 102 XML layout fragments |
| `e2e__view_styles.css` | 43 KB | CSS for all widget types |
| `e2e__final_strings.xml` | 130 KB | 2579 strings.xml entries |
| `e2e__control_manifest.json` | 48 KB | 267 control/validation rules |
| `e2e__operators_manifest.json` | 28 KB | 192 operator sets |
| `e2e__moreblocks_manifest.json` | 38 KB | 271 reusable code blocks |
| `e2e__files_manifest.json` | 2 KB | 13 registered files |
| `e2e__components_manifest.json` | 1 KB | 6 component definitions |
| `e2e__math_manifest.json` | 1 KB | 12 math formulas |
| `e2e__lists_manifest.json` | 2 B | 0 list manifests (no Array IDs) |

## How to Re-generate

```bash
# Re-run the full test suite (regenerates all files in this directory)
python tests/comprehensive_test.py

# View results
cat test_results/test_report.json | python -m json.tool

# Open the end-to-end template in a browser
firefox test_results/e2e_template.html
```

## Live Backend Verification

```bash
# 1. Check backend health
curl -s https://html-to-apk-1789777001.onrender.com/api/app-types | python -m json.tool

# 2. Build a test APK (~57 seconds when warm)
curl -s -X POST https://html-to-apk-1789777001.onrender.com/api/build-apk-from-html \
  -H 'Content-Type: application/json' \
  -d '{"app_name":"Test","package_name":"com.test.app",
       "html":"<html><body><h1>Test</h1></body></html>","media_type":"any"}' \
  | python -m json.tool
```
