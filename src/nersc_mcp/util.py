"""Structured result envelope (DESIGN.md invariant I6).

Every tool returns result(...) — never a bare string, never a traceback.
"""

from __future__ import annotations

from typing import Any, Optional


def result(
    ok: bool,
    data: Any = None,
    warnings: Optional[list] = None,
    hints: Optional[list] = None,
    error: Optional[dict] = None,
) -> dict:
    out: dict = {"ok": ok, "data": data, "warnings": warnings or [], "hints": hints or []}
    if error is not None:
        out["error"] = error
    return out


def err(kind: str, message: str, raw: str = "") -> dict:
    return result(False, error={"kind": kind, "message": message, "raw": raw})
