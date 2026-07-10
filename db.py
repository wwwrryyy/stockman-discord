"""
Quant-Core AI — db.py (Phase 5)
-------------------------------
Responsible for database interactions using SQLite.
Stores user watchlists and other persistent state.
"""

import sqlite3
import os
from typing import List

DB_PATH = "quant_core.db"

def get_connection() -> sqlite3.Connection:
    """Returns a connection to the SQLite database."""
    return sqlite3.connect(DB_PATH)

def init_db() -> None:
    """Initializes the database schema if tables do not exist."""
    conn = get_connection()
    try:
        with conn:
            cursor = conn.cursor()
            # Create watchlist table: user_id (Discord User ID) and ticker (Stock Symbol)
            cursor.execute(
                """
                CREATE TABLE IF NOT EXISTS watchlist (
                    user_id TEXT NOT NULL,
                    ticker TEXT NOT NULL,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    PRIMARY KEY (user_id, ticker)
                )
                """
            )
    finally:
        conn.close()

def add_to_watchlist(user_id: int, ticker: str) -> bool:
    """
    Adds a ticker to a user's watchlist.
    Returns:
        bool: True if inserted successfully, False if already exists.
    """
    ticker = ticker.upper().strip()
    user_id_str = str(user_id)
    conn = get_connection()
    try:
        with conn:
            cursor = conn.cursor()
            cursor.execute(
                "INSERT INTO watchlist (user_id, ticker) VALUES (?, ?)",
                (user_id_str, ticker)
            )
            return True
    except sqlite3.IntegrityError:
        # Ticker already exists in user's watchlist due to PRIMARY KEY constraint
        return False
    finally:
        conn.close()

def remove_from_watchlist(user_id: int, ticker: str) -> bool:
    """
    Removes a ticker from a user's watchlist.
    Returns:
        bool: True if removed successfully, False if ticker was not in watchlist.
    """
    ticker = ticker.upper().strip()
    user_id_str = str(user_id)
    conn = get_connection()
    try:
        with conn:
            cursor = conn.cursor()
            cursor.execute(
                "DELETE FROM watchlist WHERE user_id = ? AND ticker = ?",
                (user_id_str, ticker)
            )
            # If any rows were affected, the delete was successful
            return cursor.rowcount > 0
    finally:
        conn.close()

def get_watchlist(user_id: int) -> List[str]:
    """
    Gets the list of tickers in a user's watchlist.
    Returns:
        List[str]: List of stock tickers.
    """
    user_id_str = str(user_id)
    conn = get_connection()
    try:
        cursor = conn.cursor()
        cursor.execute(
            "SELECT ticker FROM watchlist WHERE user_id = ? ORDER BY ticker ASC",
            (user_id_str,)
        )
        rows = cursor.fetchall()
        return [row[0] for row in rows]
    finally:
        conn.close()
