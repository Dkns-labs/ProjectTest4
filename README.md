# ResumeIQ - Flask + SQLite + Gemini AI

ResumeIQ is a basic Flask application using HTML, CSS, SQLite and Gemini AI.

## Why Netlify was removed

This project uses Flask/Python for the backend. Netlify Functions do not provide a Python serverless runtime, so a Flask app cannot be deployed there as a Python Function. The previous Netlify setup therefore resulted in the Netlify 404 page.

This version is configured for Render, which supports Flask/Python web services.

## Install locally

```bash
pip install -r requirements.txt
```

## Gemini API key

Set `GEMINI_API_KEY` as an environment variable.

Windows PowerShell:

```powershell
$env:GEMINI_API_KEY="YOUR_GEMINI_API_KEY"
python app.py
```

Linux/macOS:

```bash
export GEMINI_API_KEY="YOUR_GEMINI_API_KEY"
python app.py
```

## Run locally

```bash
python app.py
```

## Render deployment

Create a **Web Service** and connect this project/repository.

Use:

- Runtime: Python 3
- Build Command: `pip install -r requirements.txt`
- Start Command: `gunicorn app:app`

Add these environment variables in Render:

- `GEMINI_API_KEY` = your Gemini API key
- `SECRET_KEY` = any long random secret string

Render's Flask deployment documentation uses the same basic `pip install -r requirements.txt` and `gunicorn app:app` setup.

## Features

- Register and login
- Account-not-registered message
- Password hashing
- CSS-only three-bar menu
- Profile
- History
- Logout
- SQLite history
- PDF and DOCX resume reading
- Gemini AI analysis
- AI-generated report
- No JavaScript required
