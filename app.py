import json
import os
import sqlite3

from docx import Document
from flask import Flask, flash, redirect, render_template, request, session, url_for
from google import genai
from pypdf import PdfReader
from werkzeug.security import check_password_hash, generate_password_hash
from werkzeug.utils import secure_filename


app = Flask(__name__)
app.secret_key = os.environ["SECRET_KEY"]

DATABASE = "resumeiq.db"
UPLOAD_FOLDER = "uploads"
ALLOWED_EXTENSIONS = {"pdf", "docx"}

GEMINI_API_KEY = os.environ.get("GEMINI_API_KEY")
GEMINI_MODEL = os.environ.get("GEMINI_MODEL", "gemini-3.6-flash")

os.makedirs(UPLOAD_FOLDER, exist_ok=True)


def get_db():
    db = sqlite3.connect(DATABASE)
    db.row_factory = sqlite3.Row
    return db


def create_tables():
    with get_db() as db:
        db.execute(
            """
            CREATE TABLE IF NOT EXISTS users (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                first_name TEXT NOT NULL,
                last_name TEXT NOT NULL,
                username TEXT UNIQUE NOT NULL,
                email TEXT UNIQUE NOT NULL,
                password TEXT NOT NULL
            )
            """
        )
        db.execute(
            """
            CREATE TABLE IF NOT EXISTS history (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER NOT NULL,
                job_title TEXT,
                company TEXT,
                score INTEGER,
                report TEXT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
            """
        )


def logged_in():
    return "user_id" in session


def allowed_file(filename):
    return "." in filename and filename.rsplit(".", 1)[1].lower() in ALLOWED_EXTENSIONS


def read_resume(upload):
    filename = secure_filename(upload.filename or "")

    if not filename:
        raise ValueError("Please select a resume.")

    if not allowed_file(filename):
        raise ValueError("Only PDF and DOCX files are supported.")

    path = os.path.join(UPLOAD_FOLDER, filename)
    upload.save(path)

    if filename.lower().endswith(".pdf"):
        reader = PdfReader(path)
        return "\n".join(page.extract_text() or "" for page in reader.pages)

    document = Document(path)
    return "\n".join(paragraph.text for paragraph in document.paragraphs)


def analyze_resume(resume, job_title, company, seniority, job_description):
    if not GEMINI_API_KEY:
        raise RuntimeError("GEMINI_API_KEY is not configured.")

    prompt = f"""
You are an ATS resume analyzer.

Job title: {job_title}
Company: {company}
Seniority: {seniority}

Job description:
{job_description}

Resume:
{resume[:30000]}

Return ONLY valid JSON with these fields:
score, ats_score, skills_match, keyword_density, experience_fit,
confirmed_skills, partial_skills, missing_skills, suggestions,
experience_summary, education_summary.

All scores must be numbers from 0 to 100.
Suggestions must contain exactly 3 items.
"""

    client = genai.Client(api_key=GEMINI_API_KEY)
    response = client.models.generate_content(
        model=GEMINI_MODEL,
        contents=prompt,
    )

    text = response.text.strip()
    text = text.replace("```json", "").replace("```", "").strip()
    return json.loads(text)


@app.route("/")
def home():
    if logged_in():
        return redirect(url_for("analyzer"))
    return render_template("index.html")


@app.route("/login", methods=["GET", "POST"])
def login():
    if request.method == "GET":
        return render_template("login.html")

    email = request.form.get("email", "").strip().lower()
    password = request.form.get("password", "")

    with get_db() as db:
        user = db.execute(
            "SELECT * FROM users WHERE email = ?",
            (email,),
        ).fetchone()

    if user is None:
        return redirect(url_for("not_registered"))

    if not check_password_hash(user["password"], password):
        flash("Incorrect email or password.")
        return redirect(url_for("login"))

    session["user_id"] = user["id"]
    session["username"] = user["username"]
    return redirect(url_for("analyzer"))


@app.route("/register", methods=["GET", "POST"])
def register():
    if request.method == "GET":
        return render_template("register.html")

    first_name = request.form.get("first_name", "").strip()
    last_name = request.form.get("last_name", "").strip()
    username = request.form.get("username", "").strip()
    email = request.form.get("email", "").strip().lower()
    password = request.form.get("password", "")
    confirm_password = request.form.get("confirm_password", "")

    if password != confirm_password:
        flash("Passwords do not match.")
        return redirect(url_for("register"))

    try:
        with get_db() as db:
            db.execute(
                """
                INSERT INTO users
                    (first_name, last_name, username, email, password)
                VALUES (?, ?, ?, ?, ?)
                """,
                (
                    first_name,
                    last_name,
                    username,
                    email,
                    generate_password_hash(password),
                ),
            )
    except sqlite3.IntegrityError:
        flash("Username or email is already registered.")
        return redirect(url_for("register"))

    return redirect(url_for("registered"))


@app.route("/registered")
def registered():
    return render_template("registered.html")


@app.route("/not-registered")
def not_registered():
    return render_template("not_registered.html")


@app.route("/analyzer", methods=["GET", "POST"])
def analyzer():
    if not logged_in():
        return redirect(url_for("login"))

    if request.method == "GET":
        return render_template("analyzer.html", page="analyzer")

    job_title = request.form.get("job_title", "").strip()
    company = request.form.get("company", "").strip()
    seniority = request.form.get("seniority", "").strip()
    job_description = request.form.get("job_description", "").strip()
    resume_file = request.files.get("resume")

    if not resume_file or not resume_file.filename:
        flash("Please upload a PDF or DOCX resume.")
        return redirect(url_for("analyzer"))

    try:
        resume = read_resume(resume_file)
        if not resume.strip():
            raise ValueError("No readable text was found in the resume.")

        result = analyze_resume(
            resume,
            job_title,
            company,
            seniority,
            job_description,
        )
    except Exception as error:
        app.logger.exception("Resume analysis failed: %s", error)
        flash("Analysis failed. Check your API configuration and resume file.")
        return redirect(url_for("analyzer"))

    with get_db() as db:
        cursor = db.execute(
            """
            INSERT INTO history
                (user_id, job_title, company, score, report)
            VALUES (?, ?, ?, ?, ?)
            """,
            (
                session["user_id"],
                job_title,
                company,
                int(result.get("score", 0)),
                json.dumps(result),
            ),
        )
        history_id = cursor.lastrowid

    return redirect(url_for("report", history_id=history_id))


@app.route("/history")
def history():
    if not logged_in():
        return redirect(url_for("login"))

    with get_db() as db:
        records = db.execute(
            """
            SELECT id, job_title, company, score, created_at
            FROM history
            WHERE user_id = ?
            ORDER BY id DESC
            """,
            (session["user_id"],),
        ).fetchall()

    return render_template("analyzer.html", page="history", history=records)


@app.route("/profile")
def profile():
    if not logged_in():
        return redirect(url_for("login"))

    with get_db() as db:
        user = db.execute(
            """
            SELECT first_name, last_name, username, email
            FROM users
            WHERE id = ?
            """,
            (session["user_id"],),
        ).fetchone()

    return render_template("analyzer.html", page="profile", user=user)


@app.route("/report/<int:history_id>")
def report(history_id):
    if not logged_in():
        return redirect(url_for("login"))

    with get_db() as db:
        item = db.execute(
            """
            SELECT id, job_title, company, score, report, created_at
            FROM history
            WHERE id = ? AND user_id = ?
            """,
            (history_id, session["user_id"]),
        ).fetchone()

    if item is None:
        return redirect(url_for("history"))

    result = json.loads(item["report"] or "{}")
    return render_template("report.html", item=item, result=result)


@app.route("/logout")
def logout():
    session.clear()
    return redirect(url_for("login"))


create_tables()


if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port)
