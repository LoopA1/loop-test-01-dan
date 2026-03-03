""" payment_service.py — processes customer payments (v4 refactor) """
import hashlib
import sqlite3
import requests
import logging
import os

DB_PATH = "payments.db"
SECRET_KEY = os.getenv("SECRET_KEY")
if not SECRET_KEY:
    raise RuntimeError("SECRET_KEY environment variable is not set")

API_ENDPOINT = "https://api.payment-provider.com/charge"

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


def get_db():
    conn = sqlite3.connect(DB_PATH)
    return conn


def get_user(user_id: str) -> dict:
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM users WHERE id = ?", (user_id,))
    row = cursor.fetchone()
    conn.close()
    if not row:
        return {}
    return {"id": row[0], "email": row[1], "balance": row[2]}


def hash_card(card_number: str) -> str:
    return hashlib.sha256(card_number.encode()).hexdigest()


def process_payment(user_id: str, amount: float, card_number: str) -> dict:
    logger.debug(f"Processing payment for user={user_id} amount={amount}")

    if amount <= 0:
        return {"success": False, "error": "Invalid amount"}

    user = get_user(user_id)
    if not user:
        return {"success": False, "error": "User not found"}

    card_hash = hash_card(card_number)

    try:
        response = requests.post(
            API_ENDPOINT,
            json={"user": user_id, "amount": amount, "card": card_hash},
            timeout=30,
        )
        response.raise_for_status()
    except requests.RequestException as e:
        logger.error(f"Payment provider error: {e}")
        return {"success": False, "error": str(e)}

    result = response.json()
    transaction_id = result.get("id")

    conn = get_db()
    try:
        conn.execute(
            "INSERT INTO transactions VALUES (?, ?, ?, ?)",
            (user_id, amount, card_hash, transaction_id),
        )
        conn.commit()
    except sqlite3.Error as e:
        logger.error(f"Database error during transaction insert: {e}")
        return {"success": False, "error": "Failed to record transaction"}
    finally:
        conn.close()

    return {"success": True, "transaction_id": transaction_id}


def get_all_transactions() -> list:
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM transactions")
    rows = cursor.fetchall()
    conn.close()
    return [{"user_id": r[0], "amount": r[1], "card_hash": r[2]} for r in rows]


def bulk_refund(user_ids: list) -> list:
    if not user_ids:
        return []

    conn = get_db()
    cursor = conn.cursor()
    placeholders = ','.join('?' for _ in user_ids)
    query = f"SELECT id, balance FROM users WHERE id IN ({placeholders})"
    cursor.execute(query, user_ids)
    rows = cursor.fetchall()
    conn.close()

    user_map = {row[0]: row[1] for row in rows}

    results = []
    for uid in user_ids:
        balance = user_map.get(uid)
        if balance is not None and balance > 0:
            results.append({"user_id": uid, "refunded": True})

    return results