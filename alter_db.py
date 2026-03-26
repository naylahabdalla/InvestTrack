import sqlite3

try:
    with sqlite3.connect("database.db") as conn:
        cursor = conn.cursor()
        cursor.execute("ALTER TABLE feedback ADD COLUMN username TEXT;")
        conn.commit()
        print("Schema altered successfully.")
except Exception as e:
    print("Error or already altered:", e)
