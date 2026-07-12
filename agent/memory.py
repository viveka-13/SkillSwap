import sqlite3
import os
import chromadb

SQLITE_PATH = os.path.join(os.path.dirname(__file__), "..", "data", "hyperlocal.db")
CHROMA_PATH = os.path.join(os.path.dirname(__file__), "..", "data", "chroma_db")

os.makedirs(os.path.dirname(SQLITE_PATH), exist_ok=True)

# ChromaDB Init
chroma_client = chromadb.PersistentClient(path=CHROMA_PATH)
try:
    skills_collection = chroma_client.get_collection("skills")
except:
    skills_collection = chroma_client.create_collection("skills")

try:
    profiles_collection = chroma_client.get_collection("profiles")
except:
    profiles_collection = chroma_client.create_collection("profiles")

def init_db():
    conn = sqlite3.connect(SQLITE_PATH, timeout=20.0)
    conn.execute('pragma journal_mode=wal')
    c = conn.cursor()
    c.executescript("""
        CREATE TABLE IF NOT EXISTS Users (
            id TEXT PRIMARY KEY,
            name TEXT,
            email TEXT UNIQUE,
            password_hash TEXT,
            phone TEXT,
            profile_pic TEXT,
            city TEXT,
            lat REAL,
            lon REAL,
            bio TEXT,
            trust_score REAL DEFAULT 0,
            wallet_balance INTEGER DEFAULT 10,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        );
        CREATE TABLE IF NOT EXISTS Skills (
            id TEXT PRIMARY KEY,
            user_id TEXT,
            skill_name TEXT,
            type TEXT, -- 'offered' or 'needed'
            FOREIGN KEY (user_id) REFERENCES Users(id)
        );
        CREATE TABLE IF NOT EXISTS Matches (
            id TEXT PRIMARY KEY,
            user1_id TEXT,
            user2_id TEXT,
            compatibility_score REAL,
            ai_reasoning TEXT,
            status TEXT DEFAULT 'pending', -- 'pending', 'accepted', 'rejected'
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        );
        CREATE TABLE IF NOT EXISTS Messages (
            id TEXT PRIMARY KEY,
            match_id TEXT,
            sender_id TEXT,
            content TEXT,
            is_flagged BOOLEAN DEFAULT 0,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        );
        CREATE TABLE IF NOT EXISTS ExchangeHistory (
            id TEXT PRIMARY KEY,
            match_id TEXT,
            completed_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            credits_transferred INTEGER
        );
        CREATE TABLE IF NOT EXISTS Ratings (
            id TEXT PRIMARY KEY,
            exchange_id TEXT,
            reviewer_id TEXT,
            reviewee_id TEXT,
            rating INTEGER,
            review_text TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        );
        CREATE TABLE IF NOT EXISTS CommunityFeed (
            id TEXT PRIMARY KEY,
            user_id TEXT,
            content TEXT,
            post_type TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        );
        CREATE TABLE IF NOT EXISTS Notifications (
            id TEXT PRIMARY KEY,
            user_id TEXT,
            content TEXT,
            is_read BOOLEAN DEFAULT 0,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        );
    """)
    conn.commit()
    conn.close()

init_db()

def _get_conn():
    # Increase timeout significantly and use WAL mode to handle concurrency better
    conn = sqlite3.connect(SQLITE_PATH, timeout=20.0)
    conn.execute('pragma journal_mode=wal')
    return conn

def run_query(query: str, params: tuple = ()):
    conn = _get_conn()
    c = conn.cursor()
    c.execute(query, params)
    conn.commit()
    lastrowid = c.lastrowid
    conn.close()
    return lastrowid

def fetch_query(query: str, params: tuple = ()):
    conn = _get_conn()
    conn.row_factory = sqlite3.Row
    c = conn.cursor()
    c.execute(query, params)
    rows = [dict(row) for row in c.fetchall()]
    conn.close()
    return rows
