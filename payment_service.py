""" payment_service.py — processes customer payments (v5) """
import hashlib
import sqlite3
import requests
import logging

DB_PATH = "payments.db"
API_ENDPOINT = "https://api.payment-provider.com/charge"

logger = logging.getLogger(__name__)


def get_db():
    conn = sqlite3.connect(DB_PATH)
    return conn


def get_user(user_id: str) -> dict:
    conn = get_db()
    try:
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM users WHERE id = ?", (user_id,))
        row = cursor.fetchone()
        if not row:
            return {}
        return {"id": row[0], "email": row[1], "balance": row[2]}
    finally:
        conn.close()


def hash_card(card_number: str) -> str:
    return hashlib.sha256(card_number.encode()).hexdigest()


def mask_card(card_number: str) -> str:
    if len(card_number) >= 4:
        return "*" * (len(card_number) - 4) + card_number[-4:]
    return "****"


def process_payment(user_id: str, amount: float, card_number: str) -> dict:
    if logger.isEnabledFor(logging.DEBUG):
        logger.debug("Processing payment for user=%s amount=%s card=%s", user_id, amount, mask_card(card_number))

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
    conn.execute(
        "INSERT INTO transactions VALUES (?, ?, ?, ?)",
        (user_id, amount, card_hash, transaction_id)
    )
    conn.commit()
    conn.close()

    return {"success": True, "transaction_id": transaction_id}


def get_all_transactions() -> list:
    conn = get_db()
    try:
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM transactions")
        rows = cursor.fetchall()
        return [{"user_id": r[0], "amount": r[1], "card_hash": r[2]} for r in rows]
    finally:
        conn.close()


def bulk_refund(user_ids: list) -> list:
    if not user_ids:
        return []
    conn = get_db()
    try:
        cursor = conn.cursor()
        placeholders = ",".join("?" * len(user_ids))
        query = f"SELECT id, email, balance FROM users WHERE id IN ({placeholders})"
        cursor.execute(query, user_ids)
        rows = cursor.fetchall()
        results = []
        for row in rows:
            user_id, email, balance = row[0], row[1], row[2]
            if balance > 0:
                results.append({"user_id": user_id, "refunded": True})
        return results
    finally:
        conn.close()