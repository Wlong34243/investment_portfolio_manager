import streamlit as st
import gspread
import google.auth

# Assuming config_template.py is renamed to config.py or imported as such
import config_template as config 
from pipeline import ingest_realized_gl 

# --- Google Sheets Authentication (Placeholder) ---
# In a real Streamlit app, you would handle this more securely,
# e.g., using st.secrets or a service account key file.
# For now, we'll mock the sheet_client or provide a dummy.
def get_gspread_client():
    """
    Returns a gspread client.
    In a real app, this would authenticate, e.g., with a service account.
    """
    # Placeholder: Replace with actual authentication
    # For local development with gspread and a service account:
    # creds, project = google.auth.default(
    #     scopes=['https://www.googleapis.com/auth/spreadsheets']
    # )
    # return gspread.authorize(creds)
    
    # Dummy client for now
    class DummyWorksheet:
        def __init__(self, title=""):
            self.title = title
            self.data = []
            self.row_count = 0
            self.col_count = 0

        def get_all_records(self):
            return self.data

        def append_row(self, row_values, value_input_option='USER_ENTERED'):
            if not self.data:
                # Assume first append_row sets the header if data is empty
                self.data.append(row_values)
                self.row_count = 1
                self.col_count = len(row_values)
            else:
                self.data.append(row_values)
                self.row_count += 1

        def append_rows(self, list_of_rows, value_input_option='USER_ENTERED'):
            for row_values in list_of_rows:
                self.append_row(row_values, value_input_option)

        def cell(self, row, col):
            # Simulate cell content, for header check mostly
            if row == 1 and col == 1 and self.data:
                return type('obj', (object,), {'value': self.data[0][0]})() # Dummy object with value attribute
            return type('obj', (object,), {'value': ''})()

    class DummySpreadsheet:
        def worksheet(self, title):
            return DummyWorksheet(title)

    class DummyClient:
        def open_by_id(self, id):
            return DummySpreadsheet()

    return DummyClient()


sheet_client = get_gspread_client()

st.set_page_config(layout="wide", page_title="Investment Portfolio Manager")

st.title("Investment Portfolio Manager")

# --- Sidebar ---
st.sidebar.header("Upload CSV Files")

gl_file = st.sidebar.file_uploader(
    "Upload Realized G/L CSV (optional)",
    type=["csv"],
    help="Schwab: Accounts > History > Realized Gain/Loss > Export"
)

# --- Main Content Area ---
tab_names = ["Portfolio Overview", "Holdings", "Daily Snapshots", "Transactions", "Tax & Behavior"]
tabs = st.tabs(tab_names)

with tabs[0]:
    st.header("Portfolio Overview")
    st.write("Summary of your investment portfolio.")

with tabs[1]:
    st.header("Holdings")
    st.write("Current and historical holdings.")

with tabs[2]:
    st.header("Daily Snapshots")
    st.write("Daily summary of portfolio value.")

with tabs[3]:
    st.header("Transactions")
    st.write("History of all transactions.")

with tabs[4]:
    st.header("Tax & Behavior")
    st.write("Detailed analysis of realized gains/losses, wash sales, and behavioral insights.")

    if gl_file is not None:
        st.subheader("Process Realized G/L CSV")
        dry_run_gl = st.checkbox("Dry Run for G/L Ingestion?", value=True, key="dry_run_gl")

        if st.button("Ingest Realized G/L Data", key="ingest_gl_button"):
            with st.spinner("Processing Realized G/L data..."):
                # Use the actual sheet_id from config_template
                sheet_id = config.PORTFOLIO_SHEET_ID
                
                if not sheet_id:
                    st.error("PORTFOLIO_SHEET_ID is not configured. Please set it in config_template.py or Streamlit secrets.")
                else:
                    try:
                        results_gl = ingest_realized_gl(gl_file, sheet_client, sheet_id, dry_run=dry_run_gl)
                        
                        st.subheader("Ingestion Results:")
                        st.write(f"Parsed records: {results_gl['parsed']}")
                        st.write(f"New records added to Sheet: {results_gl['new']}")
                        st.write(f"Skipped (duplicates or invalid): {results_gl['skipped']}")
                        if results_gl['errors']:
                            st.error(f"Errors: {'; '.join(results_gl['errors'])}")
                        else:
                            st.success("Realized G/L data processed successfully!")
                            if dry_run_gl:
                                st.info("This was a DRY RUN. No data was actually written to the Google Sheet.")

                    except Exception as e:
                        st.error(f"An unexpected error occurred during G/L ingestion: {e}")
                        import traceback
                        st.exception(e)
    else:
        st.info("Upload a Realized G/L CSV file in the sidebar to process it.")