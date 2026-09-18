"""
code_extractor.py — Walks source code and extracts every ID and every string.

This is the heart of the config.json / strings.json processors.

What it does:
    1.  Walks an entire function folder recursively.
    2.  For every source file (.py / .js / .ts / .java / .kt / .html / .css /
        .json / .xml / .gradle / .sh) it scans token-by-token.
    3.  Extracts identifiers (IDs) — variables, function names, class names,
        XML @+id/... entries, view IDs, etc. — and remembers the full
        surrounding code block (start → end) so nothing is truncated.
    4.  Extracts strings — quoted literals, XML text content, JSON values —
        in the exact order they appear, file by file, line by line.
    5.  Preserves the branching structure: if a function has sub-functions
        (e.g. a module with multiple methods), each branch is captured
        separately and the parent-child relationship is recorded.

Output shape (consumed by config_json_processor & strings_json_processor):

    {
      "files": [
        {
          "path": "handler.py",
          "language": "python",
          "lines": 142,
          "ids": [
            {"id": "calculate_total", "kind": "function",
             "line_start": 12, "line_end": 28,
             "code": "def calculate_total(...):\n    ...",
             "branch_of": null},
            ...
          ],
          "strings": [
            {"text": "Total amount", "line": 14, "id_at_line": "calculate_total"},
            ...
          ]
        }, ...
      ]
    }
"""
from __future__ import annotations

import re
import os
import json
from pathlib import Path
from dataclasses import dataclass, field, asdict
from typing import Optional, Iterator


# --------------------------------------------------------------------------- #
# Data classes
# --------------------------------------------------------------------------- #
@dataclass
class IdEntry:
    id: str
    kind: str                      # function | class | variable | view_id | const | import
    line_start: int
    line_end: int
    code: str
    file: str
    branch_of: Optional[str] = None   # parent function ID if this is a sub-branch
    children: list[str] = field(default_factory=list)


@dataclass
class StringEntry:
    text: str
    line: int
    file: str
    id_at_line: Optional[str] = None   # enclosing function/class ID


@dataclass
class FileExtraction:
    path: str
    language: str
    lines: int
    ids: list[IdEntry]
    strings: list[StringEntry]


# --------------------------------------------------------------------------- #
# Language detection
# --------------------------------------------------------------------------- #
_LANG_BY_EXT = {
    ".py":   "python",
    ".js":   "javascript",
    ".mjs":  "javascript",
    ".ts":   "typescript",
    ".jsx":  "javascript",
    ".tsx":  "typescript",
    ".java": "java",
    ".kt":   "kotlin",
    ".html": "html",
    ".htm":  "html",
    ".css":  "css",
    ".scss": "css",
    ".json": "json",
    ".xml":  "xml",
    ".gradle": "gradle",
    ".sh":   "shell",
    ".md":   "markdown",
}

_BINARY_EXT = {".png", ".jpg", ".jpeg", ".gif", ".webp", ".ico", ".svg",
               ".keystore", ".jks", ".class", ".dex", ".apk", ".zip", ".bin"}


def detect_language(path: Path) -> Optional[str]:
    return _LANG_BY_EXT.get(path.suffix.lower())


# --------------------------------------------------------------------------- #
# Patterns per language
# --------------------------------------------------------------------------- #
# Python: def / class / module-level variables
_PY_FUNC = re.compile(r"^(?P<indent>\s*)(?:async\s+def|def)\s+(?P<name>[A-Za-z_][A-Za-z0-9_]*)\s*\(")
_PY_CLASS = re.compile(r"^class\s+(?P<name>[A-Za-z_][A-Za-z0-9_]*)\s*[\(:]")
_PY_VAR = re.compile(r"^(?P<name>[A-Z_][A-Z0-9_]+)\s*=")
_PY_IMPORT = re.compile(r"^(?:from\s+\S+\s+)?import\s+(?P<name>[A-Za-z_][A-Za-z0-9_,\s*]+)")

# JS/TS: function / class / const NAME = / let NAME = / var NAME =
_JS_FUNC = re.compile(r"^(?:export\s+)?(?:async\s+)?function\s+(?P<name>[A-Za-z_$][A-Za-z0-9_$]*)\s*\(")
_JS_FUNC_ARROW = re.compile(r"^(?:export\s+)?(?:const|let|var)\s+(?P<name>[A-Za-z_$][A-Za-z0-9_$]*)\s*=\s*(?:async\s*)?\(?\s*[^=]*=>\s*")
_JS_CLASS = re.compile(r"^(?:export\s+)?class\s+(?P<name>[A-Za-z_$][A-Za-z0-9_$]*)")
_JS_CONST = re.compile(r"^(?:export\s+)?(?:const|let|var)\s+(?P<name>[A-Za-z_$][A-Za-z0-9_$]*)\s*=")

# Java/Kotlin
_JAVA_FUNC = re.compile(r"\b(?:public|private|protected|static|final|\s)*\s+(?P<ret>[A-Za-z_<>\[\]]+)\s+(?P<name>[A-Za-z_][A-Za-z0-9_]*)\s*\([^)]*\)\s*(?:\{|throws)")
_JAVA_CLASS = re.compile(r"^(?:public\s+|private\s+|final\s+|abstract\s+)*class\s+(?P<name>[A-Za-z_][A-Za-z0-9_]*)")
_KT_FUNC = re.compile(r"^(?:fun)\s+(?P<name>[A-Za-z_][A-Za-z0-9_]*)\s*\(")
_KT_CLASS = re.compile(r"^(?:class|object|interface)\s+(?P<name>[A-Za-z_][A-Za-z0-9_]*)")

# XML / HTML view IDs
_XML_ID = re.compile(r"@(?:\+)?id/(?P<id>[A-Za-z_][A-Za-z0-9_]*)")
_HTML_ID = re.compile(r"\bid\s*=\s*[\"'](?P<id>[A-Za-z_][A-Za-z0-9_\-]*)[\"']")

# String literals (works for most languages)
_STR_DQ = re.compile(r'"(?P<text>(?:\\.|[^"\\])*)"')
_STR_SQ = re.compile(r"'(?P<text>(?:\\.|[^'\\])*)'")
# XML text content (between > and <)
_XML_TEXT = re.compile(r">(?P<text>[^<>]+)<")
# HTML text content
_HTML_TEXT = re.compile(r">(?P<text>[^<>]+)<")
# JSON key:value string
_JSON_STR_VAL = re.compile(r":\s*\"(?P<text>(?:\\.|[^\"\\])*)\"")
_JSON_STR_KEY = re.compile(r"\"(?P<text>[A-Za-z_][A-Za-z0-9_]*)\"\s*:")

# Comments
_PY_COMMENT = re.compile(r"#(.*)$")
_JS_COMMENT_LINE = re.compile(r"//(.*)$")
_HTML_COMMENT = re.compile(r"<!--(.*?)-->", re.DOTALL)
_CSS_COMMENT = re.compile(r"/\*.*?\*/", re.DOTALL)


# --------------------------------------------------------------------------- #
# Extractors
# --------------------------------------------------------------------------- #
def _strip_py_comments(code: str) -> str:
    out = []
    for line in code.splitlines():
        in_str = False
        quote = ""
        cleaned = []
        i = 0
        while i < len(line):
            ch = line[i]
            if in_str:
                cleaned.append(ch)
                if ch == "\\" and i + 1 < len(line):
                    cleaned.append(line[i + 1])
                    i += 2
                    continue
                if ch == quote:
                    in_str = False
            else:
                if ch in ('"', "'"):
                    in_str = True
                    quote = ch
                    cleaned.append(ch)
                elif ch == "#":
                    break
                else:
                    cleaned.append(ch)
            i += 1
        out.append("".join(cleaned))
    return "\n".join(out)


def _strip_js_comments(code: str) -> str:
    # Remove block comments first
    code = _CSS_COMMENT.sub("", code)
    out = []
    for line in code.splitlines():
        in_str = False
        quote = ""
        cleaned = []
        i = 0
        while i < len(line):
            ch = line[i]
            if in_str:
                cleaned.append(ch)
                if ch == "\\" and i + 1 < len(line):
                    cleaned.append(line[i + 1])
                    i += 2
                    continue
                if ch == quote:
                    in_str = False
            else:
                if ch in ('"', "'", "`"):
                    in_str = True
                    quote = ch
                    cleaned.append(ch)
                elif ch == "/" and i + 1 < len(line) and line[i + 1] == "/":
                    break
                else:
                    cleaned.append(ch)
            i += 1
        out.append("".join(cleaned))
    return "\n".join(out)


def _strip_html_comments(code: str) -> str:
    return _HTML_COMMENT.sub("", code)


def _find_block_end(lines: list[str], start: int, indent: str) -> int:
    """Return the last line index (inclusive) of a Python block.

    A block ends when a non-empty line appears at indent level <= `indent`.
    """
    i = start + 1
    while i < len(lines):
        ln = lines[i]
        if ln.strip() == "":
            i += 1
            continue
        # Compare indentation
        curr_indent = ln[:len(ln) - len(ln.lstrip())]
        if len(curr_indent) <= len(indent) and not ln.lstrip().startswith((")", "]", "}", "elif", "else", "except", "finally")):
            return i - 1
        i += 1
    return len(lines) - 1


def _find_brace_block(lines: list[str], start: int) -> int:
    """Return the last line index of a `{ ... }` block starting near `start`."""
    depth = 0
    started = False
    for i in range(start, len(lines)):
        for ch in lines[i]:
            if ch == "{":
                depth += 1
                started = True
            elif ch == "}":
                depth -= 1
                if started and depth == 0:
                    return i
    return len(lines) - 1


def _extract_strings_from_line(line: str, language: str) -> list[str]:
    strings: list[str] = []
    if language in ("html", "xml"):
        for m in _XML_TEXT.finditer(line):
            txt = m.group("text").strip()
            if txt and not txt.startswith("<?") and not txt.startswith("<!"):
                strings.append(txt)
    elif language == "json":
        for m in _JSON_STR_VAL.finditer(line):
            strings.append(m.group("text"))
    else:
        # Use double-quoted and single-quoted, skip empty & single chars
        for m in _STR_DQ.finditer(line):
            txt = m.group("text")
            if len(txt) >= 2:
                strings.append(txt)
        for m in _STR_SQ.finditer(line):
            txt = m.group("text")
            if len(txt) >= 2:
                strings.append(txt)
    return strings


def extract_file(path: Path, root: Path) -> Optional[FileExtraction]:
    """Extract every ID and string from a single source file."""
    lang = detect_language(path)
    if lang is None:
        return None

    try:
        raw = path.read_text(encoding="utf-8", errors="replace")
    except Exception:
        return None

    lines = raw.splitlines()
    ids: list[IdEntry] = []
    strings: list[StringEntry] = []

    rel_path = str(path.relative_to(root)).replace("\\", "/")

    if lang == "python":
        cleaned = _strip_py_comments(raw)
        c_lines = cleaned.splitlines()
        current_parent: Optional[str] = None
        parent_indent = ""
        for i, line in enumerate(c_lines):
            stripped = line.lstrip()
            indent = line[:len(line) - len(stripped)]
            # Exit parent if indentation dropped
            if current_parent and len(indent) <= len(parent_indent) and stripped:
                current_parent = None

            m = _PY_FUNC.match(line)
            if m:
                name = m.group("name")
                end = _find_block_end(c_lines, i, indent)
                code_block = "\n".join(lines[i:end + 1])
                entry = IdEntry(
                    id=name, kind="function",
                    line_start=i + 1, line_end=end + 1,
                    code=code_block, file=rel_path,
                    branch_of=current_parent,
                )
                if current_parent:
                    for parent in ids:
                        if parent.id == current_parent and parent.file == rel_path:
                            parent.children.append(name)
                            break
                ids.append(entry)
                current_parent = name
                parent_indent = indent
                # Strings inside this function
                for j in range(i, end + 1):
                    for s in _extract_strings_from_line(c_lines[j], "python"):
                        strings.append(StringEntry(text=s, line=j + 1, file=rel_path, id_at_line=name))
                continue

            m = _PY_CLASS.match(line)
            if m:
                name = m.group("name")
                end = _find_block_end(c_lines, i, indent)
                code_block = "\n".join(lines[i:end + 1])
                entry = IdEntry(
                    id=name, kind="class",
                    line_start=i + 1, line_end=end + 1,
                    code=code_block, file=rel_path,
                    branch_of=None,
                )
                ids.append(entry)
                current_parent = name
                parent_indent = indent
                for j in range(i, end + 1):
                    for s in _extract_strings_from_line(c_lines[j], "python"):
                        strings.append(StringEntry(text=s, line=j + 1, file=rel_path, id_at_line=name))
                continue

            m = _PY_VAR.match(line)
            if m:
                name = m.group("name")
                ids.append(IdEntry(
                    id=name, kind="const",
                    line_start=i + 1, line_end=i + 1,
                    code=line, file=rel_path, branch_of=current_parent,
                ))

            # Standalone strings (not inside a function we already captured)
            for s in _extract_strings_from_line(line, "python"):
                strings.append(StringEntry(text=s, line=i + 1, file=rel_path, id_at_line=current_parent))

    elif lang in ("javascript", "typescript"):
        cleaned = _strip_js_comments(raw)
        c_lines = cleaned.splitlines()
        for i, line in enumerate(c_lines):
            m = _JS_FUNC.match(line) or _JS_FUNC_ARROW.match(line)
            if m:
                name = m.group("name")
                end = _find_brace_block(c_lines, i)
                code_block = "\n".join(lines[i:end + 1])
                ids.append(IdEntry(
                    id=name, kind="function",
                    line_start=i + 1, line_end=end + 1,
                    code=code_block, file=rel_path,
                ))
                for j in range(i, end + 1):
                    for s in _extract_strings_from_line(c_lines[j], lang):
                        strings.append(StringEntry(text=s, line=j + 1, file=rel_path, id_at_line=name))
                continue

            m = _JS_CLASS.match(line)
            if m:
                name = m.group("name")
                end = _find_brace_block(c_lines, i)
                code_block = "\n".join(lines[i:end + 1])
                ids.append(IdEntry(
                    id=name, kind="class",
                    line_start=i + 1, line_end=end + 1,
                    code=code_block, file=rel_path,
                ))
                for j in range(i, end + 1):
                    for s in _extract_strings_from_line(c_lines[j], lang):
                        strings.append(StringEntry(text=s, line=j + 1, file=rel_path, id_at_line=name))
                continue

            m = _JS_CONST.match(line)
            if m:
                name = m.group("name")
                ids.append(IdEntry(
                    id=name, kind="const",
                    line_start=i + 1, line_end=i + 1,
                    code=line, file=rel_path,
                ))

            for s in _extract_strings_from_line(line, lang):
                strings.append(StringEntry(text=s, line=i + 1, file=rel_path))

    elif lang in ("java", "kotlin"):
        c_lines = raw.splitlines()
        for i, line in enumerate(c_lines):
            cls_pat = _KT_CLASS if lang == "kotlin" else _JAVA_CLASS
            fn_pat = _KT_FUNC if lang == "kotlin" else _JAVA_FUNC
            m = cls_pat.match(line)
            if m:
                name = m.group("name")
                end = _find_brace_block(c_lines, i)
                code_block = "\n".join(lines[i:end + 1])
                ids.append(IdEntry(
                    id=name, kind="class",
                    line_start=i + 1, line_end=end + 1,
                    code=code_block, file=rel_path,
                ))
                for j in range(i, end + 1):
                    for s in _extract_strings_from_line(c_lines[j], lang):
                        strings.append(StringEntry(text=s, line=j + 1, file=rel_path, id_at_line=name))
                continue

            m = fn_pat.match(line) or fn_pat.search(line)
            if m:
                name = m.group("name")
                end = _find_brace_block(c_lines, i)
                code_block = "\n".join(lines[i:end + 1])
                ids.append(IdEntry(
                    id=name, kind="function",
                    line_start=i + 1, line_end=end + 1,
                    code=code_block, file=rel_path,
                ))
                for j in range(i, end + 1):
                    for s in _extract_strings_from_line(c_lines[j], lang):
                        strings.append(StringEntry(text=s, line=j + 1, file=rel_path, id_at_line=name))

    elif lang in ("html", "xml"):
        cleaned = _strip_html_comments(raw)
        c_lines = cleaned.splitlines()
        # Collect all id= attributes
        id_pat = _HTML_ID if lang == "html" else _XML_ID
        for i, line in enumerate(c_lines):
            for m in id_pat.finditer(line):
                name = m.group("id")
                ids.append(IdEntry(
                    id=name, kind="view_id",
                    line_start=i + 1, line_end=i + 1,
                    code=line, file=rel_path,
                ))
            for s in _extract_strings_from_line(line, lang):
                if s.strip():
                    strings.append(StringEntry(text=s, line=i + 1, file=rel_path))

    elif lang == "css":
        # Extract selectors and rule blocks
        rule_pat = re.compile(r"^([.#]?[A-Za-z_][A-Za-z0-9_\-:,\s.]*)\s*\{")
        for i, line in enumerate(raw.splitlines()):
            m = rule_pat.match(line)
            if m:
                selector = m.group(1).strip()
                end = _find_brace_block(raw.splitlines(), i)
                code_block = "\n".join(lines[i:end + 1])
                ids.append(IdEntry(
                    id=selector, kind="css_rule",
                    line_start=i + 1, line_end=end + 1,
                    code=code_block, file=rel_path,
                ))
            for s in _extract_strings_from_line(line, "css"):
                if s.strip():
                    strings.append(StringEntry(text=s, line=i + 1, file=rel_path))

    elif lang == "json":
        try:
            data = json.loads(raw)
        except Exception:
            data = {}
        # Walk JSON, every key is an "id"
        def _walk(obj, prefix=""):
            if isinstance(obj, dict):
                for k, v in obj.items():
                    full_id = f"{prefix}.{k}" if prefix else k
                    ids.append(IdEntry(
                        id=full_id, kind="json_key",
                        line_start=1, line_end=1,
                        code=json.dumps({k: v}, ensure_ascii=False, indent=2),
                        file=rel_path,
                    ))
                    if isinstance(v, str):
                        strings.append(StringEntry(text=v, line=1, file=rel_path, id_at_line=full_id))
                    else:
                        _walk(v, full_id)
            elif isinstance(obj, list):
                for idx, item in enumerate(obj):
                    _walk(item, f"{prefix}[{idx}]")
        _walk(data)

    elif lang == "gradle":
        for i, line in enumerate(raw.splitlines()):
            m = re.match(r"^\s*(?P<name>[a-zA-Z_][a-zA-Z0-9_]*)\s*(?:\(|=|\{)", line)
            if m:
                name = m.group("name")
                ids.append(IdEntry(
                    id=name, kind="gradle_call",
                    line_start=i + 1, line_end=i + 1,
                    code=line, file=rel_path,
                ))
            for s in _extract_strings_from_line(line, "gradle"):
                strings.append(StringEntry(text=s, line=i + 1, file=rel_path))

    elif lang == "shell":
        for i, line in enumerate(raw.splitlines()):
            m = re.match(r"^(?:function\s+)?([a-zA-Z_][a-zA-Z0-9_]*)\s*\(\)", line)
            if m:
                name = m.group(1)
                end = i
                for j in range(i + 1, len(lines)):
                    if lines[j].startswith("}") or (lines[j].strip() and not lines[j].startswith(" ") and not lines[j].startswith("\t")):
                        end = j - 1
                        break
                else:
                    end = len(lines) - 1
                ids.append(IdEntry(
                    id=name, kind="function",
                    line_start=i + 1, line_end=end + 1,
                    code="\n".join(lines[i:end + 1]), file=rel_path,
                ))
            for s in _extract_strings_from_line(line, "shell"):
                strings.append(StringEntry(text=s, line=i + 1, file=rel_path))

    return FileExtraction(
        path=rel_path,
        language=lang,
        lines=len(lines),
        ids=ids,
        strings=strings,
    )


# --------------------------------------------------------------------------- #
# Folder walker
# --------------------------------------------------------------------------- #
SKIP_DIRS = {"__pycache__", ".git", "node_modules", ".venv", "venv",
             "build", ".gradle", ".idea", "_builds", "_output", "self_test_output"}


def iter_source_files(root: Path) -> Iterator[Path]:
    for dirpath, dirnames, filenames in os.walk(root):
        dirnames[:] = [d for d in dirnames if d not in SKIP_DIRS and not d.startswith(".")]
        for fn in filenames:
            p = Path(dirpath) / fn
            if p.suffix.lower() in _BINARY_EXT:
                continue
            if detect_language(p) is None:
                continue
            yield p


def extract_folder(root: Path) -> list[FileExtraction]:
    """Extract every ID and every string from every source file under `root`."""
    results: list[FileExtraction] = []
    for path in iter_source_files(root):
        fe = extract_file(path, root)
        if fe is not None:
            results.append(fe)
    # Sort by path for stable output
    results.sort(key=lambda f: f.path)
    return results


def to_dict(extractions: list[FileExtraction]) -> dict:
    return {
        "files": [
            {
                "path": fe.path,
                "language": fe.language,
                "lines": fe.lines,
                "ids": [asdict(i) for i in fe.ids],
                "strings": [asdict(s) for s in fe.strings],
            }
            for fe in extractions
        ]
    }
