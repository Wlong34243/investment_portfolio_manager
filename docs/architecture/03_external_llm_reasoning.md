# 03. External LLM Reasoning

**Motivating Question:** How do we leverage frontier AI models without suffering from API latency, cost, or "hallucinated" data?

**Decision:** APIs compute locally; LLMs reason externally via exportable context packages.

**Rationale:**
Local agent execution (Phase 0) proved fragile. Keeping reasoning "in-the-loop" via manual paste provides:
1. **Model Agnostic:** Use Claude for tax, Gemini for macro, or Perplexity for news without changing a single line of code.
2. **Deterministic Context:** The "Export Engine" ensures the LLM sees the exact same numbers Bill sees in his sheet, eliminating hallucination of portfolio state.
3. **Reasoning Quality:** Frontier models are best used when they have 100% of a human's attention, not when running in a background loop.
4. **Cost Control:** Zero ongoing API costs for "automated" analysis that might not be read.

**Alternatives Considered:**
- **Automated Local Agents:** Rejected as too hard to maintain and tune for production-grade reliability.
- **Embedded LLM Chat:** Rejected to avoid building a redundant UI.

**Result:** A "Reasoning Workflow" that treats the LLM as a high-powered research partner rather than a replacement for the investor.
