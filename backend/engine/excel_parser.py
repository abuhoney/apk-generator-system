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


def parse_pdf_file(file_path):
    """Extract text from PDF file and return as datasets."""
    datasets = []
    try:
        # Try pdfplumber first (better table extraction)
        import pdfplumber
        with pdfplumber.open(str(file_path)) as pdf:
            for page_num, page in enumerate(pdf.pages):
                tables = page.extract_tables()
                if tables:
                    for table_idx, table in enumerate(tables):
                        if len(table) < 2:
                            continue
                        headers = [str(h).strip() if h else f"col_{i}" for i, h in enumerate(table[0])]
                        items = []
                        for row in table[1:]:
                            item = {}
                            for i, val in enumerate(row):
                                if i < len(headers):
                                    item[headers[i]] = str(val).strip() if val else ""
                            if any(v for v in item.values()):
                                items.append(item)
                        if items:
                            datasets.append({"name": f"Page{page_num+1}_Table{table_idx+1}", "items": items})
                            continue
                
                # If no tables, extract text as paragraphs
                text = page.extract_text()
                if text:
                    paragraphs = [p.strip() for p in text.split("\n\n") if p.strip()]
                    if paragraphs:
                        items = [{"paragraph": p[:500], "page": page_num+1} for p in paragraphs]
                        datasets.append({"name": f"Page{page_num+1}_Text", "items": items})
    except ImportError:
        # Fallback: PyPDF2
        try:
            import PyPDF2
            with open(file_path, "rb") as f:
                reader = PyPDF2.PdfReader(f)
                items = []
                for page_num, page in enumerate(reader.pages):
                    text = page.extract_text()
                    if text:
                        for para in text.split("\n\n"):
                            para = para.strip()
                            if para:
                                items.append({"paragraph": para[:500], "page": page_num+1})
                if items:
                    datasets.append({"name": "PDF Content", "items": items})
        except ImportError:
            print("[excel_parser] no PDF library available (pdfplumber/PyPDF2)", flush=True)
    except Exception as e:
        print(f"[excel_parser] PDF parse error: {e}", flush=True)
    return datasets


def parse_docx_file(file_path):
    """Extract text + tables from Word .docx file and return as datasets."""
    datasets = []
    try:
        from docx import Document as DocxDocument
        
        doc = DocxDocument(str(file_path))
        
        # Extract tables
        for table_idx, table in enumerate(doc.tables):
            if len(table.rows) < 2:
                continue
            headers = [cell.text.strip() for cell in table.rows[0].cells]
            items = []
            for row in table.rows[1:]:
                item = {}
                for i, cell in enumerate(row.cells):
                    if i < len(headers):
                        item[headers[i]] = cell.text.strip()
                if any(v for v in item.values()):
                    items.append(item)
            if items:
                datasets.append({"name": f"Table{table_idx+1}", "items": items})
        
        # Extract paragraphs (non-empty, non-heading)
        paragraphs = []
        for para in doc.paragraphs:
            text = para.text.strip()
            if text and para.style.name not in ("Heading 1", "Heading 2", "Heading 3", "Title"):
                paragraphs.append({"paragraph": text[:500]})
        
        if paragraphs:
            datasets.append({"name": "Document Text", "items": paragraphs})
        
        # Extract headings as structure
        headings = []
        for para in doc.paragraphs:
            if para.style.name in ("Heading 1", "Heading 2", "Heading 3", "Title"):
                headings.append({
                    "heading": para.text.strip(),
                    "level": para.style.name.replace("Heading ", "").replace("Title", "0"),
                })
        if headings:
            datasets.append({"name": "Headings", "items": headings})
            
    except ImportError:
        print("[excel_parser] python-docx not available for .docx parsing", flush=True)
    except Exception as e:
        print(f"[excel_parser] DOCX parse error: {e}", flush=True)
    return datasets


def parse_any_file(file_path):
    """Master parser: detects file type and calls the appropriate parser."""
    ext = file_path.suffix.lower()
    if ext in (".xlsx", ".xls"):
        return parse_excel_file(file_path)
    elif ext == ".pdf":
        return parse_pdf_file(file_path)
    elif ext == ".docx":
        return parse_docx_file(file_path)
    elif ext == ".json":
        import json
        try:
            data = json.loads(file_path.read_text(encoding="utf-8"))
            from engine.data_analyzer import _detect_datasets
            return _detect_datasets(data, file_path.name)
        except: return []
    elif ext == ".csv":
        return _parse_csv_to_datasets(file_path)
    elif ext == ".txt":
        return _parse_txt_to_datasets(file_path)
    elif ext in (".html", ".htm"):
        content = file_path.read_text(encoding="utf-8")
        return [{"name": file_path.stem, "items": [{"content": content[:5000], "type": "html"}]}]
    return []


def _parse_csv_to_datasets(file_path):
    """Parse CSV file into datasets."""
    text = file_path.read_text(encoding="utf-8")
    lines = text.strip().split("\n")
    if len(lines) < 2:
        return []
    headers = [h.strip() for h in lines[0].split(",")]
    items = []
    for line in lines[1:]:
        vals = line.split(",")
        item = {}
        for i, h in enumerate(headers):
            v = vals[i].strip() if i < len(vals) else ""
            try: v = int(v)
            except ValueError:
                try: v = float(v)
                except ValueError: pass
            item[h] = v
        items.append(item)
    return [{"name": file_path.stem, "items": items}]


def _parse_txt_to_datasets(file_path):
    """Parse TXT file into datasets (key: value format or plain lines)."""
    text = file_path.read_text(encoding="utf-8")
    items = []
    for line in text.strip().split("\n"):
        line = line.strip()
        if not line:
            continue
        if ":" in line:
            k, v = line.split(":", 1)
            items.append({"name": k.strip(), "value": v.strip()})
        else:
            items.append({"name": line})
    return [{"name": file_path.stem, "items": items}]
