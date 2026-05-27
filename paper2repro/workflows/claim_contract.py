from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any


_IMPLEMENT_RE = re.compile(r"\bimplement\s+([a-zA-Z_][a-zA-Z0-9_]*)", re.IGNORECASE)
_REQUIRED_API_RE = re.compile(r"^\s*-\s*([a-zA-Z_][a-zA-Z0-9_]*)\s*$")
_LIMITATION_RE = re.compile(r"(?:risk|limitation):\s*(.+)", re.IGNORECASE)
_CLAIM_KEYWORDS = (
    "reward",
    "rollout",
    "retrieval",
    "inference",
    "evaluation",
    "metric",
    "dataset",
    "skill",
    "reflection",
    "dedup",
)


@dataclass(frozen=True)
class ClaimRequirement:
    claim_id: str
    description: str
    required_symbols: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "claim_id": self.claim_id,
            "description": self.description,
            "required_symbols": self.required_symbols,
        }


@dataclass(frozen=True)
class ClaimContract:
    claims: list[ClaimRequirement]
    required_symbols: list[str]
    limitations: list[str]

    def to_dict(self) -> dict[str, Any]:
        return {
            "claims": [claim.to_dict() for claim in self.claims],
            "required_symbols": self.required_symbols,
            "limitations": self.limitations,
        }

    def to_prompt_block(self) -> str:
        lines = ["# PAPER CLAIM CONTRACT", "Implement these required symbols:"]
        for symbol in self.required_symbols:
            lines.append(f"- `{symbol}`")
        lines.append("Claim requirements:")
        for claim in self.claims:
            lines.append(f"- {claim.claim_id}: {claim.description}")
        if self.limitations:
            lines.append("Known limitations to state honestly:")
            for limitation in self.limitations:
                lines.append(f"- {limitation}")
        return "\n".join(lines)


def build_claim_contract(plan_text: str, critique_text: str = "") -> ClaimContract:
    required_symbols = _extract_required_symbols(plan_text)
    return ClaimContract(
        claims=_extract_claims(plan_text, required_symbols),
        required_symbols=required_symbols,
        limitations=_extract_limitations(critique_text),
    )


def _extract_required_symbols(plan_text: str) -> list[str]:
    symbols: set[str] = set(_IMPLEMENT_RE.findall(plan_text or ""))
    in_required_api = False

    for line in (plan_text or "").splitlines():
        stripped = line.strip()
        if stripped.endswith(":") and "required_api" in stripped:
            in_required_api = True
            continue
        if not in_required_api:
            continue
        if stripped and not stripped.startswith("-"):
            in_required_api = False
            continue
        match = _REQUIRED_API_RE.match(line)
        if match:
            symbols.add(match.group(1))

    return sorted(symbols)


def _extract_claims(plan_text: str, required_symbols: list[str]) -> list[ClaimRequirement]:
    claims: list[ClaimRequirement] = []
    for line in (plan_text or "").splitlines():
        stripped = line.strip(" -")
        if not stripped:
            continue
        lowered = stripped.lower()
        if not any(keyword in lowered for keyword in _CLAIM_KEYWORDS):
            continue
        line_symbols = [symbol for symbol in required_symbols if symbol in stripped]
        claims.append(
            ClaimRequirement(
                claim_id=f"claim_{len(claims) + 1}",
                description=stripped,
                required_symbols=line_symbols,
            )
        )

    if not claims and required_symbols:
        claims.append(
            ClaimRequirement(
                claim_id="claim_1",
                description="Implement required paper APIs with runnable behavior.",
                required_symbols=required_symbols,
            )
        )

    return claims


def _extract_limitations(critique_text: str) -> list[str]:
    return sorted(
        {
            match.group(1).strip().rstrip(".")
            for match in _LIMITATION_RE.finditer(critique_text or "")
            if match.group(1).strip()
        }
    )
