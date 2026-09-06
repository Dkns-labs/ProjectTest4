import os
import json
import sqlite3

from flask import Flask, render_template, request, redirect, url_for, session, flash
from werkzeug.security import generate_password_hash, check_password_hash
from werkzeug.utils import secure_filename
from google import genai
from pypdf import PdfReader
from docx import Document


app = Flask(__name__)
app.secret_key = os.environ.get("SECRET_KEY", "resumeiq-secret-key")
app.config["MAX_CONTENT_LENGTH"] = 10 * 1024 * 1024

DB = "resumeiq.db"
UPLOADS = "uploads"
MODEL = "gemini-3.6-flash"

os.makedirs(UPLOADS, exist_ok=True)


# Gemini API key is directly in app.py for testing.
GEMINI_API_KEY = "AQ.Ab8RN6JBcn4BF-QeuTFhDu-nb5-bg5CChxVbYztfHQjThgoLmw"
gemini = genai.Client(api_key=GEMINI_API_KEY)


def db():
    connection = sqlite3.connect(DB)
    connection.row_factory = sqlite3.Row
    return connection


def setup_database():
    connection = db()

    connection.execute("""
        CREATE TABLE IF NOT EXISTS users (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            first_name TEXT NOT NULL,
            last_name TEXT NOT NULL,
            username TEXT UNIQUE NOT NULL,
            email TEXT UNIQUE NOT NULL,
            password TEXT NOT NULL
        )
    """)

    connection.execute("""
        CREATE TABLE IF NOT EXISTS history (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL,
            job_title TEXT NOT NULL,
            company TEXT,
            score INTEGER,
            report TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)

    connection.commit()
    connection.close()


setup_database()


def read_resume(file):
    filename = secure_filename(file.filename)

    if not filename:
        raise ValueError("Please upload a resume.")

    path = os.path.join(UPLOADS, filename)
    file.save(path)

    if filename.lower().endswith(".pdf"):
        reader = PdfReader(path)
        return "\n".join(page.extract_text() or "" for page in reader.pages)

    if filename.lower().endswith(".docx"):
        document = Document(path)
        return "\n".join(paragraph.text for paragraph in document.paragraphs)

    raise ValueError("Please upload a PDF or DOCX resume.")


def analyze(resume, job_title, company, seniority, job_description):
    prompt = f"""
Analyze this resume for the job below.

JOB TITLE: {job_title}
COMPANY: {company or "Not provided"}
SENIORITY: {seniority}
JOB DESCRIPTION:
{job_description or "Not provided"}

RESUME:
{resume[:30000]}

Return ONLY valid JSON with these fields:
score, ats_score, skills_match, keyword_density, experience_fit,
confirmed_skills, partial_skills, missing_skills, suggestions,
experience_summary, education_summary

Scores must be integers from 0 to 100.
Skills and suggestions must be lists.
Suggestions must contain 3 practical suggestions.
"""

    response = gemini.models.generate_content(
        model=MODEL,
        contents=prompt,
        config={
            "response_mime_type": "application/json"
        }
    )

    text = (response.text or "").strip()
    text = text.replace("```json", "").replace("```", "").strip()

    if not text:
        raise ValueError("Gemini returned an empty response.")

    return json.loads(text)


def logged_in():
    return "user_id" in session


@app.route("/")
def home():
    return redirect(url_for("analyzer" if logged_in() else "login"))


@app.route("/login", methods=["GET", "POST"])
def login():
    if request.method == "GET":
        return render_template("login.html")

    email = request.form["email"].strip().lower()
    password = request.form["password"]

    connection = db()
    user = connection.execute(
        "SELECT * FROM users WHERE email = ?",
        (email,)
    ).fetchone()
    connection.close()

    if not user:
        return redirect(url_for("not_registered"))

    if not check_password_hash(user["password"], password):
        flash("Incorrect email or password.")
        return render_template("login.html")

    session["user_id"] = user["id"]
    session["username"] = user["username"]

    return redirect(url_for("analyzer"))


@app.route("/not-registered")
def not_registered():
    return render_template("not_registered.html")


@app.route("/register", methods=["GET", "POST"])
def register():
    if request.method == "GET":
        return render_template("register.html")

    first = request.form["first_name"].strip()
    last = request.form["last_name"].strip()
    username = request.form["username"].strip()
    email = request.form["email"].strip().lower()
    password = request.form["password"]
    confirm = request.form["confirm_password"]

    if password != confirm:
        flash("Passwords do not match.")
        return render_template("register.html")

    connection = db()

    try:
        connection.execute("""
            INSERT INTO users
            (first_name, last_name, username, email, password)
            VALUES (?, ?, ?, ?, ?)
        """, (
            first,
            last,
            username,
            email,
            generate_password_hash(password)
        ))

        connection.commit()

    except sqlite3.IntegrityError:
        connection.close()
        flash("Email or username is already registered.")
        return render_template("register.html")

    connection.close()
    return redirect(url_for("registered"))


@app.route("/registered")
def registered():
    return render_template("registered.html")


@app.route("/analyzer", methods=["GET", "POST"])
def analyzer():
    if not logged_in():
        return redirect(url_for("login"))

    if request.method == "GET":
        return render_template("analyzer.html", page="analyzer")

    job_title = request.form["job_title"].strip()
    company = request.form.get("company", "").strip()
    seniority = request.form.get("seniority", "")
    job_description = request.form.get("job_description", "")
    resume_file = request.files.get("resume")

    if not resume_file or not resume_file.filename:
        flash("Please upload your resume.")
        return render_template("analyzer.html", page="analyzer")

    try:
        resume = read_resume(resume_file)

        if not resume.strip():
            raise ValueError("No readable text was found in the resume.")

        result = analyze(
            resume,
            job_title,
            company,
            seniority,
            job_description
        )

    except Exception as error:
        print("AI analysis error:", repr(error))
        flash("AI analysis failed. Please try again.")
        return render_template("analyzer.html", page="analyzer")

    connection = db()

    cursor = connection.execute("""
        INSERT INTO history
        (user_id, job_title, company, score, report)
        VALUES (?, ?, ?, ?, ?)
    """, (
        session["user_id"],
        job_title,
        company,
        int(result.get("score", 0)),
        json.dumps(result)
    ))

    connection.commit()
    history_id = cursor.lastrowid
    connection.close()

    return redirect(url_for("report", history_id=history_id))


@app.route("/history")
def history():
    if not logged_in():
        return redirect(url_for("login"))

    connection = db()

    rows = connection.execute("""
        SELECT *
        FROM history
        WHERE user_id = ?
        ORDER BY id DESC
    """, (session["user_id"],)).fetchall()

    connection.close()

    return render_template(
        "analyzer.html",
        page="history",
        history=rows
    )


@app.route("/profile")
def profile():
    if not logged_in():
        return redirect(url_for("login"))

    connection = db()

    user = connection.execute(
        "SELECT * FROM users WHERE id = ?",
        (session["user_id"],)
    ).fetchone()

    connection.close()

    return render_template(
        "analyzer.html",
        page="profile",
        user=user
    )


@app.route("/report/<int:history_id>")
def report(history_id):
    if not logged_in():
        return redirect(url_for("login"))

    connection = db()

    item = connection.execute("""
        SELECT *
        FROM history
        WHERE id = ? AND user_id = ?
    """, (
        history_id,
        session["user_id"]
    )).fetchone()

    connection.close()

    if not item:
        return redirect(url_for("history"))

    result = json.loads(item["report"] or "{}")

    return render_template(
        "report.html",
        item=item,
        result=result
    )


@app.route("/logout")
def logout():
    session.clear()
    return redirect(url_for("login"))


if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port)
