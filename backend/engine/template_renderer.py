"""
template_renderer.py — Renders a function's template.html using strings.json.

Each function folder ships a `template.html` file with placeholders like:

    {{ strings.by_id.calculate_total[0].text }}
    {{ strings.global_strings[0].text }}
    {{ config.function }}

The renderer loads `strings.json` + `config.json` from the function folder
and replaces every placeholder with the matching value. Missing placeholders
are left in place (so authors can see what's still unwired).

The template engine is intentionally minimal — no third-party dependencies —
but supports:
    * dot-path lookups        {{ a.b.c }}
    * [index] lookups         {{ a.b[0].c }}
    * {{#if var}}...{{/if}}   conditional blocks
    * {{#each list}}...{{/each}} loops with {{this}} and {{@index}}
"""
from __future__ import annotations

import json
import re
import html as html_lib
from pathlib import Path
from typing import Any, Optional


# --------------------------------------------------------------------------- #
# Tiny path resolver: supports a.b.c and a.b[0].c
# --------------------------------------------------------------------------- #
_PATH_TOKEN = re.compile(r"[^.\[\]]+|\[\d+\]")


def _resolve(obj: Any, path: str) -> Any:
    tokens = _PATH_TOKEN.findall(path)
    cur = obj
    for tok in tokens:
        if tok.startswith("[") and tok.endswith("]"):
            idx = int(tok[1:-1])
            if isinstance(cur, list) and 0 <= idx < len(cur):
                cur = cur[idx]
            else:
                return None
        else:
            if isinstance(cur, dict) and tok in cur:
                cur = cur[tok]
            else:
                return None
    return cur


# --------------------------------------------------------------------------- #
# Placeholder substitution
# --------------------------------------------------------------------------- #
_PLACEHOLDER = re.compile(r"\{\{\s*(?P<path>[^}]+?)\s*\}\}")


def _stringify(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, str):
        return html_lib.escape(value)
    if isinstance(value, (int, float, bool)):
        return str(value)
    return html_lib.escape(json.dumps(value, ensure_ascii=False, indent=2))


def _render_placeholders(template: str, ctx: dict) -> str:
    def repl(m: re.Match) -> str:
        path = m.group("path").strip()
        # Special token: this / @index handled by callers via ctx
        if path in ("this", "@index", "@key"):
            return _stringify(ctx.get(path))
        val = _resolve(ctx, path)
        return _stringify(val)
    return _PLACEHOLDER.sub(repl, template)


# --------------------------------------------------------------------------- #
# {{#if}}...{{/if}}
# --------------------------------------------------------------------------- _
_IF_BLOCK = re.compile(
    r"\{\{#if\s+(?P<cond>[^}]+?)\s*\}\}(?P<body>.*?)\{\{/if\}\}",
    re.DOTALL,
)


def _render_ifs(template: str, ctx: dict) -> str:
    def repl(m: re.Match) -> str:
        cond = m.group("cond").strip()
        val = _resolve(ctx, cond) if "." in cond or "[" in cond else ctx.get(cond)
        if val:
            return _render_block(m.group("body"), ctx)
        return ""
    prev = None
    cur = template
    while prev != cur:
        prev = cur
        cur = _IF_BLOCK.sub(repl, cur)
    return cur


# --------------------------------------------------------------------------- #
# {{#each list}}...{{/each}}
# --------------------------------------------------------------------------- #
_EACH_BLOCK = re.compile(
    r"\{\{#each\s+(?P<list>[^}]+?)\s*\}\}(?P<body>.*?)\{\{/each\}\}",
    re.DOTALL,
)


def _render_each(template: str, ctx: dict) -> str:
    def repl(m: re.Match) -> str:
        path = m.group("list").strip()
        lst = _resolve(ctx, path)
        if not isinstance(lst, list):
            return ""
        body = m.group("body")
        parts: list[str] = []
        for idx, item in enumerate(lst):
            sub_ctx = dict(ctx)
            sub_ctx["this"] = item
            sub_ctx["@index"] = idx
            parts.append(_render_block(body, sub_ctx))
        return "".join(parts)
    prev = None
    cur = template
    while prev != cur:
        prev = cur
        cur = _EACH_BLOCK.sub(repl, cur)
    return cur


def _render_block(template: str, ctx: dict) -> str:
    template = _render_each(template, ctx)
    template = _render_ifs(template, ctx)
    template = _render_placeholders(template, ctx)
    return template


# --------------------------------------------------------------------------- #
# Public API
# --------------------------------------------------------------------------- #
def render_template(template_str: str,
                    config: dict,
                    strings: dict,
                    extra: Optional[dict] = None) -> str:
    ctx = {
        "config": config,
        "strings": strings,
        "function": config.get("function", "unknown"),
        "version": config.get("version", "1.0.0"),
    }
    if extra:
        ctx.update(extra)
    return _render_block(template_str, ctx)


def render_function(function_dir: Path) -> str:
    """Load template.html + config.json + strings.json from a function folder
    and return the fully rendered HTML."""
    tpl_path = function_dir / "template.html"
    cfg_path = function_dir / "config.json"
    str_path = function_dir / "strings.json"

    if not tpl_path.exists():
        raise FileNotFoundError(f"template.html not found in {function_dir}")
    if not cfg_path.exists():
        raise FileNotFoundError(f"config.json not found in {function_dir}")
    if not str_path.exists():
        raise FileNotFoundError(f"strings.json not found in {function_dir}")

    template_str = tpl_path.read_text(encoding="utf-8")
    config = json.loads(cfg_path.read_text(encoding="utf-8"))
    strings = json.loads(str_path.read_text(encoding="utf-8"))

    return render_template(template_str, config, strings)


def render_to_file(function_dir: Path, out_path: Optional[Path] = None) -> Path:
    html = render_function(function_dir)
    if out_path is None:
        out_path = function_dir / "rendered.html"
    out_path.write_text(html, encoding="utf-8")
    return out_path


if __name__ == "__main__":
    import sys
    target = Path(sys.argv[1]) if len(sys.argv) > 1 else Path("functions/calculator")
    if not target.exists():
        print(f"Function folder not found: {target}")
        sys.exit(1)
    out = render_to_file(target)
    print(f"Rendered → {out}")
