import streamlit as st
from datetime import date
import config
from pipeline import append_decision_log

st.set_page_config(page_title="Decision Journal", page_icon="📝")
st.title("📝 Decision Journal")
st.caption("Your memory layer — log the *why* behind every trade decision.")

# --- SPY context auto-fetch ---
if "market_context" not in st.session_state:
    st.session_state["market_context"] = ""

if st.button("📡 Fetch SPY Price"):
    try:
        from utils.enrichment import get_live_price
        price = get_live_price("SPY")
        if price is not None:
            st.session_state["market_context"] = f"SPY @ ${price:.2f} | "
        else:
            st.warning("Could not fetch SPY price — enter market context manually.")
    except Exception:
        st.warning("Could not fetch SPY price — enter market context manually.")

# --- Journal entry form ---
with st.form("journal_entry"):
    col1, col2 = st.columns(2)
    with col1:
        entry_date = st.date_input("Date", value=date.today())
    with col2:
        action = st.selectbox("Action", ["Buy", "Sell", "Hold", "Rebalance", "Watch"])

    tickers = st.text_input("Tickers Involved", placeholder="NVDA, AAPL")

    market_context = st.text_input(
        "Market Context",
        value=st.session_state.get("market_context", ""),
        placeholder="SPY @ $510, VIX spiking, pre-earnings",
    )

    rationale = st.text_area(
        "Rationale",
        placeholder="What must be true for this decision to work? Why now?",
        height=150,
    )

    tags = st.text_input("Tags", placeholder="Macro, Tech, Rebalance, TLH")

    submitted = st.form_submit_button("Log Decision")

if submitted:
    if not tickers.strip() or not rationale.strip():
        st.error("Tickers and Rationale are required.")
    else:
        success = append_decision_log(
            date_str=entry_date.strftime("%Y-%m-%d"),
            tickers=tickers.strip(),
            action=action,
            context=market_context.strip(),
            rationale=rationale.strip(),
            tags=tags.strip(),
        )
        if success:
            st.success("Decision logged to Memory Layer.")
            st.balloons()
        else:
            st.error("Failed to log decision. Check the Logs tab.")

# --- Recent decisions display ---
with st.expander("📖 Recent Decisions", expanded=False):
    try:
        from utils.sheet_readers import get_gspread_client
        import pandas as pd

        client = get_gspread_client()
        spreadsheet = client.open_by_key(config.PORTFOLIO_SHEET_ID)
        ws = spreadsheet.worksheet(config.TAB_DECISION_LOG)
        all_rows = ws.get_all_values()
        if len(all_rows) > 1:
            df = pd.DataFrame(all_rows[1:], columns=all_rows[0])
            st.dataframe(df.tail(10).iloc[::-1], use_container_width=True, hide_index=True)
        else:
            st.info("No decisions logged yet.")
    except Exception as e:
        st.warning(f"Could not load recent decisions: {e}")
