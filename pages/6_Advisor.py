import streamlit as st
from utils.sheet_readers import get_holdings_current
from utils.column_guard import ensure_display_columns
from utils.chat_engine import chat, build_portfolio_summary
from datetime import datetime
import os
import sys

st.title("💬 AI Portfolio Advisor")

# --- Initialize Chat History ---
if "messages" not in st.session_state:
    st.session_state.messages = []

# --- Load Data for Context ---
try:
    holdings_df = get_holdings_current()
    holdings_df = ensure_display_columns(holdings_df)
except Exception as e:
    st.error("Could not connect to Google Sheets. Check your connection and service account permissions.")
    st.stop()

if holdings_df.empty:
    st.warning("Please upload your portfolio on the main page to enable the advisor.")
    st.stop()

# --- Sidebar ---
with st.sidebar:
    if st.button("🗑️ Clear Chat"):
        st.session_state.messages = []
        st.rerun()
    st.write(f"Messages: {len(st.session_state.messages)}")

# --- Podcast-Driven Trade Ideas ---
with st.expander("📻 Podcast-Driven Trade Ideas", expanded=False):
    st.caption("Generates BUY / REDUCE / HOLD recommendations by combining recent analyst podcast signals with your top 15 holdings.")
    if st.button("Generate Trade Ideas from Podcasts"):
        with st.spinner("Loading podcast signals and building recommendations..."):
            try:
                from utils.podcast_digest import build_trade_prompt
                from utils.gemini_client import ask_gemini
                prompt_text = build_trade_prompt(holdings_df)
                trade_ideas = ask_gemini(prompt_text)
                st.markdown(trade_ideas)
            except Exception as e:
                st.error(f"Could not generate trade ideas: {e}")

st.divider()

# --- Suggested Prompts ---
suggestions = [
    "What's my tech exposure risk?",
    "Any earnings coming up?",
    "Which stocks look undervalued?",
    "Can I sell covered calls?",
    "Am I actually diversified?",
    "What if the Fed cuts rates?",
    "Why did UNH drop today?",
    "What tax losses can I harvest?"
]

st.write("### Quick Questions")
cols = st.columns(4)
for i, sug in enumerate(suggestions):
    if cols[i % 4].button(sug, key=f"sug_{i}"):
        # Simulate user input from suggestion
        st.session_state.messages.append({"role": "user", "content": sug})
        # Generate response
        summary = build_portfolio_summary(holdings_df)
        hist = [m["content"] for m in st.session_state.messages[:-1]]
        response, intent = chat(sug, hist, summary)
        st.session_state.messages.append({"role": "assistant", "content": response, "intent": intent})
        st.rerun()

# --- Display Chat History ---
for message in st.session_state.messages:
    with st.chat_message(message["role"]):
        st.markdown(message["content"])
        if message["role"] == "assistant":
            st.caption(f"Refreshed at: {datetime.now().strftime('%H:%M:%S')}")
        if "intent" in message:
            st.caption(f"Intent: {message['intent']}")

# --- Chat Input ---
if prompt := st.chat_input("Ask me anything about your portfolio..."):
    # Display user message
    with st.chat_message("user"):
        st.markdown(prompt)
    st.session_state.messages.append({"role": "user", "content": prompt})

    # Generate response
    with st.chat_message("assistant"):
        with st.spinner("Thinking..."):
            summary = build_portfolio_summary(holdings_df)
            hist = [m["content"] for m in st.session_state.messages[:-1]]
            response, intent = chat(prompt, hist, summary)
            st.markdown(response)
            st.caption(f"Intent: {intent}")
            
    st.session_state.messages.append({"role": "assistant", "content": response, "intent": intent})
