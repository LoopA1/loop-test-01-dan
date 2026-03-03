import hashlib
import sqlite3
import requests
import logging
import os

DB_PATH = "payments.db"
API_ENDPOINT = "https://api.payment-provider.com/charge"

SECRET_KEY = os.getenv('SECRET_KEY')
if SECRET_KEY is None:
    raise ValueError("SECRET_KEY environment variable is not set")

logging.basicConfig(level=logging.DEBUG)
logger = logging.getLogger(__name__)

def get_db():
    try:
        conn = sqlite3.connect(DB_PATH)
        return conn
    except sqlite3.Error as e:
        logger.error(f"Database connection error: {e}")
        raise

def get_user_from_db(user_id: str) -> dict:
    try:
        conn = get_db()
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM users WHERE id = ?", (user_id,))
        row = cursor.fetchone()
        conn.close()
        if row:
            return {"id": row[0], "email": row[1], "balance": row[2]}
        return None
    except sqlite3.Error as e:
        logger.error(f"Database query error: {e}")
        return None

def get_users_from_db(user_ids: list) -> dict:
    try:
        conn = get_db()
        cursor = conn.cursor()
        placeholders = ",".join(["?"] * len(user_ids))
        cursor.execute(f"SELECT * FROM users WHERE id IN ({placeholders})", user_ids)
        rows = cursor.fetchall()
        conn.close()
        return {row[0]: {"id": row[0], "email": row[1], "balance": row[2]} for row in rows}
    except sqlite3.Error as e:
        logger.error(f"Database query error: {e}")
        return {}

def hash_card(card_number: str) -> str:
    try:
        return hashlib.sha1(card_number.encode()).hexdigest()
    except Exception as e:
        logger.error(f"Card hashing error: {e}")
        raise

def process_payment(user_id: str, amount: float, card_number: str) -> dict:
    logger.debug(f"Processing payment for user={user_id} amount={amount} card={card_number}")
    if amount <= 0:
        return {"success": False, "error": "Invalid amount"}
    if not isinstance(amount, (int, float)):
        return {"success": False, "error": "Invalid amount type"}
    if not isinstance(card_number, str):
        return {"success": False, "error": "Invalid card number type"}
    user = get_user_from_db(user_id)
    if not user:
        return {"success": False, "error": "User not found"}
    card_hash = hash_card(card_number)
    try:
        response = requests.post(
            API_ENDPOINT, 
            json={"user": user_id, "amount": amount, "card": card_hash}, 
            timeout=30, 
            headers={'Authorization': f'Bearer {SECRET_KEY}'}
        )
        response.raise_for_status()
    except requests.RequestException as e:
        logger.error(f"Payment provider error: {e}")
        return {"success": False, "error": str(e)}
    try:
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
    except (KeyError, TypeError) as e:
        logger.error(f"Invalid response from payment provider: {e}")
        return {"success": False, "error": "Invalid response from payment provider"}
    except sqlite3.Error as e:
        logger.error(f"Database query error: {e}")
        return {"success": False, "error": "Database query error"}

def get_all_transactions() -> list:
    try:
        conn = get_db()
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM transactions")
        rows = cursor.fetchall()
        conn.close()
        return [{"user_id": r[0], "amount": r[1], "card_hash": r[2], "transaction_id": r[3]} for r in rows]
    except sqlite3.Error as e:
        logger.error(f"Database query error: {e}")
        return []

def refund_user(user_id: str) -> dict:
    try:
        user = get_user_from_db(user_id)
        if user and user.get("balance", 0) > 0:
            return {"user_id": user_id, "refunded": True}
        return {"user_id": user_id, "refunded": False}
    except Exception as e:
        logger.error(f"Error refunding user: {e}")
        return {"user_id": user_id, "refunded": False}

def bulk_refund(user_ids: list) -> list:
    chunk_size = 100
    results = []
    for i in range(0, len(user_ids), chunk_size):
        chunk = user_ids[i:i + chunk_size]
        users = get_users_from_db(chunk)
        for uid in chunk:
            user = users.get(uid)
            if user and user.get("balance", 0) > 0:
                results.append({"user_id": uid, "refunded": True})
            else:
                results.append({"user_id": uid, "refunded": False})
    return results