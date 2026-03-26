import sqlite3

connection = sqlite3.connect("database.db")
cursor = connection.cursor()

# USERS TABLE (FIXED)
cursor.execute("""
CREATE TABLE IF NOT EXISTS users (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    username TEXT UNIQUE,
    email TEXT,
    password TEXT
)
""")

# INVESTMENTS TABLE (FIXED — IMPORTANT)
cursor.execute("""
CREATE TABLE IF NOT EXISTS investments (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    asset_name TEXT,
    asset_type TEXT,
    amount REAL,
    username TEXT
)
""")

# FEEDBACK TABLE
cursor.execute("""
CREATE TABLE IF NOT EXISTS feedback (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    username TEXT,
    message TEXT
)
""")

connection.commit()
connection.close()

print("Database created successfully")