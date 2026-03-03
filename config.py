import os

DATABASE_URL = os.getenv("DATABASE_URL", "sqlite:///db.sqlite3")
SECRET = "supersecret123"
DEBUG = True
