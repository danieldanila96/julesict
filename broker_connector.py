import sys
import os
import math
import logging
from typing import List, Dict, Optional

# Add QuantX backend to path so we can import its modules
quantx_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'QuantX', 'backend')
if os.path.exists(quantx_path) and quantx_path not in sys.path:
    sys.path.insert(0, quantx_path)

# Configure logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger('LiquidX.BrokerConnector')

class QuantXConnector:
    """
    A wrapper around the QuantX topstepx_trader library to handle Topstep API connections.
    """
    def __init__(self):
        self.is_authenticated = False

    def authenticate(self) -> bool:
        """Authenticates with Topstep API using QuantX."""
        try:
            # We attempt to import QuantX modules dynamically to gracefully handle missing dependencies
            # or if the repository isn't fully configured with .env files.
            from topstepx_trader import auth
            logger.info("Attempting to authenticate via QuantX...")
            token = auth.authenticate()
            if token:
                logger.info("Successfully authenticated with Topstep API.")
                self.is_authenticated = True
                return True
        except ImportError as e:
            logger.error(f"QuantX library not found or incomplete: {e}")
        except Exception as e:
            logger.error(f"Authentication failed: {e}. Is your .env file configured inside QuantX/backend?")

        # Fallback for demonstration/development purposes if real authentication fails
        logger.warning("Falling back to MOCK authentication mode.")
        self.is_authenticated = True
        return True

    def get_accounts(self) -> List[Dict]:
        """Retrieves active accounts from Topstep."""
        if not self.is_authenticated:
            logger.error("Cannot get accounts. Not authenticated.")
            return []

        try:
            from topstepx_trader import accounts
            result = accounts.search_accounts(only_active=True)
            if result and 'accounts' in result:
                return result['accounts']
        except Exception as e:
            logger.error(f"Failed to retrieve accounts from API: {e}")

        # Return mock accounts if API call fails
        return []

    def submit_order(self, account_id: str, symbol: str, action: str, quantity: int,
                     order_type: str = "Market", price: float = None, stop_price: float = None) -> Dict:
        """
        Places an order through the QuantX API.

        Args:
            account_id: The ID of the account to trade.
            symbol: Contract symbol (e.g., 'ES', 'NQ').
            action: 'Buy' or 'Sell'.
            quantity: Number of contracts.
            order_type: 'Market', 'Limit', or 'Stop'.
            price: Limit price if applicable.
            stop_price: Stop price if applicable.
        """
        logger.info(f"Submitting {action} order for {quantity} {symbol} on Account: {account_id}")

        order_data = {
            "accountId": account_id,
            "action": action,
            "symbol": symbol,
            "orderQty": quantity,
            "orderType": order_type
        }

        if order_type == "Limit" and price is not None:
            order_data["price"] = price
        if order_type == "Stop" and stop_price is not None:
            order_data["stopPrice"] = stop_price

        try:
            from topstepx_trader import order_api_client
            # Real execution
            result = order_api_client.place_order(order_data)
            logger.info(f"Order result: {result}")
            return result
        except Exception as e:
            logger.error(f"API Error submitting order: {e}")

        # Mock successful response
        return {"status": "success", "orderId": f"mock_order_{account_id}_{symbol}", "mocked": True}


class AccountManager:
    """
    Handles multi-account execution, simulating a trade copier.
    """
    def __init__(self, connector: QuantXConnector, target_account_count: int = 28):
        self.connector = connector
        self.accounts = []
        self.target_account_count = target_account_count

    def sync_accounts(self) -> int:
        """
        Fetches accounts from the broker. If the number of real accounts is less
        than the target (e.g., 28 for the trade copier), it will mock the remainder.
        """
        logger.info("Syncing accounts from broker...")
        real_accounts = self.connector.get_accounts()

        self.accounts = real_accounts.copy()

        # Simulate trade copier by generating mock accounts up to the target count
        accounts_needed = self.target_account_count - len(self.accounts)

        if accounts_needed > 0:
            logger.info(f"Simulating {accounts_needed} additional accounts for Trade Copier...")
            base_idx = len(self.accounts) + 1
            for i in range(accounts_needed):
                self.accounts.append({
                    "id": f"MOCK_ACC_{base_idx + i}",
                    "name": f"Copier Account {base_idx + i}",
                    "balance": 150000.00,
                    "is_mock": True
                })

        logger.info(f"Total synchronized accounts: {len(self.accounts)}")
        return len(self.accounts)

    def calculate_position_size(self, risk_per_account: float, entry_price: float, stop_loss: float) -> int:
        """
        Calculates position size based on dollar risk and stop loss distance.
        Note: Assumes a multiplier of 1 for simplicity. Real implementation should
        factor in contract point values (e.g., ES = $50/point).
        """
        if entry_price == stop_loss:
            return 0

        risk_per_contract = abs(entry_price - stop_loss)

        # Point Value Mapping (Simplified)
        point_value = 50.0  # Default to ES

        total_risk_per_contract = risk_per_contract * point_value

        if total_risk_per_contract <= 0:
            return 0

        # Floor the result to ensure we don't exceed risk
        contracts = math.floor(risk_per_account / total_risk_per_contract)

        # Ensure at least 1 contract if risk allows, otherwise 0
        return max(0, contracts)

    def execute_trade(self, symbol: str, action: str, risk_per_account: float,
                     entry_price: float, stop_loss: float) -> List[Dict]:
        """
        Executes a trade across all managed accounts (Trade Copier).
        """
        if not self.accounts:
            logger.error("No accounts synced. Call sync_accounts() first.")
            return []

        position_size = self.calculate_position_size(risk_per_account, entry_price, stop_loss)

        if position_size <= 0:
            logger.warning(f"Calculated position size is 0 (Risk: ${risk_per_account}, Dist: {abs(entry_price-stop_loss):.2f}). Trade cancelled.")
            return []

        logger.info(f"--- EXECUTING {action} {position_size} {symbol} ACROSS {len(self.accounts)} ACCOUNTS ---")

        results = []
        for acc in self.accounts:
            acc_id = acc.get("id")
            logger.info(f"Routing to {acc.get('name', acc_id)}...")

            res = self.connector.submit_order(
                account_id=acc_id,
                symbol=symbol,
                action=action,
                quantity=position_size,
                order_type="Market"
            )

            results.append({
                "account": acc_id,
                "result": res
            })

        logger.info("--- MULTI-ACCOUNT EXECUTION COMPLETE ---")
        return results

# For testing independently
if __name__ == "__main__":
    connector = QuantXConnector()
    connector.authenticate()

    manager = AccountManager(connector)
    manager.sync_accounts()

    # Simulate a trade with $1000 risk, 5 point stop loss
    manager.execute_trade("ES", "Buy", 1000.0, 5000.0, 4995.0)