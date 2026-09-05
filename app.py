from flask import Flask, render_template, request, redirect, session
import sqlite3
import os

from werkzeug.security import generate_password_hash, check_password_hash
from google import genai

app = Flask(__name__)

app.secret_key = os.environ.get("SECRET_KEY", "resumeiq-secret-key")

DATABASE = "resumeiq.db"


# -------------------------
# DATABASE
# -------------------------

def get_db():
    conn = sqlite3.connect(DATABASE)
    conn.row_factory = sqlite3.Row
    return conn


def setup_database():

    conn = get_db()

    conn.execute("""
        CREATE TABLE IF NOT EXISTS users (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            email TEXT UNIQUE,
            password TEXT
        )
    """)

    conn.execute("""
        CREATE TABLE IF NOT EXISTS history (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER,
            resume_text TEXT,
            result TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)

    conn.commit()
    conn.close()


setup_database()


# -------------------------
# GEMINI
# -------------------------

def analyze_resume(resume_text):

    api_key = os.environ.get("GEMINI_API_KEY")

    if not api_key:
        return "Gemini API key is missing. Add GEMINI_API_KEY to your environment."

    client = genai.Client(api_key=api_key)

    prompt = f"""
You are ResumeIQ, an AI resume analyzer.

Analyze this resume:

{resume_text}

Give a simple useful report with these sections:

1. Resume Score
2. Strengths
3. Problems
4. Missing Skills
5. ATS Suggestions
6. Job Match Suggestions
7. Final Advice

Keep the answer clear and beginner-friendly.
"""

    response = client.models.generate_content(
        model="gemini-3.6-flash",
        contents=prompt
    )

    return response.text


# -------------------------
# LANDING PAGE
# -------------------------

@app.route("/")
def home():

    if "user_id" in session:
        return redirect("/dashboard")

    return render_template("login.html")


# -------------------------
# REGISTER
# -------------------------

@app.route("/register", methods=["POST"])
def register():

    email = request.form.get("email")
    password = request.form.get("password")

    if not email or not password:
        return render_template(
            "login.html",
            error="Please enter email and password."
        )

    conn = get_db()

    try:

        conn.execute(
            "INSERT INTO users (email, password) VALUES (?, ?)",
            (email, generate_password_hash(password))
        )

        conn.commit()

    except sqlite3.IntegrityError:

        conn.close()

        return render_template(
            "login.html",
            error="Account already exists."
        )

    conn.close()

    return render_template(
        "login.html",
        message="Account created. You can login now."
    )


# -------------------------
# LOGIN
# -------------------------

@app.route("/login", methods=["POST"])
def login():

    email = request.form.get("email")
    password = request.form.get("password")

    conn = get_db()

    user = conn.execute(
        "SELECT * FROM users WHERE email = ?",
        (email,)
    ).fetchone()

    conn.close()

    if user and check_password_hash(user["password"], password):

        session["user_id"] = user["id"]
        session["email"] = user["email"]

        return redirect("/dashboard")

    return render_template(
        "login.html",
        error="Wrong email or password."
    )


# -------------------------
# DASHBOARD
# -------------------------

@app.route("/dashboard", methods=["GET", "POST"])
def dashboard():

    if "user_id" not in session:
        return redirect("/")

    result = None

    if request.method == "POST":

        resume_text = request.form.get("resume_text", "").strip()

        if resume_text:

            result = analyze_resume(resume_text)

            conn = get_db()

            conn.execute(
                """
                INSERT INTO history
                (user_id, resume_text, result)
                VALUES (?, ?, ?)
                """,
                (
                    session["user_id"],
                    resume_text,
                    result
                )
            )

            conn.commit()
            conn.close()

    conn = get_db()

    history = conn.execute(
        """
        SELECT *
        FROM history
        WHERE user_id = ?
        ORDER BY id DESC
        """,
        (session["user_id"],)
    ).fetchall()

    conn.close()

    return render_template(
        "dashboard.html",
        result=result,
        history=history
    )


# -------------------------
# LOGOUT
# -------------------------

@app.route("/logout")
def logout():

    session.clear()

    return redirect("/")


# -------------------------
# RUN
# -------------------------

if __name__ == "__main__":

    app.run(
        debug=True,
        host="0.0.0.0",
        port=5000
    )
