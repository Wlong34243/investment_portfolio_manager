"""Decision record schema — field names are the contract (see doc 07 + Amendment A)."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Optional


@dataclass
class ConditionLeg:
    metric: str
    comparator: str
    value: Any

    def to_dict(self) -> dict[str, Any]:
        return {"metric": self.metric, "comparator": self.comparator, "value": self.value}

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> ConditionLeg:
        return cls(
            metric=str(d.get("metric", "")),
            comparator=str(d.get("comparator", "")),
            value=d.get("value"),
        )


@dataclass
class Conditions:
    operator: str  # all | any
    legs: list[ConditionLeg] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "operator": self.operator,
            "legs": [leg.to_dict() for leg in self.legs],
        }

    @classmethod
    def from_dict(cls, d: dict[str, Any] | None) -> Conditions:
        if not d:
            return cls(operator="all", legs=[])
        legs = [ConditionLeg.from_dict(x) for x in (d.get("legs") or [])]
        return cls(operator=str(d.get("operator") or "all"), legs=legs)


@dataclass
class DecisionRecord:
    id: str
    decided_on: Optional[str]
    decided_on_status: str  # known | unknown
    scope: str  # position | portfolio
    tickers: list[str]
    assertion: str  # verbatim source text only
    conditions: Conditions
    unencodable_conditions: list[str]
    overrides: list[str]
    falsifier: str
    supersedes: Optional[str]
    provenance: str  # extracted | authored_at_desk
    source_ref: str
    status: str  # proposed | ratified | rejected | superseded
    proposed_restatement: Optional[str] = None  # model output; discarded on Confirm
    restatement: Optional[str] = None  # Bill's words on Correct
    restatement_author: Optional[str] = None  # bill
    ratified_on: Optional[str] = None
    rejection_reason: Optional[str] = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "decided_on": self.decided_on,
            "decided_on_status": self.decided_on_status,
            "scope": self.scope,
            "tickers": list(self.tickers),
            "assertion": self.assertion,
            "conditions": self.conditions.to_dict(),
            "unencodable_conditions": list(self.unencodable_conditions),
            "overrides": list(self.overrides),
            "falsifier": self.falsifier,
            "supersedes": self.supersedes,
            "provenance": self.provenance,
            "source_ref": self.source_ref,
            "status": self.status,
            "proposed_restatement": self.proposed_restatement,
            "restatement": self.restatement,
            "restatement_author": self.restatement_author,
            "ratified_on": self.ratified_on,
            "rejection_reason": self.rejection_reason,
        }

    def to_binding_dict(self) -> dict[str, Any]:
        """Binding vault file — never includes proposed_restatement."""
        d = self.to_dict()
        d.pop("proposed_restatement", None)
        if not d.get("restatement"):
            d.pop("restatement", None)
            d.pop("restatement_author", None)
        return d

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> DecisionRecord:
        if "unencodable_conditions" not in d:
            raise KeyError("unencodable_conditions is required")
        if "decided_on_status" not in d:
            raise KeyError("decided_on_status is required")
        decided_on = d.get("decided_on")
        if decided_on is not None and str(decided_on).strip() == "":
            decided_on = None
        return cls(
            id=str(d["id"]),
            decided_on=str(decided_on)[:10] if decided_on else None,
            decided_on_status=str(d["decided_on_status"]),
            scope=str(d["scope"]),
            tickers=[str(t) for t in (d.get("tickers") or [])],
            assertion=str(d.get("assertion") or ""),
            conditions=Conditions.from_dict(d.get("conditions")),
            unencodable_conditions=[str(x) for x in d["unencodable_conditions"]],
            overrides=[str(x) for x in (d.get("overrides") or [])],
            falsifier=str(d.get("falsifier") or ""),
            supersedes=d.get("supersedes"),
            provenance=str(d.get("provenance") or "extracted"),
            source_ref=str(d.get("source_ref") or ""),
            status=str(d.get("status") or "proposed"),
            proposed_restatement=d.get("proposed_restatement"),
            restatement=d.get("restatement"),
            restatement_author=d.get("restatement_author"),
            ratified_on=d.get("ratified_on"),
            rejection_reason=d.get("rejection_reason"),
        )
