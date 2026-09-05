from flask import Flask, render_template, request, redirect, session
from werkzeug.security import generate_password_hash, check_password_hash
from google import genai
import sqlite3
import os

from database import setup


app = Flask(__name__)

app.secret_key = "resumeiq-secret-key"

setup()


# HOME
@app.route("/")
def home():
    if "user_id" in session:
        return redirect("/dashboard")

    return render_template("login.html")


# REGISTER
@app.route("/register", methods=["POST"])
def register():

    email = request.form["email"]
    password = request.form["password"]

    con = sqlite3.connect("resumeiq.db")

    try:
        con.execute(
            "INSERT INTO users (email, password) VALUES (?, ?)",
            (
                email,
                generate_password_hash(password)
            )
        )

        con.commit()

    except:
        con.close()

        return render_template(
            "login.html",
            error="Account already exists."
        )

    con.close()

    return render_template(
        "login.html",
        message="Account created!"
    )


# LOGIN
@app.route("/login", methods=["POST"])
def login():

    email = request.form["email"]
    password = request.form["password"]

    con = sqlite3.connect("resumeiq.db")

    user = con.execute(
        "SELECT * FROM users WHERE email = ?",
        (email,)
    ).fetchone()

    con.close()

    if user and check_password_hash(
        user[2],
        password
    ):

        session["user_id"] = user[0]
        session["email"] = user[1]

        return redirect("/dashboard")

    return render_template(
        "login.html",
        error="Wrong email or password."
    )


# AI
def analyze(resume):

    key = os.environ.get("GEMINI_API_KEY")

    if not key:
        return "Gemini API key missing."

    ai = genai.Client(api_key=key)

    response = ai.models.generate_content(
        model=os.environ.get(
            "GEMINI_MODEL",
            "gemini-3-flash-preview"
        ),
        contents=f"""
Analyze this resume.

Give:
1. Resume Score
2. Strengths
3. Problems
4. Missing Skills
5. ATS Suggestions
6. Job Match
7. Final Advice

Resume:

{resume}
"""
    )

    return response.text


# DASHBOARD
@app.route("/dashboard", methods=["GET", "POST"])
def dashboard():

    if "user_id" not in session:
        return redirect("/")

    result = None

    if request.method == "POST":

        resume = request.form["resume_text"]

        result = analyze(resume)

        con = sqlite3.connect("resumeiq.db")

        con.execute(
            """
            INSERT INTO history
            (user_id, resume, result)
            VALUES (?, ?, ?)
            """,
            (
                session["user_id"],
                resume,
                result
            )
        )

        con.commit()
        con.close()


    con = sqlite3.connect("resumeiq.db")

    history = con.execute(
        """
        SELECT * FROM history
        WHERE user_id = ?
        ORDER BY id DESC
        """,
        (session["user_id"],)
    ).fetchall()

    con.close()


    return render_template(
        "dashboard.html",
        result=result,
        history=history
    )


# LOGOUT
@app.route("/logout")
def logout():

    session.clear()

    return redirect("/")


app.run(debug=True)
