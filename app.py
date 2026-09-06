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

# Gemini uses the GEMINI_API_KEY environment variable.
api_key = os.environ.get("GEMINI_API_KEY")
gemini = genai.Client(api_key=api_key) if api_key else None


def db():
    return sqlite3.connect(DB)


def setup_database():
    con = db()
    con.execute("""
        CREATE TABLE IF NOT EXISTS users (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            first_name TEXT NOT NULL,
            last_name TEXT NOT NULL,
            username TEXT UNIQUE NOT NULL,
            email TEXT UNIQUE NOT NULL,
            password TEXT NOT NULL
        )
    """)
    con.execute("""
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
    con.commit()
    con.close()


setup_database()


def read_resume(file):
    name = file.filename.lower()
    path = os.path.join(UPLOADS, secure_filename(file.filename))
    file.save(path)

    if name.endswith(".pdf"):
        pdf = PdfReader(path)
        return "\n".join(page.extract_text() or "" for page in pdf.pages)

    if name.endswith(".docx"):
        document = Document(path)
        return "\n".join(p.text for p in document.paragraphs)

    raise ValueError("Please upload a PDF or DOCX resume.")


def analyze(resume, job_title, company, seniority, job_description):
    if not gemini:
        raise ValueError("Gemini API key is not configured.")

    prompt = f"""
Analyze this resume for the job below.

JOB TITLE: {job_title}
COMPANY: {company or 'Not provided'}
SENIORITY: {seniority}
JOB DESCRIPTION:
{job_description or 'Not provided'}

RESUME:
{resume[:30000]}

Return ONLY valid JSON using exactly these fields:
score, ats_score, skills_match, keyword_density, experience_fit,
confirmed_skills, partial_skills, missing_skills, suggestions,
experience_summary, education_summary

Scores must be 0-100 integers.
Skills and suggestions must be lists.
Suggestions must contain 3 practical suggestions.
"""

    response = gemini.models.generate_content(
        model=MODEL,
        contents=prompt
    )

    text = response.text.strip()
    text = text.replace("```json", "").replace("```", "").strip()
    return json.loads(text)


@app.route("/")
def home():
    return redirect(url_for("analyzer" if "user_id" in session else "login"))


@app.route("/login", methods=["GET", "POST"])
def login():
    if request.method == "POST":
        email = request.form["email"].strip().lower()
        password = request.form["password"]

        con = db()
        user = con.execute(
            "SELECT * FROM users WHERE email = ?", (email,)
        ).fetchone()
        con.close()

        if not user:
            return redirect(url_for("not_registered"))

        if not check_password_hash(user[5], password):
            flash("Incorrect email or password.")
            return render_template("login.html")

        session["user_id"] = user[0]
        session["username"] = user[3]
        return redirect(url_for("analyzer"))

    return render_template("login.html")


@app.route("/not-registered")
def not_registered():
    return render_template("not_registered.html")


@app.route("/register", methods=["GET", "POST"])
def register():
    if request.method == "POST":
        first = request.form["first_name"].strip()
        last = request.form["last_name"].strip()
        username = request.form["username"].strip()
        email = request.form["email"].strip().lower()
        password = request.form["password"]
        confirm = request.form["confirm_password"]

        if password != confirm:
            flash("Passwords do not match.")
            return render_template("register.html")

        con = db()
        try:
            con.execute("""
                INSERT INTO users
                (first_name, last_name, username, email, password)
                VALUES (?, ?, ?, ?, ?)
            """, (
                first, last, username, email,
                generate_password_hash(password)
            ))
            con.commit()
        except sqlite3.IntegrityError:
            con.close()
            flash("Email or username is already registered.")
            return render_template("register.html")

        con.close()
        return redirect(url_for("registered"))

    return render_template("register.html")


@app.route("/registered")
def registered():
    return render_template("registered.html")


@app.route("/analyzer", methods=["GET", "POST"])
def analyzer():
    if "user_id" not in session:
        return redirect(url_for("login"))

    if request.method == "POST":
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
            result = analyze(
                resume,
                job_title,
                company,
                seniority,
                job_description
            )
        except Exception as error:
            print(error)
            flash("AI analysis failed. Check your Gemini API key and resume file.")
            return render_template("analyzer.html", page="analyzer")

        con = db()
        cursor = con.execute("""
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
        con.commit()
        history_id = cursor.lastrowid
        con.close()

        return redirect(url_for("report", history_id=history_id))

    return render_template("analyzer.html", page="analyzer")


@app.route("/history")
def history():
    if "user_id" not in session:
        return redirect(url_for("login"))

    con = db()
    rows = con.execute("""
        SELECT * FROM history
        WHERE user_id = ?
        ORDER BY id DESC
    """, (session["user_id"],)).fetchall()
    con.close()

    return render_template("analyzer.html", page="history", history=rows)


@app.route("/profile")
def profile():
    if "user_id" not in session:
        return redirect(url_for("login"))

    con = db()
    user = con.execute(
        "SELECT * FROM users WHERE id = ?",
        (session["user_id"],)
    ).fetchone()
    con.close()

    return render_template("analyzer.html", page="profile", user=user)


@app.route("/report/<int:history_id>")
def report(history_id):
    if "user_id" not in session:
        return redirect(url_for("login"))

    con = db()
    item = con.execute("""
        SELECT * FROM history
        WHERE id = ? AND user_id = ?
    """, (history_id, session["user_id"])).fetchone()
    con.close()

    if not item:
        return redirect(url_for("history"))

    result = json.loads(item[5] or "{}")
    return render_template("report.html", item=item, result=result)


@app.route("/logout")
def logout():
    session.clear()
    return redirect(url_for("login"))


if __name__ == "__main__":
    app.run(debug=True)
