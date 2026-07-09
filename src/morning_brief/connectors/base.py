"""Connector contract + a small self-test helper."""
from __future__ import annotations

from dataclasses import dataclass


@dataclass
class ConnectorStatus:
    name: str
    ok: bool
    detail: str = ""

    def __str__(self) -> str:
        mark = "✓" if self.ok else "✗"
        return f"  {mark} {self.name}: {self.detail}"
