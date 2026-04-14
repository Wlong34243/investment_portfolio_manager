"""
Pydantic schemas for the analyze-all run manifest (Phase 5-H).

AgentRunManifest is written to bundles/runs/ after every analyze-all invocation,
regardless of --live mode. It provides a complete audit record of what ran,
what succeeded, what failed, and how many rows were written.
"""

from pydantic import BaseModel, Field
from typing import Literal


class AgentRunSummary(BaseModel):
    """Per-agent status summary within a run manifest."""
    agent: str = Field(..., description="Agent name: rebuy | tax | valuation | concentration | macro | thesis | bagger")
    status: Literal["success", "failed", "skipped"] = Field(
        ..., description="success = ran and produced output. failed = exception or exit. skipped = not in --agents list."
    )
    findings_count: int = Field(
        default=0,
        description="Number of actionable findings (signals, candidates, flags). Excludes portfolio-level summary rows.",
    )
    top_action: str = Field(
        default="",
        description="First or most significant action from this agent's output.",
    )
    sheet_rows: int = Field(
        default=0,
        description="Number of rows this agent contributed to the Agent_Outputs batch write.",
    )
    output_json_path: str | None = Field(
        default=None,
        description="Path to this agent's full JSON output file in bundles/.",
    )
    error_msg: str | None = Field(
        default=None,
        description="Error message if status=failed.",
    )


class AgentRunManifest(BaseModel):
    """
    Full audit record of one analyze-all invocation.
    Written to bundles/runs/manifest_{run_id[:8]}_{date}.json.
    """
    run_id: str = Field(..., description="UUID for this run.")
    run_ts: str = Field(..., description="ISO-8601 UTC timestamp when the run started.")
    composite_hash: str = Field(..., description="Full composite_hash of the bundle used.")
    composite_hash_short: str = Field(..., description="First 16 chars of composite_hash.")
    composite_bundle_path: str = Field(..., description="Path to the composite bundle used.")

    agents_requested: list[str] = Field(
        ..., description="Agents requested via --agents flag."
    )
    agents_succeeded: list[str] = Field(
        default_factory=list,
        description="Agents that completed successfully.",
    )
    agents_failed: list[str] = Field(
        default_factory=list,
        description="Agents that raised an exception or exited with an error.",
    )
    agents_skipped: list[str] = Field(
        default_factory=list,
        description="Agents not in --agents list.",
    )

    agent_summaries: list[AgentRunSummary] = Field(
        default_factory=list,
        description="Per-agent status summaries.",
    )

    total_sheet_rows: int = Field(
        default=0,
        description="Total rows written to Agent_Outputs (standard-schema agents only).",
    )
    errors: list[str] = Field(
        default_factory=list,
        description="Per-agent failure messages. Does not abort the run.",
    )
    dry_run: bool = Field(..., description="True = no Sheet writes.")
    fresh_bundle: bool = Field(..., description="True = fresh market+vault+composite bundles were generated.")

    manifest_path: str | None = Field(
        default=None,
        description="Path where this manifest was written.",
    )


__all__ = ["AgentRunSummary", "AgentRunManifest"]
