# University Holographic Leaderboard

Flask website with a holographic leaderboard design, batch filters, secure admin login, spreadsheet import, separate assessment rankings, and combined overall rankings.

## Run locally (Windows)

1. Install Python 3.11 or newer.
2. Open Command Prompt in this folder.
3. Create an environment:
   ```bat
   py -m venv .venv
   .venv\Scripts\activate
   pip install -r requirements.txt
   ```
4. Copy `.env.example` to `.env` and change `ADMIN_PASSWORD` and `SECRET_KEY`.
5. Start:
   ```bat
   python app.py
   ```
6. Visit `http://127.0.0.1:5000`; admin login is at `/admin/login`.

## Spreadsheet columns

Required: student name, roll number (or email), score/marks. Optional: accuracy, time taken, tab switches. Example headers accepted include `Name`, `Student Name`, `Roll No`, `USN`, `Score`, `Marks`, `Accuracy`, `Time Taken`, `Tab Switches`.

Use the same roll number consistently across assessments. To update a report, upload it again with the same academic year, department, branch, batch and assessment name.

## Important before public deployment

This package currently uses SQLite for easy local testing. **Do not deploy this exact database configuration for real university data on a free Render web service**: Render free services have an ephemeral filesystem, and local SQLite data can be lost when the service restarts, spins down or redeploys. Render's free Postgres database also expires after 30 days. Use a persistent external PostgreSQL database and adapt the database layer before using it for real results. Keep student fields private and publish only what students are allowed to see.

## Render overview

Render supports Flask/Gunicorn. Push this project to a GitHub repository, create a Render Web Service from it, use build command `pip install -r requirements.txt` and start command `gunicorn app:app`, then set `SECRET_KEY`, `ADMIN_USERNAME`, and `ADMIN_PASSWORD` in Render's environment settings. The app URL is created by Render. Free web services may sleep when idle.

This is a deployable starter project, not already hosted; no public URL is created until you deploy it in your own hosting account.
