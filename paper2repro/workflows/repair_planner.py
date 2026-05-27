from __future__ import annotations

from typing import Any


def build_repair_prompt(quality_result: dict[str, Any]) -> str:
    empty_files = quality_result.get("empty_python_files", []) or []
    missing_imports = quality_result.get("missing_local_imports", []) or []
    syntax_errors = quality_result.get("syntax_errors", []) or []
    missing_advertised_files = (
        quality_result.get("missing_advertised_files", []) or []
    )
    empty_advertised_files = quality_result.get("empty_advertised_files", []) or []
    source_roots = quality_result.get("source_roots", []) or []
    failures = quality_result.get("failures", []) or []
    smoke = quality_result.get("smoke", {}) or {}
    validation = quality_result.get("validation", {}) or {}
    reproduction_gate = quality_result.get("reproduction_gate", {}) or {}

    lines = [
        "Repair the generated code so the deterministic quality gate passes.",
        "Rules:",
        "- Keep one single project root. Do not maintain duplicate src trees.",
        "- Implement empty Python files with real runnable code, not placeholders.",
        "- Add missing local modules or correct imports to existing modules.",
        "- Keep README commands aligned with actual files.",
        "",
        "Quality failures:",
    ]
    lines.extend(f"- {failure}" for failure in failures)
    if empty_files:
        lines.append("")
        lines.append("Empty Python implementation files to fill:")
        lines.extend(f"- {path}" for path in empty_files)
    if missing_imports:
        lines.append("")
        lines.append("Missing local imports to resolve:")
        lines.extend(
            f"- {item['file']} imports {item['module']}"
            for item in missing_imports
        )
    if syntax_errors:
        lines.append("")
        lines.append("Python syntax errors to fix:")
        lines.extend(
            f"- {item['file']}: {item['error']}"
            for item in syntax_errors
        )
    if missing_advertised_files:
        lines.append("")
        lines.append("Advertised files missing from generated code:")
        lines.extend(f"- {path}" for path in missing_advertised_files)
    if empty_advertised_files:
        lines.append("")
        lines.append("Advertised files that are empty:")
        lines.extend(f"- {path}" for path in empty_advertised_files)
    if len(source_roots) > 1:
        lines.append("")
        lines.append("Project root conflict:")
        lines.append(
            f"- Found {', '.join(source_roots)}; converge to a single project root."
        )
    if str(smoke.get("status", "")).lower() == "error":
        lines.append("")
        lines.append("Smoke check failures to fix:")
        for check in smoke.get("checks", []) or []:
            if check.get("status") != "error":
                continue
            command = " ".join(str(part) for part in check.get("command", []) or [])
            stderr = (check.get("stderr") or check.get("stdout") or "").strip()
            if command:
                lines.append(f"- Command `{command}` failed")
            if stderr:
                lines.append(f"  Error: {stderr[:1000]}")
    if str(validation.get("status", "")).lower() in {"error", "partial", "failed"}:
        lines.append("")
        lines.append("Validation failures to fix:")
        reason = validation.get("reason")
        raw_output = validation.get("raw_output")
        if reason:
            lines.append(f"- Reason: {reason}")
        if raw_output:
            lines.append(f"- Pytest output: {str(raw_output).strip()[:1500]}")
    if reproduction_gate:
        lines.append("")
        lines.append("Reproduction gate failures to fix:")
        for check in reproduction_gate.get("checks", []) or []:
            if check.get("status") == "success":
                continue
            lines.append(f"- Check: {check.get('name', 'unknown')}")
            for failure in check.get("failures", []) or []:
                lines.append(f"  Failure: {failure}")
            stderr = check.get("stderr")
            stdout = check.get("stdout")
            if stderr:
                lines.append(f"  Stderr: {str(stderr).strip()[:1000]}")
            if stdout:
                lines.append(f"  Stdout: {str(stdout).strip()[:1000]}")
    type_check_gate = quality_result.get("type_check_gate") or {}
    if (
        str(type_check_gate.get("status", "")).lower() == "errors"
        and type_check_gate.get("rendered_prompt")
    ):
        lines.append("")
        lines.append(type_check_gate["rendered_prompt"])
    return "\n".join(lines)
