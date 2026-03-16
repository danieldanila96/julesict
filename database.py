import sqlite3
import datetime
import json

DB_FILE = "liquidx.db"

def init_db():
    """Initializes the SQLite database and creates necessary tables if they don't exist."""
    conn = sqlite3.connect(DB_FILE)
    cursor = conn.cursor()

    # Create trades table
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS trades (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            symbol TEXT NOT NULL,
            direction TEXT NOT NULL,
            entry_price REAL NOT NULL,
            stop_loss REAL NOT NULL,
            take_profit REAL,
            position_size REAL NOT NULL,
            status TEXT NOT NULL, -- OPEN, CLOSED, FAILED
            entry_time TEXT NOT NULL,
            exit_time TEXT,
            exit_price REAL,
            pnl REAL,
            broker_order_id TEXT
        )
    ''')

    conn.commit()
    conn.close()

def log_trade(symbol, direction, entry_price, stop_loss, position_size, take_profit=None, broker_order_id=None):
    """Logs a new open trade to the database."""
    conn = sqlite3.connect(DB_FILE)
    cursor = conn.cursor()
    now = datetime.datetime.now().isoformat()

    cursor.execute('''
        INSERT INTO trades (symbol, direction, entry_price, stop_loss, take_profit, position_size, status, entry_time, broker_order_id)
        VALUES (?, ?, ?, ?, ?, ?, 'OPEN', ?, ?)
    ''', (symbol, direction, entry_price, stop_loss, take_profit, position_size, now, broker_order_id))

    trade_id = cursor.lastrowid
    conn.commit()
    conn.close()
    return trade_id

def close_trade(trade_id, exit_price, pnl):
    """Marks a trade as CLOSED in the database and records PnL."""
    conn = sqlite3.connect(DB_FILE)
    cursor = conn.cursor()
    now = datetime.datetime.now().isoformat()

    cursor.execute('''
        UPDATE trades
        SET status = 'CLOSED', exit_time = ?, exit_price = ?, pnl = ?
        WHERE id = ?
    ''', (now, exit_price, pnl, trade_id))

    conn.commit()
    conn.close()

def get_open_trades():
    """Retrieves all currently open trades."""
    conn = sqlite3.connect(DB_FILE)
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM trades WHERE status = 'OPEN'")
    columns = [column[0] for column in cursor.description]

    trades = []
    for row in cursor.fetchall():
        trades.append(dict(zip(columns, row)))

    conn.close()
    return trades

if __name__ == "__main__":
    init_db()
    print("Database initialized successfully.")
