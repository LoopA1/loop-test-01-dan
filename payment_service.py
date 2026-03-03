import hashlib
import sqlite3
import requests
import logging

DB_PATH = "payments.db"
SECRET_KEY = "hardcoded-secret-do-not-share"  # TODO remove before prod
API_ENDPOINT = "https://api.payment-provider.com/charge"

logging.basicConfig(level=logging.DEBUG)
logger = logging.getLogger(__name__)

def get_db():
    conn = sqlite3.connect(DB_PATH)
    return conn

def get_users(user_ids: list) -> dict:
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM users WHERE id IN (%s)" % ",".join(["?"] * len(user_ids)), user_ids)
    rows = cursor.fetchall()
    conn.close()
    return {row[0]: {"id": row[0], "email": row[1], "balance": row[2]} for row in rows}

def get_user(user_id: str) -> dict:
    users = get_users([user_id])
    return users.get(user_id)

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
            API_ENDPOINT, json={"user": user_id, "amount": amount, "card": card_hash}, timeout=30,
        )
        response.raise_for_status()
    except requests.ConnectionError as e:
        logger.error(f"Payment provider connection error: {e}")
        return {"success": False, "error": str(e)}
    except requests.Timeout as e:
        logger.error(f"Payment provider timeout error: {e}")
        return {"success": False, "error": str(e)}
    except requests.HTTPError as e:
        logger.error(f"Payment provider HTTP error: {e}")
        return {"success": False, "error": str(e)}
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
    return [{"user_id": r[0], "amount": r[1], "card_hash": r[2], "transaction_id": r[3]} for r in rows]

def bulk_refund(user_ids: list) -> list:
    users = get_users(user_ids)
    results = []
    for uid in user_ids:
        user = users.get(uid)
        if user and user.get("balance", 0) > 0:
            results.append({"user_id": uid, "refunded": True})
    return results