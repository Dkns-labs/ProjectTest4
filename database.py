import sqlite3

db = "resumeiq.db"


def connect():
    return sqlite3.connect(db)


def setup():
    con = connect()

    con.execute("""
        CREATE TABLE IF NOT EXISTS users (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            email TEXT UNIQUE,
            password TEXT
        )
    """)

    con.execute("""
        CREATE TABLE IF NOT EXISTS history (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER,
            resume TEXT,
            result TEXT
        )
    """)

    con.commit()
    con.close()
