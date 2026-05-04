# 05. Tax Visibility as First-Class

**Motivating Question:** How can a CPA leverage his expertise without manually calculating every lot?

**Decision:** Tax planning is a dedicated pipeline component with its own high-level dashboard (`Tax_Control`).

**Rationale:**
Most portfolio trackers treat tax as a year-end afterthought. This system treats it as a "behavioral lever":
1. **Offset Capacity:** By surfacing exactly how many dollars of gains can be offset by harvesting losses, the system creates behavioral pressure to take losses early.
2. **Wash-Sale Sentinel:** Automated highlighting prevents expensive behavioral mistakes.
3. **Planning vs Advice:** The system explicitly frames tax as a planning tool, allowing for conservative estimates that guide decision-making without the risk of being mistaken for "official" tax reporting.

**Alternatives Considered:**
- **Agent Narrative:** Rejected because tax is a numeric fact, not a qualitative opinion.
- **Ignore Tax:** Rejected as non-viable for a CPA-led system.

**Result:** A "CPA's Corner" that turns tax drag into a manageable strategic component.
