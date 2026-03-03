import hashlib
import sqlite3
import requests
import logging
import os
from cryptography.fernet import Fernet

DB_PATH = "payments.db"
API_ENDPOINT = "https://api.payment-provider.com/charge"

ENCRYPTED_SECRET_KEY = os.getenv('ENCRYPTED_SECRET_KEY')
if ENCRYPTED_SECRET_KEY is None:
    raise ValueError("ENCRYPTED_SECRET_KEY environment variable is not set")

ENCRYPTION_KEY = os.getenv('ENCRYPTION_KEY')
if ENCRYPTION_KEY is None:
    raise ValueError("ENCRYPTION_KEY environment variable is not set")

fernet = Fernet(ENCRYPTION_KEY.encode())
SECRET_KEY = fernet.decrypt(ENCRYPTED_SECRET_KEY.encode()).decode()

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
        query = "SELECT * FROM users WHERE id = ?"
        params = (user_id,)
        cursor.execute(query, params)
        row = cursor.fetchone()
        conn.close()
        if row is None:
            return {}
        return {
            "id": row[0],
            "name": row[1],
            "email": row[2]
        }
    except sqlite3.Error as e:
        logger.error(f"Database query error: {e}")
        raise

def get_users_from_db(user_ids: list) -> list:
    try:
        conn = get_db()
        cursor = conn.cursor()
        placeholders = ",".join(["?"] * len(user_ids))
        query = "SELECT * FROM users WHERE id IN (%s)" % placeholders
        params = user_ids
        cursor.execute(query, params)
        rows = cursor.fetchall()
        conn.close()
        return [
            {
                "id": row[0],
                "name": row[1],
                "email": row[2]
            } for row in rows
        ]
    except sqlite3.Error as e:
        logger.error(f"Database query error: {e}")
        raise

def get_all_users_from_db() -> list:
    try:
        conn = get_db()
        cursor = conn.cursor()
        query = "SELECT * FROM users"
        cursor.execute(query)
        rows = cursor.fetchall()
        conn.close()
        return [
            {
                "id": row[0],
                "name": row[1],
                "email": row[2]
            } for row in rows
        ]
    except sqlite3.Error as e:
        logger.error(f"Database query error: {e}")
        raise

def charge_user(user_id: str, amount: float) -> bool:
    try:
        user = get_user_from_db(user_id)
        if not user:
            logger.error(f"User not found: {user_id}")
            return False
        response = requests.post(API_ENDPOINT, json={
            "user_id": user_id,
            "amount": amount
        }, headers={
            "Authorization": f"Bearer {SECRET_KEY}"
        })
        if response.status_code != 200:
            logger.error(f"Payment provider API error: {response.text}")
            return False
        return True
    except requests.RequestException as e:
        logger.error(f"Payment provider API request error: {e}")
        raise

def refund_user(user_id: str) -> bool:
    try:
        user = get_user_from_db(user_id)
        if not user:
            logger.error(f"User not found: {user_id}")
            return False
        response = requests.post(API_ENDPOINT, json={
            "user_id": user_id,
            "amount": 0.0
        }, headers={
            "Authorization": f"Bearer {SECRET_KEY}"
        })
        if response.status_code != 200:
            logger.error(f"Payment provider API error: {response.text}")
            return False
        return True
    except requests.RequestException as e:
        logger.error(f"Payment provider API request error: {e}")
        raise

def bulk_refund(user_ids: list, chunk_size: int = 100) -> None:
    try:
        users = get_users_from_db(user_ids)
        for i in range(0, len(users), chunk_size):
            chunk = users[i:i + chunk_size]
            for user in chunk:
                refund_user(user["id"])
    except Exception as e:
        logger.error(f"Error during bulk refund: {e}")
        raise

def main():
    user_id = "example_user_id"
    amount = 10.99
    if charge_user(user_id, amount):
        logger.info(f"User charged successfully: {user_id}")
    else:
        logger.error(f"Failed to charge user: {user_id}")
    bulk_refund([user_id])

if __name__ == "__main__":
    main()