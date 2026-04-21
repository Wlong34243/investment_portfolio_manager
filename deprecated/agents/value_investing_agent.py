import json
import logging
import os
from pathlib import Path

logger = logging.getLogger(__name__)

class ValueInvestingAgent:
    """
    An agent that screens stocks based on the principles of Benjamin Graham, 
    Warren Buffett, and Christopher H. Browne.
    """
    def __init__(self, strategy_path="value_investing_strategy.json"):
        self.strategy_file = Path(strategy_path)
        self.strategy = self._load_strategy()

    def _load_strategy(self):
        if not self.strategy_file.exists():
            logger.error(f"Strategy file not found at {self.strategy_file}")
            return {}
        
        with open(self.strategy_file, 'r') as f:
            try:
                return json.load(f)
            except json.JSONDecodeError as e:
                logger.error(f"Error parsing {self.strategy_file}: {e}")
                return {}

    def screen_ticker(self, ticker: str, fundamental_data: dict) -> dict:
        """
        Evaluates a stock based on Graham and Buffett criteria.
        
        :param ticker: The stock ticker symbol.
        :param fundamental_data: A dictionary containing fundamental metrics 
                                 (e.g., pe_ratio, pb_ratio, current_ratio, roe, etc.)
                                 fetched from finnhub_client or fmp_client.
        :return: A dictionary containing the analysis results and pass/fail boolean.
        """
        if not self.strategy:
            return {"ticker": ticker, "passed": False, "reason": "No strategy loaded."}

        graham = self.strategy.get("graham_criteria", {})
        buffett = self.strategy.get("buffett_criteria", {})
        
        reasons_failed = []
        passes_graham = True
        passes_buffett = True

        # --- Evaluate Graham Criteria (Defensive/Net-Net) ---
        pe = fundamental_data.get("pe_ratio", float('inf'))
        pb = fundamental_data.get("pb_ratio", float('inf'))
        current_ratio = fundamental_data.get("current_ratio", 0)

        if pe > graham.get("max_pe_ratio", 15.0):
            passes_graham = False
            reasons_failed.append(f"P/E ratio {pe} exceeds max {graham.get('max_pe_ratio')}")
            
        if pb > graham.get("max_pb_ratio", 1.5):
            passes_graham = False
            reasons_failed.append(f"P/B ratio {pb} exceeds max {graham.get('max_pb_ratio')}")
            
        # Graham Number Check (PE * PB should not exceed 22.5 usually)
        if (pe * pb) > graham.get("graham_number_multiplier", 22.5):
            passes_graham = False
            reasons_failed.append(f"P/E * P/B ({pe * pb}) exceeds Graham multiplier 22.5")

        if current_ratio < graham.get("min_current_ratio", 2.0):
            passes_graham = False
            reasons_failed.append(f"Current ratio {current_ratio} is below min {graham.get('min_current_ratio')}")

        # --- Evaluate Buffett Criteria (Quality/Moat) ---
        roe = fundamental_data.get("roe_pct", 0)
        debt_to_equity = fundamental_data.get("debt_to_equity", float('inf'))

        if roe < buffett.get("min_roe_pct", 15.0):
            passes_buffett = False
            reasons_failed.append(f"ROE {roe}% is below min {buffett.get('min_roe_pct')}%")
            
        if debt_to_equity > buffett.get("max_debt_to_equity", 0.5):
            passes_buffett = False
            reasons_failed.append(f"Debt/Equity {debt_to_equity} exceeds max {buffett.get('max_debt_to_equity')}")

        # Determine overall pass
        # Depending on your strictness, you can require BOTH or just ONE to pass.
        # Christopher Browne often advocated blending the two (quality on sale).
        is_buy = passes_graham and passes_buffett

        return {
            "ticker": ticker,
            "passed": is_buy,
            "passes_graham_criteria": passes_graham,
            "passes_buffett_criteria": passes_buffett,
            "reasons_failed": reasons_failed,
            "margin_of_safety_required": self.strategy.get("margin_of_safety_pct", 33.0)
        }

    def evaluate_portfolio(self, portfolio_data: list) -> list:
        """
        Batch process a list of portfolio holdings.
        """
        results = []
        for asset in portfolio_data:
            ticker = asset.get("ticker")
            metrics = asset.get("metrics", {})
            result = self.screen_ticker(ticker, metrics)
            results.append(result)
            
            if result["passed"]:
                logger.info(f"{ticker} PASSED value investing screen.")
            else:
                logger.info(f"{ticker} FAILED: {', '.join(result['reasons_failed'])}")
                
        return results

# Example usage for testing standalone:
if __name__ == "__main__":
    agent = ValueInvestingAgent("../../value_investing_strategy.json") # Adjust path as needed
    mock_data = {
        "pe_ratio": 12.5,
        "pb_ratio": 1.2,
        "current_ratio": 2.5,
        "roe_pct": 18.0,
        "debt_to_equity": 0.3
    }
    print(agent.screen_ticker("AAPL", mock_data))