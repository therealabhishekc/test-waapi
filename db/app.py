from dotenv import load_dotenv
from sqlalchemy import create_engine, text
import os

load_dotenv()  # reads .env

DB_HOST = os.getenv("DB_HOST")
DB_PORT = os.getenv("DB_PORT")
DB_USER = os.getenv("DB_USER")
DB_PASS = os.getenv("DB_PASS")
DB_NAME = os.getenv("DB_NAME")

DATABASE_URL = f"mysql+pymysql://{DB_USER}:{DB_PASS}@{DB_HOST}:{DB_PORT}/{DB_NAME}"

engine = create_engine(DATABASE_URL, pool_pre_ping=True)

with engine.connect() as conn:
    print("✅ Connected!")
    print("Server time:", conn.execute(text("SELECT NOW();")).scalar())

