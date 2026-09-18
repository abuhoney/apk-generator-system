"""
BardomPro APK Generator — Engine Package

Modular engine that drives the universal APK generation pipeline.

Submodules:
    config                   — Loads .env credentials and runtime config
    function_registry        — Discovers and registers every function folder
    config_json_processor   — Builds config.json (all IDs + full code per function)
    strings_json_processor   — Builds strings.json (all strings per ID, ordered)
    template_renderer        — Renders template.html using strings.json
    project_generator        — Generates a full Android project tree per function
    apk_builder             — Drives aapt2 → javac → d8 → apksigner pipeline
    code_extractor          — Walks source code, extracts IDs, strings, branches
    self_test               — End-to-end self-test runner
"""

__version__ = "5.0.0"
__all__ = [
    "config",
    "function_registry",
    "config_json_processor",
    "strings_json_processor",
    "template_renderer",
    "project_generator",
    "apk_builder",
    "code_extractor",
    "self_test",
]
