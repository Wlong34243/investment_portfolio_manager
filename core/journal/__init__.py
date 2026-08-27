"""
Journal / rationale loop — proposals you confirm, correct, or reject.

Poisoning controls (mechanical):
1. Fabricated rationale — proposal stays machine-visible until confirmed; Proposed_Bet
   retains what was proposed alongside Implicit_Bet (Bill's words only).
2. Hindsight — reconcile defaults to Rationale_Provenance=reconstructed_after.
   declared_before is set only when an acted precommitment firing matches the fill
   (core/journal/precommit.py). No CLI flag re-labels provenance by hand.
"""

from core.journal.propose import Proposal, build_proposals, match_strength_counts
from core.journal.reconcile import UnreconciledCluster, load_unreconciled_clusters

__all__ = [
    "Proposal",
    "UnreconciledCluster",
    "build_proposals",
    "load_unreconciled_clusters",
    "match_strength_counts",
]
