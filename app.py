import os
import secrets
import sqlite3
from pathlib import Path
from functools import wraps
from datetime import datetime

import pandas as pd
from dotenv import load_dotenv
from flask import Flask, render_template, request, redirect, url_for, session, flash, abort
from flask_wtf.csrf import CSRFProtect
from werkzeug.security import check_password_hash, generate_password_hash

load_dotenv()
BASE = Path(__file__).resolve().parent
DB_PATH = os.getenv("DATABASE_PATH", str(BASE / "leaderboard.db"))
ALLOWED = {"xlsx", "xls", "csv"}

app = Flask(__name__)
app.config.update(
    SECRET_KEY=os.getenv("SECRET_KEY") or secrets.token_hex(32),
    MAX_CONTENT_LENGTH=12 * 1024 * 1024,
    SESSION_COOKIE_HTTPONLY=True,
    SESSION_COOKIE_SAMESITE="Lax",
    SESSION_COOKIE_SECURE=os.getenv("COOKIE_SECURE", "0") == "1",
)
CSRFProtect(app)


def connect():
    con = sqlite3.connect(DB_PATH)
    con.row_factory = sqlite3.Row
    con.execute("PRAGMA foreign_keys=ON")
    return con


def init_db():
    with connect() as con:
        con.executescript("""
        CREATE TABLE IF NOT EXISTS admins(id INTEGER PRIMARY KEY, username TEXT UNIQUE NOT NULL, password_hash TEXT NOT NULL);
        CREATE TABLE IF NOT EXISTS students(
          id INTEGER PRIMARY KEY, roll TEXT NOT NULL, name TEXT NOT NULL, email TEXT DEFAULT '',
          year TEXT NOT NULL, department TEXT NOT NULL, branch TEXT NOT NULL, batch TEXT NOT NULL,
          UNIQUE(roll,year,department,branch,batch));
        CREATE TABLE IF NOT EXISTS assessments(
          id INTEGER PRIMARY KEY, year TEXT NOT NULL, department TEXT NOT NULL, branch TEXT NOT NULL, batch TEXT NOT NULL,
          assessment_name TEXT NOT NULL, max_score REAL, uploaded_at TEXT NOT NULL,
          UNIQUE(year,department,branch,batch,assessment_name));
        CREATE TABLE IF NOT EXISTS results(
          id INTEGER PRIMARY KEY, student_id INTEGER NOT NULL REFERENCES students(id) ON DELETE CASCADE,
          assessment_id INTEGER NOT NULL REFERENCES assessments(id) ON DELETE CASCADE,
          score REAL DEFAULT 0, accuracy REAL, time_taken TEXT DEFAULT '', tab_switches INTEGER,
          UNIQUE(student_id,assessment_id));
        """)
        username, password = os.getenv("ADMIN_USERNAME", "").strip(), os.getenv("ADMIN_PASSWORD", "")
        if username and password and not con.execute("SELECT 1 FROM admins WHERE username=?", (username,)).fetchone():
            con.execute("INSERT INTO admins(username,password_hash) VALUES(?,?)",
                        (username, generate_password_hash(password)))


init_db()


def admin_required(fn):
    @wraps(fn)
    def inner(*args, **kwargs):
        if not session.get("admin_id"):
            return redirect(url_for("login"))
        return fn(*args, **kwargs)
    return inner


def norm(s):
    return "".join(c.lower() for c in str(s) if c.isalnum())


def getval(row, names, default=""):
    cols = {norm(c): c for c in row.index}
    for n in names:
        if norm(n) in cols:
            value = row[cols[norm(n)]]
            if not pd.isna(value) and str(value).strip():
                return value
    # Accept common prefixes/suffixes in export headers.
    for key, col in cols.items():
        if any(key.startswith(norm(n)) for n in names):
            value = row[col]
            if not pd.isna(value) and str(value).strip():
                return value
    return default


def clean(v):
    return "" if pd.isna(v) else str(v).strip()


def num(v, default=None):
    try:
        if v is None or pd.isna(v) or str(v).strip() == "":
            return default
        return float(str(v).replace("%", "").replace(",", "").strip())
    except (ValueError, TypeError):
        return default


def read_sheet(file):
    ext = file.filename.rsplit(".", 1)[-1].lower()
    if ext == "csv":
        return pd.read_csv(file)
    if ext == "xls":
        return pd.read_excel(file, engine="xlrd")
    return pd.read_excel(file, engine="openpyxl")


@app.get("/")
def home():
    with connect() as con:
        years = [r[0] for r in con.execute("SELECT DISTINCT year FROM students ORDER BY year DESC")]
        departments = [r[0] for r in con.execute("SELECT DISTINCT department FROM students ORDER BY department")]
        branches = [r[0] for r in con.execute("SELECT DISTINCT branch FROM students ORDER BY branch")]
        batches = [r[0] for r in con.execute("SELECT DISTINCT batch FROM students ORDER BY batch")]
    return render_template("index.html", years=years, departments=departments, branches=branches, batches=batches)


@app.get("/leaderboard")
def leaderboard():
    year, dept, branch, batch = [request.args.get(k, "").strip() for k in ("year", "department", "branch", "batch")]
    mode = request.args.get("mode", "overall")
    assessment_id = request.args.get("assessment_id", "")
    if not all((year, dept, branch, batch)):
        flash("Select academic year, department, branch and batch.", "warning")
        return redirect(url_for("home"))
    with connect() as con:
        assessments = con.execute("""SELECT * FROM assessments WHERE year=? AND department=? AND branch=? AND batch=?
            ORDER BY uploaded_at, assessment_name""", (year, dept, branch, batch)).fetchall()
        if mode not in ("overall", "assessment"):
            mode = "overall"
        if mode == "assessment" and not assessment_id and assessments:
            assessment_id = str(assessments[-1]["id"])
        students = con.execute("SELECT * FROM students WHERE year=? AND department=? AND branch=? AND batch=?",
                               (year, dept, branch, batch)).fetchall()
        data = []
        for s in students:
            rs = con.execute("""SELECT r.*, a.assessment_name, a.max_score FROM results r
                JOIN assessments a ON a.id=r.assessment_id WHERE r.student_id=? ORDER BY a.uploaded_at""", (s["id"],)).fetchall()
            score_map = {str(r["assessment_id"]): r for r in rs}
            if mode == "assessment":
                r = score_map.get(str(assessment_id))
                score = float(r["score"] or 0) if r else 0
                accuracy = float(r["accuracy"] or 0) if r else 0
                time_taken = r["time_taken"] or "—" if r else "—"
                switches = r["tab_switches"] if r and r["tab_switches"] is not None else "—"
            else:
                score = sum(float(r["score"] or 0) for r in rs)
                accs = [float(r["accuracy"]) for r in rs if r["accuracy"] is not None]
                accuracy = sum(accs)/len(accs) if accs else 0
                time_taken = "—"
                vals = [r["tab_switches"] for r in rs if r["tab_switches"] is not None]
                switches = max(vals) if vals else "—"
            data.append({"roll": s["roll"], "name": s["name"], "score": score,
                         "accuracy": max(0, min(100, accuracy)), "time": time_taken, "switches": switches})
    data.sort(key=lambda x: (-x["score"], -x["accuracy"], x["name"].casefold()))
    for i, s in enumerate(data, 1):
        s["rank"] = i
    selected = next((a for a in assessments if str(a["id"]) == str(assessment_id)), None)
    return render_template("leaderboard.html", rows=data, year=year, department=dept, branch=branch,
                           batch=batch, mode=mode, assessments=assessments, assessment_id=str(assessment_id),
                           selected=selected)


@app.route("/admin/login", methods=["GET", "POST"])
def login():
    if request.method == "POST":
        with connect() as con:
            admin = con.execute("SELECT * FROM admins WHERE username=?", (request.form.get("username", "").strip(),)).fetchone()
        if admin and check_password_hash(admin["password_hash"], request.form.get("password", "")):
            session.clear()
            session["admin_id"] = admin["id"]
            session["admin_username"] = admin["username"]
            return redirect(url_for("admin"))
        flash("Invalid username or password.", "error")
    return render_template("login.html")


@app.get("/admin")
@admin_required
def admin():
    with connect() as con:
        recent = con.execute("SELECT * FROM assessments ORDER BY uploaded_at DESC LIMIT 20").fetchall()
        student_count = con.execute("SELECT COUNT(*) FROM students").fetchone()[0]
        assessment_count = con.execute("SELECT COUNT(*) FROM assessments").fetchone()[0]
    return render_template("admin.html", recent=recent, student_count=student_count, assessment_count=assessment_count)


@app.post("/admin/upload")
@admin_required
def upload():
    fields = {k: request.form.get(k, "").strip() for k in ("year", "department", "branch", "batch", "assessment_name")}
    file = request.files.get("spreadsheet")
    if not all(fields.values()) or not file or not file.filename:
        flash("Fill in all group fields, assessment name and spreadsheet.", "error")
        return redirect(url_for("admin"))
    if "." not in file.filename or file.filename.rsplit(".", 1)[1].lower() not in ALLOWED:
        flash("Upload an .xlsx, .xls or .csv file.", "error")
        return redirect(url_for("admin"))
    try:
        frame = read_sheet(file)
    except Exception:
        flash("Could not read the spreadsheet. Make sure the first row contains column headers.", "error")
        return redirect(url_for("admin"))
    max_score = num(request.form.get("max_score"))
    imported = skipped = 0
    stamp = datetime.utcnow().strftime("%Y-%m-%d %H:%M:%S UTC")
    try:
        with connect() as con:
            con.execute("""INSERT INTO assessments(year,department,branch,batch,assessment_name,max_score,uploaded_at)
                VALUES(?,?,?,?,?,?,?) ON CONFLICT(year,department,branch,batch,assessment_name)
                DO UPDATE SET max_score=excluded.max_score, uploaded_at=excluded.uploaded_at""",
                (fields["year"], fields["department"], fields["branch"], fields["batch"], fields["assessment_name"], max_score, stamp))
            aid = con.execute("SELECT id FROM assessments WHERE year=? AND department=? AND branch=? AND batch=? AND assessment_name=?",
                (fields["year"], fields["department"], fields["branch"], fields["batch"], fields["assessment_name"])).fetchone()[0]
            for _, row in frame.iterrows():
                roll = clean(getval(row, ["roll_number", "roll_no", "roll", "registration_number", "reg_no", "student_id", "usn"]))
                email = clean(getval(row, ["email", "email_id", "mail_id"]))
                name = clean(getval(row, ["student_name", "name", "full_name", "candidate_name", "candidate"]))
                if not roll and not email:
                    skipped += 1
                    continue
                if not roll:
                    roll = email.lower()
                if not name:
                    name = roll
                score = num(getval(row, ["score", "marks", "total_marks", "obtained_marks", "final_score"]), 0) or 0
                accuracy = num(getval(row, ["accuracy", "accuracy_percentage", "accuracy_percent", "correct_percentage"]))
                if accuracy is not None:
                    accuracy = max(0, min(100, accuracy))
                time_taken = clean(getval(row, ["time_taken", "time", "duration", "time_spent"]))
                tabs = num(getval(row, ["tab_switches", "tab_switch", "switches", "tab_changes"]))
                tabs = int(tabs) if tabs is not None else None
                con.execute("""INSERT INTO students(roll,name,email,year,department,branch,batch) VALUES(?,?,?,?,?,?,?)
                    ON CONFLICT(roll,year,department,branch,batch) DO UPDATE SET name=excluded.name,
                    email=CASE WHEN excluded.email='' THEN students.email ELSE excluded.email END""",
                    (roll, name, email, fields["year"], fields["department"], fields["branch"], fields["batch"]))
                sid = con.execute("SELECT id FROM students WHERE roll=? AND year=? AND department=? AND branch=? AND batch=?",
                    (roll, fields["year"], fields["department"], fields["branch"], fields["batch"])).fetchone()[0]
                con.execute("""INSERT INTO results(student_id,assessment_id,score,accuracy,time_taken,tab_switches)
                    VALUES(?,?,?,?,?,?) ON CONFLICT(student_id,assessment_id) DO UPDATE SET
                    score=excluded.score,accuracy=excluded.accuracy,time_taken=excluded.time_taken,tab_switches=excluded.tab_switches""",
                    (sid, aid, score, accuracy, time_taken, tabs))
                imported += 1
    except Exception:
        app.logger.exception("Spreadsheet import failed")
        flash("Import failed. Check the spreadsheet headers and values.", "error")
        return redirect(url_for("admin"))
    flash(f"Updated {fields['assessment_name']}: {imported} rows imported, {skipped} rows skipped (missing roll number/email).", "success")
    return redirect(url_for("admin"))


@app.post("/admin/logout")
@admin_required
def logout():
    session.clear()
    return redirect(url_for("home"))


@app.get("/health")
def health():
    return {"status": "ok"}


@app.errorhandler(413)
def too_large(_):
    flash("The upload exceeds the 12 MB limit.", "error")
    return redirect(url_for("admin"))


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=int(os.getenv("PORT", "5000")), debug=False)
