"""
core/retrieval — read-only template API over the local ledger + corpus FTS.

The model never authors SQL. It names a template id and supplies value params.
Python executes via a read-only SQLite URI (mode=ro + PRAGMA query_only).
Writes (retrieval_log only) go through the SQLAlchemy write engine separately.
"""

from core.retrieval.api import CorpusQuery, RetrievalSet, TemplateCall, retrieve

__all__ = ["CorpusQuery", "RetrievalSet", "TemplateCall", "retrieve"]
