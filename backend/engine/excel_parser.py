"""
excel_parser.py — Parse Excel (.xlsx/.xls) files into datasets.

Uses openpyxl to read Excel workbooks. Each sheet becomes a dataset.
The first row is treated as headers (field names).

Output: list of {name, items} where items is a list of dicts.
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any


def parse_excel_file(file_path: Path) -> list:
    """Parse an Excel file and return datasets (one per sheet).
    
    Returns: [{"name": "Sheet1", "items": [{...}, ...]}, ...]
    """
    try:
        from openpyxl import load_workbook
    except ImportError:
        print("[excel_parser] openpyxl not installed — trying xlrd fallback", flush=True)
        try:
            import xlrd
            return _parse_xls(file_path)
        except ImportError:
            print("[excel_parser] ERROR: neither openpyxl nor xlrd available", flush=True)
            return []

    datasets = []
    try:
        wb = load_workbook(file_path, read_only=True, data_only=True)
        for sheet_name in wb.sheetnames:
            ws = wb[sheet_name]
            rows = list(ws.iter_rows(values_only=True))
            if len(rows) < 2:
                continue
            headers = [str(h).strip() if h else f"col_{i}" for i, h in enumerate(rows[0])]
            items = []
            for row in rows[1:]:
                item = {}
                for i, val in enumerate(row):
                    if i >= len(headers):
                        break
                    if val is None:
                        item[headers[i]] = ""
                    elif isinstance(val, float) and val == int(val):
                        item[headers[i]] = int(val)
                    else:
                        item[headers[i]] = str(val) if not isinstance(val, (int, float, bool)) else val
                if any(v != "" for v in item.values()):
                    items.append(item)
            if items:
                datasets.append({"name": sheet_name, "items": items})
        wb.close()
    except Exception as e:
        print(f"[excel_parser] error parsing {file_path.name}: {e}", flush=True)
    
    return datasets


def _parse_xls(file_path: Path) -> list:
    """Fallback parser for old .xls format using xlrd."""
    import xlrd
    datasets = []
    try:
        book = xlrd.open_workbook(str(file_path))
        for sheet_name in book.sheet_names():
            sheet = book.sheet_by_name(sheet_name)
            if sheet.nrows < 2:
                continue
            headers = [str(sheet.cell_value(0, c)).strip() for c in range(sheet.ncols)]
            items = []
            for r in range(1, sheet.nrows):
                item = {}
                for c in range(sheet.ncols):
                    if c < len(headers):
                        val = sheet.cell_value(r, c)
                        if isinstance(val, float) and val == int(val):
                            val = int(val)
                        item[headers[c]] = val
                if any(v != "" for v in item.values()):
                    items.append(item)
            if items:
                datasets.append({"name": sheet_name, "items": items})
    except Exception as e:
        print(f"[excel_parser] xlrd error: {e}", flush=True)
    return datasets


if __name__ == "__main__":
    import sys
    if len(sys.argv) > 1:
        result = parse_excel_file(Path(sys.argv[1]))
        for ds in result:
            print(f"Sheet: {ds['name']} ({len(ds['items'])} items)")
            if ds['items']:
                print(f"  Fields: {list(ds['items'][0].keys())}")
