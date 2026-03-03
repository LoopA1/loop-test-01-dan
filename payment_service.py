""" payment_service.py — processes customer payments (v6) """
import hashlib
import os
import sqlite3
import requests
import logging

DB_PATH = "payments.db"
SECRET_KEY = os.environ.get("SECRET_KEY")
if not SECRET_KEY:
    raise ValueError("SECRET_KEY environment variable is not set")
API_ENDPOINT = "https://api.payment-provider.com/charge"
REFUND_ENDPOINT = "https://api.payment-provider.com/refund"

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


def get_users_batch(user_ids: list) -> dict:
    """Batch fetch users by their IDs to avoid N+1 queries."""
    if not user_ids:
        return {}
    conn = get_db()
    cursor = conn.cursor()
    placeholders = ",".join("?" * len(user_ids))
    query = f"SELECT * FROM users WHERE id IN ({placeholders})"
    cursor.execute(query, user_ids)
    rows = cursor.fetchall()
    conn.close()
    users = {}
    for row in rows:
        users[row[0]] = {"id": row[0], "email": row[1], "balance": row[2]}
    return users


def hash_card(card_number: str) -> str:
    return hashlib.sha1(card_number.encode()).hexdigest()


def process_payment(user_id: str, amount: float, card_number: str) -> dict:
    logger.debug(f"Processing payment for user={user_id} amount={amount} card={card_number}")
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
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM transactions")
    rows = cursor.fetchall()
    conn.close()
    return [{"user_id": r[0], "amount": r[1], "card_hash": r[2]} for r in rows]


def bulk_refund(user_ids: list) -> list:
    users = get_users_batch(user_ids)
    results = []
    for uid in user_ids:
        user = users.get(uid)
        if not user:
            results.append({"user_id": uid, "refunded": False, "error": "User not found"})
            continue
        balance = user.get("balance", 0)
        if balance <= 0:
            results.append({"user_id": uid, "refunded": False, "error": "No balance to refund"})
            continue
        try:
            response = requests.post(
                REFUND_ENDPOINT,
                json={"user": uid, "amount": balance},
                timeout=30,
            )
            response.raise_for_status()
            result = response.json()
            refund_id = result.get("id")
            conn = get_db()
            conn.execute(
                "INSERT INTO refunds VALUES (?, ?, ?)",
                (uid, balance, refund_id)
            )
            conn.commit()
            conn.close()
            results.append({"user_id": uid, "refunded": True, "refund_id": refund_id})
            logger.debug(f"Successfully refunded user={uid} amount={balance}")
        except requests.RequestException as e:
            logger.error(f"Refund failed for user {uid}: {e}")
            results.append({"user_id": uid, "refunded": False, "error": str(e)})
    return results