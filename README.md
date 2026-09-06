# ResumeIQ - Flask + SQLite + Gemini

Basic ResumeIQ application using Flask, SQLite, HTML/CSS and Gemini AI.

## Install

```bash
pip install -r requirements.txt
```

## Gemini API key

Set the environment variable `GEMINI_API_KEY` before starting Flask.

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

The app uses the Gemini model `gemini-3.6-flash`.

## Run

```bash
python app.py
```

Then open the local Flask address shown in the terminal.

## Features

- Register and login
- Account-not-registered message
- Password hashing
- CSS-only three-bar menu after login
- Profile
- Logout
- SQLite analysis history
- PDF and DOCX text extraction
- Gemini AI resume analysis
- AI-generated report
- No JavaScript required

## Netlify

`netlify/functions/api.py` provides the Netlify function wrapper. Set `GEMINI_API_KEY` and `SECRET_KEY` in Netlify environment variables.

SQLite is suitable for local/basic use. A persistent hosted database is recommended for production serverless deployment.
