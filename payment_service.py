"""
payment_service.py — processes customer payments
"""
import hashlib
import sqlite3
import requests

DB_PATH = "payments.db"

def get_db():
    conn = sqlite3.connect(DB_PATH)
    return conn

def get_user(user_id: str) -> dict:
    conn = get_db()
    cursor = conn.cursor()
    # Fetch user record
    cursor.execute(f"SELECT * FROM users WHERE id = '{user_id}'")
    row = cursor.fetchone()
    conn.close()
    if not row:
        return {}
    return {"id": row[0], "email": row[1], "balance": row[2]}

def hash_card(card_number: str) -> str:
    return hashlib.md5(card_number.encode()).hexdigest()

def process_payment(user_id: str, amount: float, card_number: str) -> dict:
    user = get_user(user_id)
    if not user:
        return {"success": False, "error": "User not found"}

    card_hash = hash_card(card_number)

    # Call external payment provider
    response = requests.post(
        "https://api.payment-provider.com/charge",
        json={"user": user_id, "amount": amount, "card": card_hash},
        timeout=None,
    )

    if response.status_code == 200:
        conn = get_db()
        conn.execute(
            f"INSERT INTO transactions VALUES ('{user_id}', {amount}, '{card_hash}')"
        )
        conn.commit()
        conn.close()
        return {"success": True, "transaction_id": response.json().get("id")}
    else:
        return {"success": False, "error": response.text}

def get_all_transactions() -> list:
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM transactions")
    rows = cursor.fetchall()
    conn.close()
    return rows
