import logging
import os
import requests
from dotenv import load_dotenv

# Ensure logs directory exists
os.makedirs('logs', exist_ok=True)

# Configure structured logging
logger = logging.getLogger("LiquidX_Engine")
logger.setLevel(logging.INFO)

# File handler
fh = logging.FileHandler('logs/liquidx.log')
fh.setLevel(logging.INFO)

# Console handler
ch = logging.StreamHandler()
ch.setLevel(logging.INFO)

# Formatter
formatter = logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s')
fh.setFormatter(formatter)
ch.setFormatter(formatter)

logger.addHandler(fh)
logger.addHandler(ch)

# Load env variables for Telegram
load_dotenv()
TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
TELEGRAM_CHAT_ID = os.getenv("TELEGRAM_CHAT_ID")

def send_telegram_alert(message):
    """Sends a markdown formatted message to the configured Telegram chat."""
    if not TELEGRAM_BOT_TOKEN or not TELEGRAM_CHAT_ID:
        logger.warning(f"Telegram credentials not configured. Missed alert: {message}")
        return False

    url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage"
    payload = {
        "chat_id": TELEGRAM_CHAT_ID,
        "text": message,
        "parse_mode": "Markdown"
    }

    try:
        response = requests.post(url, json=payload, timeout=5)
        if response.status_code == 200:
            return True
        else:
            logger.error(f"Failed to send Telegram alert: {response.text}")
            return False
    except Exception as e:
        logger.error(f"Telegram alert exception: {str(e)}")
        return False

def alert_trade_entry(symbol, direction, price, sl, tp, size):
    msg = f"🚨 *TRADE ENTRY* 🚨\n\n*Symbol:* {symbol}\n*Direction:* {direction}\n*Entry:* {price:.2f}\n*Stop Loss:* {sl:.2f}\n*Take Profit:* {tp:.2f if tp else 'N/A'}\n*Size:* {size:.2f}"
    logger.info(f"Executing Trade: {direction} {size} units of {symbol} at {price}")
    send_telegram_alert(msg)

def alert_trade_exit(symbol, direction, price, pnl):
    icon = "✅" if pnl > 0 else "❌"
    msg = f"{icon} *TRADE CLOSED* {icon}\n\n*Symbol:* {symbol}\n*Direction:* {direction}\n*Exit Price:* {price:.2f}\n*PnL:* ${pnl:.2f}"
    logger.info(f"Closed Trade: {direction} {symbol} at {price} | PnL: ${pnl:.2f}")
    send_telegram_alert(msg)

def alert_error(error_msg):
    msg = f"⚠️ *SYSTEM ERROR* ⚠️\n\n```\n{error_msg}\n```"
    logger.error(error_msg)
    send_telegram_alert(msg)

if __name__ == "__main__":
    logger.info("Notifier system initialized.")
    alert_error("Test System Error Alert")
