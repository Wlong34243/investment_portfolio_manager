import streamlit as st

def require_auth():
    """Single auth gate. Call once in app.py before navigation."""
    if "app_password" not in st.secrets:
        return  # Local dev mode
    
    if st.session_state.get("password_correct"):
        return  # Already authenticated
    
    def password_entered():
        if st.session_state["password"] == st.secrets["app_password"]:
            st.session_state["password_correct"] = True
            del st.session_state["password"]
        else:
            st.session_state["password_correct"] = False
    
    st.text_input("Password", type="password", 
                   on_change=password_entered, key="password")
    
    if st.session_state.get("password_correct") == False:
        st.error("😕 Password incorrect")
        
    st.stop()
