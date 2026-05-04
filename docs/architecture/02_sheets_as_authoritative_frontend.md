# 02. Sheets as Authoritative Frontend

**Motivating Question:** What is the best user interface for a CPA-led investment system?

**Decision:** Google Sheets is the authoritative frontend for both data visualization and manual configuration.

**Rationale:**
Early in the project, Streamlit was considered for the dashboard. However, for a professional investor (CPA), Sheets offers superior advantages:
1. **Familiarity:** Zero learning curve for data manipulation, filtering, and sorting.
2. **Persistence:** Built-in history, version control, and multi-device access without hosting a server.
3. **Hybrid Input:** Sheets allows Bill to manually override targets (Trim/Add) or strategic weights directly in the UI, which Python can then read as a source of truth.
4. **Reliability:** No "web server" to crash or maintain.

**Alternatives Considered:**
- **Streamlit:** Rejected for production-grade UI because "app state" is harder to manage than "cell state."
- **Custom Web UI:** Rejected as too much overhead for a single-user system.

**Result:** A familiar, high-performance UI that supports both passive scanning and active manual control.
