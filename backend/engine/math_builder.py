"""
math_builder.py — Evaluates formula expressions from the source data
and generates computed field definitions.

Handles formulas like:
  total_bill = service_cost * (1 + vat_rate)
  bmi = weight / pow(height/100, 2)
  stay_days = DATEDIFF(discharge_date, admission_date)
"""
import json, re
from pathlib import Path

def build(config: dict, strings: dict, function_dir: Path, source_data: dict = None) -> dict:
    formulas = {}
    
    # Try to extract formulas from source data
    if source_data and isinstance(source_data, dict) and "formulas" in source_data:
        formulas = source_data["formulas"]
    
    computed_fields = []
    for name, expr in formulas.items():
        # Sanitize the expression for JS
        js_expr = expr
        js_expr = js_expr.replace("DATEDIFF(", "__datediff(")
        js_expr = js_expr.replace("pow(", "Math.pow(")
        js_expr = js_expr.replace("log(", "Math.log(")
        
        computed_fields.append({
            "name": name,
            "original_expr": expr,
            "js_expr": js_expr,
            "depends_on": re.findall(r'[a-z_][a-z0-9_]*', expr.lower()),
        })
    
    manifest = {"formulas": computed_fields}
    (function_dir / "_math_manifest.json").write_text(
        json.dumps(manifest, indent=2, ensure_ascii=False), encoding="utf-8")
    
    print(f"[math_builder] {len(computed_fields)} formulas", flush=True)
    return manifest
