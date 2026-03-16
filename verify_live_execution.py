from broker_connector import QuantXConnector, AccountManager
import logging
import time

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger('LiquidX.TestTrade')

def run_test_trade():
    connector = QuantXConnector()
    connector.authenticate()
    manager = AccountManager(connector)
    manager.sync_accounts()

    if not manager.accounts:
        logger.error("No accounts synced. Is ACCOUNT_ID correct in .env?")
        return

    target_account = manager.accounts[0]['id']
    logger.info(f"Targeting Account: {target_account}")

    contracts = connector.search_contracts("MNQ")
    active_mnq = next((c for c in contracts if c.get('activeContract') == True and "Micro" in c.get('description', '')), contracts[0])
    symbol_id = active_mnq['id']
    logger.info(f"Found active MNQ contract: {active_mnq['name']} ({symbol_id})")

    logger.info(f"Submitting 1-lot Market BUY order for {symbol_id}...")
    try:
        buy_res = connector.submit_order(
            account_id=target_account,
            symbol=symbol_id,
            action="Buy",
            quantity=1,
            order_type="Market"
        )
        logger.info(f"Buy Order Response: {buy_res}")
    except Exception as e:
        logger.error(f"Buy Order Failed: {e}")
        return

    logger.info("Waiting 3 seconds for fill...")
    time.sleep(3)

    logger.info(f"Submitting 1-lot Market SELL order to close {symbol_id}...")
    try:
        sell_res = connector.submit_order(
            account_id=target_account,
            symbol=symbol_id,
            action="Sell",
            quantity=1,
            order_type="Market"
        )
        logger.info(f"Sell Order Response: {sell_res}")
    except Exception as e:
        logger.error(f"Sell Order Failed: {e}")

if __name__ == "__main__":
    run_test_trade()