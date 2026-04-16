
import pytest
import pandas as pd
from unittest.mock import MagicMock, patch
from tasks.sync_transactions import sync_transactions
import config

@pytest.fixture
def mock_schwab_client():
    with patch('utils.schwab_client.get_accounts_client') as mock_get:
        mock_client = MagicMock()
        mock_get.return_value = mock_client
        yield mock_client

@pytest.fixture
def mock_gspread():
    with patch('utils.sheet_readers.get_gspread_client') as mock_get:
        mock_gc = MagicMock()
        mock_get.return_value = mock_gc
        
        mock_ss = MagicMock()
        mock_gc.open_by_key.return_value = mock_ss
        
        mock_ws = MagicMock()
        mock_ss.worksheet.return_value = mock_ws
        
        # Default mock for get_all_values (header only)
        mock_ws.get_all_values.return_value = [config.TRANSACTION_COLUMNS]
        
        yield mock_gc, mock_ss, mock_ws

def test_sync_transactions_multi_row(mock_schwab_client, mock_gspread):
    """
    Test 1: Mock multi-row DataFrame from API.
    A multi-row DataFrame triggers "ambiguous truth value" if evaluated as 'if df:'.
    """
    mock_gc, mock_ss, mock_ws = mock_gspread
    
    # Mock API to return a multi-row DataFrame
    multi_row_df = pd.DataFrame([
        {
            'Trade Date': '2026-01-01',
            'Settlement Date': '2026-01-03',
            'Ticker': 'AAPL',
            'Description': 'Apple Inc',
            'Action': 'TRADE',
            'Quantity': 10,
            'Price': 150.0,
            'Amount': 1500.0,
            'Fees': 0.0,
            'Net Amount': 1500.0,
            'Account': 'Schwab Primary',
            'Fingerprint': '2026-01-01|AAPL|TRADE|10|150.0'
        },
        {
            'Trade Date': '2026-01-02',
            'Settlement Date': '2026-01-04',
            'Ticker': 'MSFT',
            'Description': 'Microsoft Corp',
            'Action': 'TRADE',
            'Quantity': 5,
            'Price': 300.0,
            'Amount': 1500.0,
            'Fees': 0.0,
            'Net Amount': 1500.0,
            'Account': 'Schwab Primary',
            'Fingerprint': '2026-01-02|MSFT|TRADE|5|300.0'
        }
    ])
    
    with patch('utils.schwab_client.fetch_transactions', return_value=multi_row_df):
        # We run in dry-run mode (live=False) to avoid actual writes
        # The goal is to see if the merging/checking logic crashes
        result = sync_transactions(days=30, live=False)
        
    assert result is True, "sync_transactions should return True on success"

def test_sync_transactions_empty_row(mock_schwab_client, mock_gspread):
    """
    Test 2: Mock empty DataFrame from API.
    Ensures 'if not df.empty:' or similar handles empty state gracefully.
    """
    mock_gc, mock_ss, mock_ws = mock_gspread
    
    # Mock API to return an empty DataFrame
    empty_df = pd.DataFrame(columns=config.TRANSACTION_COLUMNS)
    
    with patch('utils.schwab_client.fetch_transactions', return_value=empty_df):
        result = sync_transactions(days=30, live=False)
        
    assert result is True, "sync_transactions should return True on success even if empty"

def test_ingest_schwab_transactions_multi_row(mock_gspread):
    """
    Test 3: Mock multi-row DataFrame for pipeline.ingest_schwab_transactions.
    Ensures this specific ingestion function is also bug-free.
    """
    from pipeline import ingest_schwab_transactions
    mock_gc, mock_ss, mock_ws = mock_gspread
    
    # Mock current sheet data (one row)
    mock_ws.col_values.return_value = ['Fingerprint', 'existing_fp']
    
    df = pd.DataFrame([
        {
            'Trade Date': '2026-01-01',
            'Ticker': 'AAPL',
            'Action': 'TRADE',
            'Quantity': 10,
            'Price': 150.0,
            'Fingerprint': 'new_fp1'
        },
        {
            'Trade Date': '2026-01-02',
            'Ticker': 'MSFT',
            'Action': 'TRADE',
            'Quantity': 5,
            'Price': 300.0,
            'Fingerprint': 'new_fp2'
        }
    ])
    
    # Run in dry-run mode
    result = ingest_schwab_transactions(df, dry_run=True)
    
    assert result['new'] == 2
    assert result['parsed'] == 2

def test_ingest_schwab_transactions_empty(mock_gspread):
    """
    Test 4: Mock empty DataFrame for pipeline.ingest_schwab_transactions.
    """
    from pipeline import ingest_schwab_transactions
    
    df = pd.DataFrame()
    
    result = ingest_schwab_transactions(df, dry_run=True)
    
    assert result['parsed'] == 0
    assert result['new'] == 0

if __name__ == "__main__":
    pytest.main([__file__])
