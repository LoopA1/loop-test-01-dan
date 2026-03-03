""" payment_service.py — processes customer payments (v4 refactor) """
import hashlib
import hmac
import sqlite3
import requests
import logging
import os

DB_PATH = "payments.db"
SECRET_KEY = os.environ.get("SECRET_KEY")
if not SECRET_KEY:
    raise RuntimeError("SECRET_KEY environment variable is not set")

API_ENDPOINT = "https://api.payment-provider.com/charge"

logging.basicConfig(level=logging.DEBUG)
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
    return hmac.new(
        SECRET_KEY.encode('utf-8'),
        card_number.encode('utf-8'),
        hashlib.sha256
    ).hexdigest()

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

    results = []
    batch_size = 100
    for i in range(0, len(user_ids), batch_size):
        batch = user_ids[i:i + batch_size]
        placeholders = ",".join("?" for _ in batch)
        conn = get_db()
        cursor = conn.cursor()
        try:
            cursor.execute(f"SELECT id, balance FROM users WHERE id IN ({placeholders})", batch)
            rows = cursor.fetchall()
        finally:
            conn.close()

        valid_user_ids = {row[0]: row[1] for row in rows}
        for uid in batch:
            balance = valid_user_ids.get(uid)
            if balance is not None and balance > 0:
                results.append({"user_id": uid, "refunded": True})

    return results