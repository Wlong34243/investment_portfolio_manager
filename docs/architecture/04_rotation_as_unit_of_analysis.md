# 04. Rotation as the Unit of Analysis

**Motivating Question:** How should we structure trade data to reflect real-world professional behavior?

**Decision:** The system treats most transactions as "Rotations" (clusters of sells and buys) rather than isolated trades.

**Rationale:**
Professional investors rarely sell into cash and sit. Usually, a sell is a decision to move capital from a "full" or "broken" position into a "better" one. By modeling data this way:
1. **Attribution:** We can compare the performance of what was bought vs what was sold (the Pair Return).
2. **Context:** Capturing technicals at the moment of rotation helps identify behavioral timing biases.
3. **Intent:** The `Trade_Log` forces the user to define an `Implicit_Bet`, turning the log from a record of history into a tool for self-tuning.

**Alternatives Considered:**
- **Isolated Trade Ledger:** Rejected as it misses the "why" behind the trade.
- **Full TWR/GIPS reporting:** Rejected as too complex for a personal tool; price-return pairs provide 80% of the value with 20% of the math.

**Result:** A feedback loop that directly improves market timing and style discipline.
