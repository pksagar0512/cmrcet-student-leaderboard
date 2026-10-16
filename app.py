import os, secrets, sqlite3
from pathlib import Path
from functools import wraps
from datetime import datetime
import pandas as pd
from dotenv import load_dotenv
from flask import Flask, render_template, request, redirect, url_for, session, flash
from flask_wtf.csrf import CSRFProtect
from werkzeug.security import check_password_hash, generate_password_hash

load_dotenv(); BASE=Path(__file__).resolve().parent; DB_PATH=os.getenv('DATABASE_PATH',str(BASE/'leaderboard.db')); ALLOWED={'xlsx','xls','csv'}
app=Flask(__name__); app.config.update(SECRET_KEY=os.getenv('SECRET_KEY') or secrets.token_hex(32),MAX_CONTENT_LENGTH=12*1024*1024,SESSION_COOKIE_HTTPONLY=True,SESSION_COOKIE_SAMESITE='Lax',SESSION_COOKIE_SECURE=os.getenv('COOKIE_SECURE','0')=='1'); CSRFProtect(app)
def connect():
 c=sqlite3.connect(DB_PATH); c.row_factory=sqlite3.Row; c.execute('PRAGMA foreign_keys=ON'); return c
def init_db():
 with connect() as c:
  c.executescript('''CREATE TABLE IF NOT EXISTS admins(id INTEGER PRIMARY KEY,username TEXT UNIQUE NOT NULL,password_hash TEXT NOT NULL);
  CREATE TABLE IF NOT EXISTS batches(id INTEGER PRIMARY KEY,name TEXT UNIQUE NOT NULL,year TEXT NOT NULL,departments TEXT NOT NULL,created_at TEXT NOT NULL);
  CREATE TABLE IF NOT EXISTS students(id INTEGER PRIMARY KEY,roll TEXT UNIQUE NOT NULL,name TEXT NOT NULL,email TEXT DEFAULT '',year TEXT NOT NULL,department TEXT NOT NULL,division TEXT DEFAULT '',batch_id INTEGER NOT NULL REFERENCES batches(id));
  CREATE TABLE IF NOT EXISTS assessments(id INTEGER PRIMARY KEY,batch_id INTEGER NOT NULL REFERENCES batches(id),name TEXT NOT NULL,max_score REAL,uploaded_at TEXT NOT NULL,UNIQUE(batch_id,name));
  CREATE TABLE IF NOT EXISTS results(id INTEGER PRIMARY KEY,student_id INTEGER NOT NULL REFERENCES students(id) ON DELETE CASCADE,assessment_id INTEGER NOT NULL REFERENCES assessments(id) ON DELETE CASCADE,score REAL DEFAULT 0,accuracy REAL,time_taken TEXT DEFAULT '',tab_switches INTEGER,UNIQUE(student_id,assessment_id));''')
  u,p=os.getenv('ADMIN_USERNAME','').strip(),os.getenv('ADMIN_PASSWORD','')
  if u and p and not c.execute('SELECT 1 FROM admins WHERE username=?',(u,)).fetchone(): c.execute('INSERT INTO admins(username,password_hash) VALUES(?,?)',(u,generate_password_hash(p)))
init_db()
def admin_required(fn):
 @wraps(fn)
 def w(*a,**kw):
  if not session.get('admin_id'): return redirect(url_for('login'))
  return fn(*a,**kw)
 return w
def norm(s): return ''.join(ch.lower() for ch in str(s) if ch.isalnum())
def getval(row,names,default=''):
 cols={norm(k):k for k in row.index}
 for n in names:
  if norm(n) in cols:
   v=row[cols[norm(n)]]
   if not pd.isna(v) and str(v).strip(): return v
 for k,col in cols.items():
  if any(k.startswith(norm(n)) for n in names):
   v=row[col]
   if not pd.isna(v) and str(v).strip(): return v
 return default
def clean(v): return '' if pd.isna(v) else str(v).strip()
def num(v,default=None):
 try:
  if v is None or pd.isna(v) or not str(v).strip(): return default
  return float(str(v).replace('%','').replace(',','').strip())
 except (ValueError,TypeError): return default
def read_sheet(f):
 ext=f.filename.rsplit('.',1)[-1].lower()
 return pd.read_csv(f) if ext=='csv' else pd.read_excel(f,engine='xlrd' if ext=='xls' else 'openpyxl')
def row_student(row):
 roll=clean(getval(row,['roll_number','roll_no','roll','registration_number','reg_no','student_id','usn'])); email=clean(getval(row,['email','email_id','mail_id'])); name=clean(getval(row,['student_name','name','full_name','candidate_name','candidate'])); year=clean(getval(row,['year','academic_year','student_year','class_year'])); dept=clean(getval(row,['department','dept','branch','program'])); div=clean(getval(row,['division','div','section']))
 if not roll and email: roll=email.lower()
 if not name or not roll: return None
 return roll,name,email,year,dept,div
@app.get('/')
def home():
 with connect() as c: batches=c.execute('SELECT b.*,COUNT(s.id) student_count FROM batches b LEFT JOIN students s ON s.batch_id=b.id GROUP BY b.id ORDER BY b.name').fetchall()
 return render_template('index.html',batches=batches)
@app.get('/leaderboard/<int:batch_id>')
def leaderboard(batch_id):
 mode=request.args.get('mode','overall'); aid=request.args.get('assessment_id','')
 with connect() as c:
  batch=c.execute('SELECT * FROM batches WHERE id=?',(batch_id,)).fetchone()
  if not batch: return 'Batch not found',404
  assessments=c.execute('SELECT * FROM assessments WHERE batch_id=? ORDER BY uploaded_at, name',(batch_id,)).fetchall()
  if mode not in ('overall','assessment'): mode='overall'
  if mode=='assessment' and not aid and assessments: aid=str(assessments[-1]['id'])
  students=c.execute('SELECT * FROM students WHERE batch_id=?',(batch_id,)).fetchall(); data=[]
  for s in students:
   rs=c.execute('SELECT r.*,a.name assessment_name,a.max_score,a.id aid FROM results r JOIN assessments a ON a.id=r.assessment_id WHERE r.student_id=? AND a.batch_id=? ORDER BY a.uploaded_at',(s['id'],batch_id)).fetchall()
   if mode=='assessment':
    r=next((r for r in rs if str(r['aid'])==str(aid)),None); score=float(r['score'] or 0) if r else 0; accuracy=float(r['accuracy'] or 0) if r else 0; time=r['time_taken'] or '—' if r else '—'; switches=r['tab_switches'] if r and r['tab_switches'] is not None else '—'
   else:
    # Complete batch ranking uses average percentage across assessments taken; score shown is average percentage.
    percentages=[(100*float(r['score'] or 0)/float(r['max_score'])) if r['max_score'] and float(r['max_score'])>0 else float(r['score'] or 0) for r in rs]
    score=sum(percentages)/len(percentages) if percentages else 0; accs=[float(r['accuracy']) for r in rs if r['accuracy'] is not None]; accuracy=sum(accs)/len(accs) if accs else 0; time='—'; vals=[r['tab_switches'] for r in rs if r['tab_switches'] is not None]; switches=max(vals) if vals else '—'
   data.append(dict(roll=s['roll'],name=s['name'],email=s['email'],score=score,accuracy=max(0,min(100,accuracy)),time=time,switches=switches))
 data.sort(key=lambda x:(-x['score'],-x['accuracy'],x['name'].casefold()))
 for i,s in enumerate(data,1): s['rank']=i
 selected=next((a for a in assessments if str(a['id'])==str(aid)),None)
 return render_template('leaderboard.html',batch=batch,rows=data,mode=mode,assessments=assessments,assessment_id=str(aid),selected=selected)
@app.route('/admin/login',methods=['GET','POST'])
def login():
 if request.method=='POST':
  with connect() as c: a=c.execute('SELECT * FROM admins WHERE username=?',(request.form.get('username','').strip(),)).fetchone()
  if a and check_password_hash(a['password_hash'],request.form.get('password','')): session.clear(); session['admin_id']=a['id']; session['admin_username']=a['username']; return redirect(url_for('admin'))
  flash('Invalid username or password.','error')
 return render_template('login.html')
@app.get('/admin')
@admin_required
def admin():
 with connect() as c: batches=c.execute('SELECT b.*,COUNT(s.id) student_count FROM batches b LEFT JOIN students s ON s.batch_id=b.id GROUP BY b.id ORDER BY b.name').fetchall(); recent=c.execute('SELECT a.*,b.name batch_name FROM assessments a JOIN batches b ON b.id=a.batch_id ORDER BY a.uploaded_at DESC LIMIT 20').fetchall(); sc=c.execute('SELECT COUNT(*) FROM students').fetchone()[0]; ac=c.execute('SELECT COUNT(*) FROM assessments').fetchone()[0]
 return render_template('admin.html',batches=batches,recent=recent,student_count=sc,assessment_count=ac)
@app.post('/admin/batches/create')
@admin_required
def create_batch():
 name=request.form.get('name','').strip(); year=request.form.get('year','').strip(); depts=sorted(set(d.strip() for d in request.form.getlist('departments') if d.strip()))
 if not name or not year or not depts: flash('Enter batch name, academic year and select at least one department.','error'); return redirect(url_for('admin'))
 try:
  with connect() as c: c.execute('INSERT INTO batches(name,year,departments,created_at) VALUES(?,?,?,?)',(name,year,', '.join(depts),datetime.utcnow().strftime('%Y-%m-%d %H:%M:%S UTC')))
  flash('Batch created. Upload the student master list for this batch next.','success')
 except sqlite3.IntegrityError: flash('A batch with that name already exists.','error')
 return redirect(url_for('admin'))
@app.post('/admin/students/upload')
@admin_required
def upload_students():
 bid=request.form.get('batch_id',''); f=request.files.get('spreadsheet')
 if not bid or not f or not f.filename or '.' not in f.filename or f.filename.rsplit('.',1)[1].lower() not in ALLOWED: flash('Choose a batch and upload .xlsx, .xls or .csv.','error'); return redirect(url_for('admin'))
 try: frame=read_sheet(f)
 except Exception: flash('Could not read the file. Check that the first row contains headers.','error'); return redirect(url_for('admin'))
 added=updated=skipped=conflicts=0
 with connect() as c:
  batch=c.execute('SELECT * FROM batches WHERE id=?',(bid,)).fetchone()
  if not batch: flash('Batch not found.','error'); return redirect(url_for('admin'))
  allowed={norm(x) for x in batch['departments'].split(',')}
  for _,r in frame.iterrows():
   parsed=row_student(r)
   if not parsed: skipped+=1; continue
   roll,name,email,year,dept,div=parsed; year=year or batch['year']
   if norm(dept) not in allowed or year!=batch['year']: skipped+=1; continue
   existing=c.execute('SELECT * FROM students WHERE roll=?',(roll,)).fetchone()
   if existing and existing['batch_id']!=int(bid): conflicts+=1; continue
   if existing:
    c.execute('UPDATE students SET name=?,email=?,year=?,department=?,division=? WHERE id=?',(name,email or existing['email'],year,dept,div,existing['id'])); updated+=1
   else:
    c.execute('INSERT INTO students(roll,name,email,year,department,division,batch_id) VALUES(?,?,?,?,?,?,?)',(roll,name,email,year,dept,div,int(bid))); added+=1
 flash(f'Student import complete: {added} added, {updated} updated, {skipped} skipped, {conflicts} blocked because the student is already in another batch.','success' if not conflicts else 'warning')
 return redirect(url_for('admin'))
@app.post('/admin/results/upload')
@admin_required
def upload_results():
 bid=request.form.get('batch_id',''); name=request.form.get('assessment_name','').strip(); f=request.files.get('spreadsheet'); maxscore=num(request.form.get('max_score'))
 if not bid or not name or not f or not f.filename or '.' not in f.filename or f.filename.rsplit('.',1)[1].lower() not in ALLOWED: flash('Choose a batch, assessment name and valid spreadsheet.','error'); return redirect(url_for('admin'))
 try: frame=read_sheet(f)
 except Exception: flash('Could not read the file. Check spreadsheet headers.','error'); return redirect(url_for('admin'))
 imported=skipped=0; stamp=datetime.utcnow().strftime('%Y-%m-%d %H:%M:%S UTC')
 with connect() as c:
  batch=c.execute('SELECT * FROM batches WHERE id=?',(bid,)).fetchone()
  if not batch: flash('Batch not found.','error'); return redirect(url_for('admin'))
  c.execute('INSERT INTO assessments(batch_id,name,max_score,uploaded_at) VALUES(?,?,?,?) ON CONFLICT(batch_id,name) DO UPDATE SET max_score=excluded.max_score,uploaded_at=excluded.uploaded_at',(int(bid),name,maxscore,stamp)); aid=c.execute('SELECT id FROM assessments WHERE batch_id=? AND name=?',(int(bid),name)).fetchone()[0]
  for _,r in frame.iterrows():
   roll=clean(getval(r,['roll_number','roll_no','roll','registration_number','reg_no','student_id','usn'])); email=clean(getval(r,['email','email_id','mail_id'])); student=c.execute('SELECT * FROM students WHERE roll=? AND batch_id=?',(roll,int(bid))).fetchone() if roll else None
   if not student and email: student=c.execute('SELECT * FROM students WHERE lower(email)=lower(?) AND batch_id=?',(email,int(bid))).fetchone()
   if not student: skipped+=1; continue
   score=num(getval(r,['score','marks','total_marks','obtained_marks','final_score']),0) or 0; accuracy=num(getval(r,['accuracy','accuracy_percentage','accuracy_percent','correct_percentage'])); accuracy=max(0,min(100,accuracy)) if accuracy is not None else None; tm=clean(getval(r,['time_taken','time','duration','time_spent'])); tabs=num(getval(r,['tab_switches','tab_switch','switches','tab_changes'])); tabs=int(tabs) if tabs is not None else None
   c.execute('INSERT INTO results(student_id,assessment_id,score,accuracy,time_taken,tab_switches) VALUES(?,?,?,?,?,?) ON CONFLICT(student_id,assessment_id) DO UPDATE SET score=excluded.score,accuracy=excluded.accuracy,time_taken=excluded.time_taken,tab_switches=excluded.tab_switches',(student['id'],aid,score,accuracy,tm,tabs)); imported+=1
 flash(f'{name} updated: {imported} results imported, {skipped} rows skipped (student must already belong to the selected batch).','success'); return redirect(url_for('admin'))
@app.post('/admin/logout')
@admin_required
def logout(): session.clear(); return redirect(url_for('home'))
@app.get('/health')
def health(): return {'status':'ok'}
@app.errorhandler(413)
def too_large(_): flash('Upload exceeds 12 MB.','error'); return redirect(url_for('admin'))
if __name__=='__main__': app.run(host='0.0.0.0',port=int(os.getenv('PORT','5000')),debug=False)
