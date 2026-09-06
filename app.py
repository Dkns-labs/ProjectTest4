import os
import json
import sqlite3

from flask import Flask, render_template, request, redirect, url_for, session, flash
from werkzeug.security import generate_password_hash, check_password_hash
from werkzeug.utils import secure_filename

from google import genai
from pypdf import PdfReader
from docx import Document

import config


# -----------------------------
# FLASK
# -----------------------------

app = Flask(__name__)

app.secret_key = config.SECRET_KEY

DATABASE = "resumeiq.db"
UPLOAD_FOLDER = "uploads"

os.makedirs(UPLOAD_FOLDER, exist_ok=True)


# -----------------------------
# DATABASE
# -----------------------------

def database():
    return sqlite3.connect(DATABASE)


def create_database():

    db = database()

    db.execute("""
        CREATE TABLE IF NOT EXISTS users (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            first_name TEXT,
            last_name TEXT,
            username TEXT UNIQUE,
            email TEXT UNIQUE,
            password TEXT
        )
    """)

    db.execute("""
        CREATE TABLE IF NOT EXISTS history (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER,
            job_title TEXT,
            company TEXT,
            score INTEGER,
            ai_report TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)

    db.commit()
    db.close()


create_database()


# -----------------------------
# GEMINI
# -----------------------------

gemini = genai.Client(
    api_key=config.GEMINI_API_KEY.strip()
)

MODEL = config.GEMINI_MODEL


# -----------------------------
# LOGIN CHECK
# -----------------------------

def logged_in():
    return "user_id" in session


# -----------------------------
# READ RESUME
# -----------------------------

def read_resume(file):

    filename = secure_filename(file.filename)

    if not filename:
        raise ValueError("Invalid file name.")

    path = os.path.join(
        UPLOAD_FOLDER,
        filename
    )

    file.save(path)

    if filename.lower().endswith(".pdf"):

        pdf = PdfReader(path)

        text = ""

        for page in pdf.pages:
            text += page.extract_text() or ""

        return text

    if filename.lower().endswith(".docx"):

        document = Document(path)

        text = ""

        for paragraph in document.paragraphs:
            text += paragraph.text + "\n"

        return text

    raise ValueError(
        "Please upload a PDF or DOCX file."
    )


# -----------------------------
# GEMINI ANALYSIS
# -----------------------------

def analyze_resume(
    resume,
    job_title,
    company,
    seniority,
    job_description
):

    prompt = f"""
Analyze this resume for the job below.

Job Title:
{job_title}

Company:
{company}

Seniority Level:
{seniority}

Job Description:
{job_description}

Resume:
{resume[:30000]}

Return ONLY valid JSON.

Use exactly these fields:

score
ats_score
skills_match
keyword_density
experience_fit
confirmed_skills
partial_skills
missing_skills
suggestions
experience_summary
education_summary

Scores must be numbers from 0 to 100.

confirmed_skills, partial_skills and missing_skills
must be lists.

suggestions must contain 3 suggestions.
"""

    response = gemini.models.generate_content(
        model=MODEL,
        contents=prompt
    )

    text = response.text.strip()

    text = text.replace("```json", "")
    text = text.replace("```", "")

    return json.loads(text)


# -----------------------------
# HOME
# -----------------------------

@app.route("/")
def home():

    if logged_in():
        return redirect(url_for("analyzer"))

    return redirect(url_for("login"))


# -----------------------------
# LOGIN
# -----------------------------

@app.route("/login", methods=["GET", "POST"])
def login():

    if request.method == "POST":

        email = request.form.get(
            "email",
            ""
        ).strip().lower()

        password = request.form.get(
            "password",
            ""
        )

        db = database()

        user = db.execute(
            """
            SELECT *
            FROM users
            WHERE email = ?
            """,
            (email,)
        ).fetchone()

        db.close()

        if not user:

            return redirect(
                url_for("not_registered")
            )

        if not check_password_hash(
            user[5],
            password
        ):

            flash(
                "Incorrect email or password."
            )

            return redirect(
                url_for("login")
            )

        session["user_id"] = user[0]
        session["username"] = user[3]

        return redirect(
            url_for("analyzer")
        )

    return render_template("login.html")


# -----------------------------
# NOT REGISTERED
# -----------------------------

@app.route("/not-registered")
def not_registered():

    return render_template(
        "not_registered.html"
    )


# -----------------------------
# REGISTER
# -----------------------------

@app.route("/register", methods=["GET", "POST"])
def register():

    if request.method == "POST":

        first_name = request.form.get(
            "first_name",
            ""
        ).strip()

        last_name = request.form.get(
            "last_name",
            ""
        ).strip()

        username = request.form.get(
            "username",
            ""
        ).strip()

        email = request.form.get(
            "email",
            ""
        ).strip().lower()

        password = request.form.get(
            "password",
            ""
        )

        confirm_password = request.form.get(
            "confirm_password",
            ""
        )

        if password != confirm_password:

            flash("Passwords do not match.")

            return redirect(
                url_for("register")
            )

        db = database()

        try:

            db.execute(
                """
                INSERT INTO users
                (
                    first_name,
                    last_name,
                    username,
                    email,
                    password
                )
                VALUES (?, ?, ?, ?, ?)
                """,
                (
                    first_name,
                    last_name,
                    username,
                    email,
                    generate_password_hash(password)
                )
            )

            db.commit()
            db.close()

            return redirect(
                url_for("registered")
            )

        except sqlite3.IntegrityError:

            db.close()

            flash(
                "Email or username is already registered."
            )

            return redirect(
                url_for("register")
            )

    return render_template("register.html")


# -----------------------------
# REGISTERED
# -----------------------------

@app.route("/registered")
def registered():

    return render_template(
        "registered.html"
    )


# -----------------------------
# ANALYZER
# -----------------------------

@app.route(
    "/analyzer",
    methods=["GET", "POST"]
)
def analyzer():

    if not logged_in():

        return redirect(
            url_for("login")
        )

    if request.method == "POST":

        job_title = request.form.get(
            "job_title",
            ""
        ).strip()

        company = request.form.get(
            "company",
            ""
        ).strip()

        seniority = request.form.get(
            "seniority",
            ""
        )

        job_description = request.form.get(
            "job_description",
            ""
        ).strip()

        resume_file = request.files.get(
            "resume"
        )

        if not resume_file or not resume_file.filename:

            flash("Please upload your resume.")

            return redirect(
                url_for("analyzer")
            )

        try:

            resume_text = read_resume(
                resume_file
            )

            result = analyze_resume(
                resume_text,
                job_title,
                company,
                seniority,
                job_description
            )

        except Exception as error:

            print("GEMINI ERROR:", error)

            flash(
                "AI analysis failed. Please check your Gemini API key."
            )

            return redirect(
                url_for("analyzer")
            )

        db = database()

        cursor = db.execute(
            """
            INSERT INTO history
            (
                user_id,
                job_title,
                company,
                score,
                ai_report
            )
            VALUES (?, ?, ?, ?, ?)
            """,
            (
                session["user_id"],
                job_title,
                company,
                result.get("score", 0),
                json.dumps(result)
            )
        )

        history_id = cursor.lastrowid

        db.commit()
        db.close()

        return redirect(
            url_for(
                "report",
                history_id=history_id
            )
        )

    return render_template(
        "analyzer.html",
        page="analyzer"
    )


# -----------------------------
# HISTORY
# -----------------------------

@app.route("/history")
def history():

    if not logged_in():

        return redirect(
            url_for("login")
        )

    db = database()

    history = db.execute(
        """
        SELECT *
        FROM history
        WHERE user_id = ?
        ORDER BY id DESC
        """,
        (session["user_id"],)
    ).fetchall()

    db.close()

    return render_template(
        "analyzer.html",
        page="history",
        history=history
    )


# -----------------------------
# PROFILE
# -----------------------------

@app.route("/profile")
def profile():

    if not logged_in():

        return redirect(
            url_for("login")
        )

    db = database()

    user = db.execute(
        """
        SELECT *
        FROM users
        WHERE id = ?
        """,
        (session["user_id"],)
    ).fetchone()

    db.close()

    return render_template(
        "analyzer.html",
        page="profile",
        user=user
    )


# -----------------------------
# REPORT
# -----------------------------

@app.route("/report/<int:history_id>")
def report(history_id):

    if not logged_in():

        return redirect(
            url_for("login")
        )

    db = database()

    item = db.execute(
        """
        SELECT *
        FROM history
        WHERE id = ?
        AND user_id = ?
        """,
        (
            history_id,
            session["user_id"]
        )
    ).fetchone()

    db.close()

    if not item:

        return redirect(
            url_for("history")
        )

    result = json.loads(
        item[5] or "{}"
    )

    return render_template(
        "report.html",
        item=item,
        result=result
    )


# -----------------------------
# LOGOUT
# -----------------------------

@app.route("/logout")
def logout():

    session.clear()

    return redirect(
        url_for("login")
    )


# -----------------------------
# RUN
# -----------------------------

if __name__ == "__main__":

    app.run(
        host="0.0.0.0",
        port=int(
            os.environ.get(
                "PORT",
                5000
            )
        )
    )
