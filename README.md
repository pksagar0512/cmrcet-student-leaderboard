# CMRCET Holographic Student Leaderboard

A Flask website prototype for CMRCET with a futuristic blue-and-gold glass leaderboard inspired by the supplied visual reference. It supports admin-created custom batches, department/year-based student import, one-batch-per-student enforcement, result uploads, a public batch selector, and separate complete-batch and assessment-specific ranking views.

## Run locally (Windows)

1. Install Python 3.11 or newer.
2. Open Command Prompt in this folder.
3. Create and activate a virtual environment:
   ```bat
   py -m venv .venv
   .venv\Scripts\activate
   pip install -r requirements.txt
   ```
4. Copy `.env.example` to `.env`. Set a strong `SECRET_KEY`, `ADMIN_USERNAME`, and `ADMIN_PASSWORD`.
5. Run `python app.py` and visit `http://127.0.0.1:5000`. Admin login is at `/admin/login`.

## Admin workflow

1. Create a batch name and enter the student year (use consistent values, such as `2nd Year`). Select all departments to include.
2. Upload a student master file containing roll number, student name, department and year. Email and division are optional. Rows are only imported if their department and year match the batch. If a roll number is already assigned to a different batch, it is blocked.
3. Upload assessment results and select that batch. Results must match students already in the batch by roll number (email is a fallback). Re-uploading the same assessment name updates existing scores.
4. Students use the public homepage to select a batch, then choose the complete batch leaderboard or a particular assessment.

Accepted files: `.xlsx`, `.xls`, `.csv` (maximum 12 MB). Common column names such as `Roll No`, `USN`, `Student Name`, `Department`, `Year`, `Score`, `Marks`, `Accuracy`, `Time Taken`, and `Tab Switches` are supported.

## Ranking rules in this prototype

- Assessment-specific rankings sort by score, then accuracy, then student name.
- Complete batch rankings use each student's average percentage across assessments they have taken. If the maximum score is provided for an assessment, score is converted to percentage; otherwise the raw score is used as the displayed value for that assessment. Missing assessments are currently excluded from that student's average.
- Ties are currently broken by accuracy, then name; formal competition-style shared ranks are not yet implemented.

## Before real/public use

This is a test prototype, not yet ready for real student records. It currently uses SQLite and the default database file is local. **Do not deploy this database configuration to Render free hosting for real student data**, because the free service filesystem is ephemeral. Before public launch, configure persistent PostgreSQL storage and review student-data privacy/access rules. Set a stable random `SECRET_KEY` and strong admin credentials in the hosting environment. Do not commit `.env` files or student spreadsheets to GitHub.

## Render settings

Build command: `pip install -r requirements.txt`

Start command: `gunicorn app:app`

Set `SECRET_KEY`, `ADMIN_USERNAME`, and `ADMIN_PASSWORD` in the Render environment settings. Deployment is not performed automatically by this ZIP.
