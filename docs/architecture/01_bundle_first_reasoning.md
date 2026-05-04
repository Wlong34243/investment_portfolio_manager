# 01. Bundle-First Reasoning

**Motivating Question:** How can we ensure that AI reasoning is grounded in a specific, auditable state of the world?

**Decision:** Every significant analysis session must begin by capturing the current market and research state into a hashed, immutable JSON "Context Bundle."

**Rationale:**
Financial data is high-velocity and ephemeral. If an LLM analyzes a portfolio on Tuesday using "live" data, and the user reviews that analysis on Thursday after a major market move, the rationale may no longer make sense. By freezing the data first:
1. **Provenance:** Every decision can be traced back to the exact prices and technicals used at that moment.
2. **Auditability:** The SHA256 hash of the bundle ensures the data hasn't been tampered with.
3. **Consistency:** All agents in a tactical squad see the exact same view of the world, preventing drift during long runs.

**Alternatives Considered:**
- **Live API Injection:** Rejected due to "state leakage" where data changes mid-analysis.
- **Database Persistence:** Rejected as too heavy for a personal tool; flat JSON files are easier to inspect and archive.

**Result:** A deterministic spine that separates data capture from data reasoning.
