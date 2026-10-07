"""
Campus Automation System - Flask application.

Sections in this file (search for the ==== headings):
  1. Setup            4. Students           7. Marks
  2. Login / roles    5. Faculty            8. Notices
  3. Dashboards       6. Attendance         9. Pages + error handling
"""
import hmac
import os
import re
import secrets
import sqlite3
from datetime import date
from functools import wraps

from flask import (Flask, abort, flash, redirect, render_template, request,
                   session, url_for)
from werkzeug.security import check_password_hash, generate_password_hash

import db

# =====================================================================
# 1. SETUP
# =====================================================================
app = Flask(__name__)
# On Render, set SECRET_KEY as an environment variable. The fallback is for local use only.
app.config["SECRET_KEY"] = os.environ.get("SECRET_KEY", "dev-only-change-me")
app.config["SESSION_COOKIE_HTTPONLY"] = True
app.config["SESSION_COOKIE_SAMESITE"] = "Lax"

app.teardown_appcontext(db.close_db)
db.init_db()  # creates tables on start (important for Render)

DEPARTMENTS = ["Data Science", "Computer Science", "Information Technology",
               "Electronics", "Mechanical"]
DESIGNATIONS = ["Professor", "Associate Professor", "Assistant Professor", "Lecturer"]
SEMESTERS = list(range(1, 9))
EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")

# Sidebar links per role: (endpoint, label, prefix used to highlight the active link)
NAV = {
    "admin": [("dashboard_admin", "Dashboard", "dashboard"),
              ("students_list", "Students", "students"),
              ("faculty_list", "Faculty", "faculty"),
              ("attendance_report", "Attendance", "attendance"),
              ("marks_list", "Marks", "marks"),
              ("notices_list", "Notices", "notices"),
              ("about_cloud", "About Cloud", "about_cloud")],
    "faculty": [("dashboard_faculty", "Dashboard", "dashboard"),
                ("attendance_mark", "Mark Attendance", "attendance_mark"),
                ("attendance_report", "Attendance Reports", "attendance_report"),
                ("students_list", "Students", "students"),
                ("marks_list", "Upload Marks", "marks"),
                ("notices_list", "Notices", "notices"),
                ("my_profile", "My Profile", "my_profile"),
                ("about_cloud", "About Cloud", "about_cloud")],
    "student": [("dashboard_student", "Dashboard", "dashboard"),
                ("my_profile", "My Profile", "my_profile"),
                ("my_marks", "My Marks", "my_marks"),
                ("notices_list", "Notices", "notices"),
                ("about_cloud", "About Cloud", "about_cloud")],
}


@app.context_processor
def inject_globals():
    """Variables available in every template."""
    return dict(nav_items=NAV.get(session.get("role"), []),
                today=date.today().isoformat(),
                DEPARTMENTS=DEPARTMENTS, DESIGNATIONS=DESIGNATIONS, SEMESTERS=SEMESTERS)


# ---- CSRF protection: every POST form must carry the secret token ----
def csrf_token():
    if "_csrf" not in session:
        session["_csrf"] = secrets.token_hex(16)
    return session["_csrf"]


app.jinja_env.globals["csrf_token"] = csrf_token


@app.before_request
def check_csrf():
    if request.method == "POST":
        sent = request.form.get("csrf_token", "").encode()
        real = session.get("_csrf", "").encode()
        if not real or not hmac.compare_digest(sent, real):
            abort(400)


# ---- Small helpers ----
def percent(part, total):
    return round(part * 100 / total, 1) if total else 0


def attendance_stats(student_id=None):
    """Present / absent / total / percentage - one function used everywhere."""
    sql = ("SELECT COALESCE(SUM(status='Present'),0) AS present, "
           "COALESCE(SUM(status='Absent'),0) AS absent FROM attendance")
    args = ()
    if student_id is not None:
        sql += " WHERE student_id = ?"
        args = (student_id,)
    row = db.query(sql, args, one=True)
    total = row["present"] + row["absent"]
    return dict(present=row["present"], absent=row["absent"], total=total,
                pct=percent(row["present"], total))


def valid_date(text):
    try:
        date.fromisoformat(text)
        return True
    except (ValueError, TypeError):
        return False


# =====================================================================
# 2. LOGIN AND ROLE PROTECTION
# =====================================================================
def login_required(*roles):
    """Use @login_required() for any logged-in user, or
    @login_required("admin", "faculty") to allow only those roles."""
    def decorator(view):
        @wraps(view)
        def wrapper(*args, **kwargs):
            if "user_id" not in session:
                flash("Please log in to continue.", "warning")
                return redirect(url_for("login"))
            if roles and session.get("role") not in roles:
                abort(403)
            return view(*args, **kwargs)
        return wrapper
    return decorator


def home_for(role):
    return url_for({"admin": "dashboard_admin", "faculty": "dashboard_faculty",
                    "student": "dashboard_student"}[role])


@app.route("/login", methods=["GET", "POST"])
def login():
    if "user_id" in session:
        return redirect(home_for(session["role"]))
    if request.method == "POST":
        email = request.form.get("email", "").strip().lower()
        password = request.form.get("password", "")
        user = db.query("SELECT * FROM users WHERE email = ?", (email,), one=True)
        if user and check_password_hash(user["password_hash"], password):
            session.clear()
            session.update(user_id=user["id"], role=user["role"], name=user["name"],
                           student_id=user["student_id"], faculty_id=user["faculty_id"])
            return redirect(home_for(user["role"]))
        flash("Invalid email or password.", "danger")
    return render_template("login.html")


@app.route("/logout")
def logout():
    session.clear()
    flash("You have been logged out.", "info")
    return redirect(url_for("login"))


def make_login(conn, name, email, role, student_id=None, faculty_id=None):
    """Create a login account and return the temporary password (shown once to the admin)."""
    temp = secrets.token_urlsafe(6)
    conn.execute(
        "INSERT INTO users (name, email, password_hash, role, student_id, faculty_id) "
        "VALUES (?,?,?,?,?,?)",
        (name, email, generate_password_hash(temp), role, student_id, faculty_id))
    return temp


# =====================================================================
# 3. DASHBOARDS
# =====================================================================
def attendance_trend():
    rows = db.query("""SELECT attendance_date AS d,
                       SUM(status='Present') AS p, SUM(status='Absent') AS a
                       FROM attendance GROUP BY attendance_date
                       ORDER BY attendance_date DESC LIMIT 7""")
    rows = list(reversed(rows))
    return dict(labels=[r["d"] for r in rows], present=[r["p"] for r in rows],
                absent=[r["a"] for r in rows])


def recent_notices(n=3):
    return db.query("SELECT * FROM notices ORDER BY notice_date DESC, id DESC LIMIT ?", (n,))


@app.route("/dashboard")
@login_required()
def dashboard():
    return redirect(home_for(session["role"]))


@app.route("/admin-dashboard")
@login_required("admin")
def dashboard_admin():
    count = lambda t: db.query(f"SELECT COUNT(*) AS c FROM {t}", one=True)["c"]  # fixed table names only
    dept = db.query("SELECT department, COUNT(*) AS c FROM students GROUP BY department ORDER BY department")
    return render_template(
        "admin_dashboard.html",
        counts=dict(students=count("students"), faculty=count("faculty"),
                    attendance=count("attendance"), notices=count("notices"), marks=count("marks")),
        overall=attendance_stats(), trend=attendance_trend(),
        dept_data=dict(labels=[r["department"] for r in dept], values=[r["c"] for r in dept]),
        notices=recent_notices())


@app.route("/faculty-dashboard")
@login_required("faculty")
def dashboard_faculty():
    me = db.query("SELECT * FROM faculty WHERE id = ?", (session["faculty_id"],), one=True)
    marked_today = db.query("SELECT COUNT(*) AS c FROM attendance WHERE attendance_date = ?",
                            (date.today().isoformat(),), one=True)["c"]
    return render_template(
        "faculty_dashboard.html", me=me, overall=attendance_stats(), trend=attendance_trend(),
        total_students=db.query("SELECT COUNT(*) AS c FROM students", one=True)["c"],
        marked_today=marked_today, notices=recent_notices())


@app.route("/student-dashboard")
@login_required("student")
def dashboard_student():
    sid = session["student_id"]
    me = db.query("SELECT * FROM students WHERE id = ?", (sid,), one=True)
    marks = db.query("""SELECT subject, obtained, maximum,
                        ROUND(obtained*100.0/maximum,1) AS pct FROM marks
                        WHERE student_id = ? ORDER BY subject""", (sid,))
    avg = round(sum(m["pct"] for m in marks) / len(marks), 1) if marks else None
    return render_template("student_dashboard.html", me=me, att=attendance_stats(sid),
                           marks=marks, avg=avg, notices=recent_notices())


# =====================================================================
# 4. STUDENT MANAGEMENT (admin + faculty)
# =====================================================================
def read_person(form, extra_field):
    """Read and validate the fields shared by students and faculty."""
    data = {"name": form.get("name", "").strip(),
            "email": form.get("email", "").strip().lower(),
            "department": form.get("department", "").strip(),
            extra_field: form.get(extra_field, "").strip()}
    errors = []
    if len(data["name"]) < 2:
        errors.append("Name must be at least 2 characters.")
    if not EMAIL_RE.match(data["email"]):
        errors.append("Please enter a valid email address.")
    if data["department"] not in DEPARTMENTS:
        errors.append("Please choose a department.")
    return data, errors


def read_student(form):
    data, errors = read_person(form, "semester")
    if not data["semester"].isdigit() or int(data["semester"]) not in SEMESTERS:
        errors.append("Semester must be between 1 and 8.")
    return data, errors


@app.route("/students")
@login_required("admin", "faculty")
def students_list():
    q = request.args.get("q", "").strip()
    dept = request.args.get("department", "").strip()
    sql, args = "SELECT * FROM students WHERE 1=1", []
    if q:
        sql += " AND (name LIKE ? OR email LIKE ?)"
        args += [f"%{q}%", f"%{q}%"]
    if dept:
        sql += " AND department = ?"
        args.append(dept)
    rows = db.query(sql + " ORDER BY name", args)
    return render_template("students/list.html", students=rows, q=q, dept=dept)


@app.route("/students/add", methods=["GET", "POST"])
@login_required("admin", "faculty")
def students_add():
    data, errors = {}, []
    if request.method == "POST":
        data, errors = read_student(request.form)
        if not errors:
            conn = db.get_db()
            try:
                cur = conn.execute(
                    "INSERT INTO students (name, email, department, semester) VALUES (?,?,?,?)",
                    (data["name"], data["email"], data["department"], int(data["semester"])))
                temp = make_login(conn, data["name"], data["email"], "student", student_id=cur.lastrowid)
                conn.commit()
            except sqlite3.IntegrityError:
                conn.rollback()
                errors.append("A user with this email already exists.")
            else:
                flash(f"Student added. Login email: {data['email']} | Temporary password: {temp} "
                      "(note it down - it is shown only once).", "success")
                return redirect(url_for("students_list"))
    return render_template("students/form.html", student=data, errors=errors, editing=False)


@app.route("/students/<int:sid>/edit", methods=["GET", "POST"])
@login_required("admin", "faculty")
def students_edit(sid):
    student = db.query("SELECT * FROM students WHERE id = ?", (sid,), one=True)
    if student is None:
        abort(404)
    data, errors = dict(student), []
    if request.method == "POST":
        data, errors = read_student(request.form)
        if not errors:
            conn = db.get_db()
            try:
                conn.execute("UPDATE students SET name=?, email=?, department=?, semester=? WHERE id=?",
                             (data["name"], data["email"], data["department"], int(data["semester"]), sid))
                conn.execute("UPDATE users SET name=?, email=? WHERE student_id=?",
                             (data["name"], data["email"], sid))
                conn.commit()
            except sqlite3.IntegrityError:
                conn.rollback()
                errors.append("Another user already uses this email.")
            else:
                flash("Student updated.", "success")
                return redirect(url_for("students_list"))
    return render_template("students/form.html", student=data, errors=errors, editing=True, sid=sid)


@app.route("/students/<int:sid>/delete", methods=["POST"])
@login_required("admin")
def students_delete(sid):
    # ON DELETE CASCADE removes this student's login, attendance and marks too.
    db.execute("DELETE FROM students WHERE id = ?", (sid,))
    flash("Student deleted.", "info")
    return redirect(url_for("students_list"))


def student_profile_page(student):
    marks = db.query("""SELECT subject, obtained, maximum, ROUND(obtained*100.0/maximum,1) AS pct
                        FROM marks WHERE student_id = ? ORDER BY subject""", (student["id"],))
    records = db.query("SELECT * FROM attendance WHERE student_id = ? ORDER BY attendance_date DESC LIMIT 60",
                       (student["id"],))
    return render_template("students/profile.html", student=student, att=attendance_stats(student["id"]),
                           marks=marks, records=records)


@app.route("/students/<int:sid>")
@login_required("admin", "faculty")
def students_view(sid):
    student = db.query("SELECT * FROM students WHERE id = ?", (sid,), one=True)
    if student is None:
        abort(404)
    return student_profile_page(student)


# =====================================================================
# 5. FACULTY MANAGEMENT (admin only)
# =====================================================================
def read_faculty(form):
    data, errors = read_person(form, "designation")
    if data["designation"] not in DESIGNATIONS:
        errors.append("Please choose a designation.")
    return data, errors


@app.route("/faculty")
@login_required("admin")
def faculty_list():
    q = request.args.get("q", "").strip()
    dept = request.args.get("department", "").strip()
    sql, args = "SELECT * FROM faculty WHERE 1=1", []
    if q:
        sql += " AND (name LIKE ? OR email LIKE ?)"
        args += [f"%{q}%", f"%{q}%"]
    if dept:
        sql += " AND department = ?"
        args.append(dept)
    return render_template("faculty/list.html", faculty=db.query(sql + " ORDER BY name", args), q=q, dept=dept)


@app.route("/faculty/add", methods=["GET", "POST"])
@login_required("admin")
def faculty_add():
    data, errors = {}, []
    if request.method == "POST":
        data, errors = read_faculty(request.form)
        if not errors:
            conn = db.get_db()
            try:
                cur = conn.execute(
                    "INSERT INTO faculty (name, email, department, designation) VALUES (?,?,?,?)",
                    (data["name"], data["email"], data["department"], data["designation"]))
                temp = make_login(conn, data["name"], data["email"], "faculty", faculty_id=cur.lastrowid)
                conn.commit()
            except sqlite3.IntegrityError:
                conn.rollback()
                errors.append("A user with this email already exists.")
            else:
                flash(f"Faculty added. Login email: {data['email']} | Temporary password: {temp} "
                      "(note it down - it is shown only once).", "success")
                return redirect(url_for("faculty_list"))
    return render_template("faculty/form.html", member=data, errors=errors, editing=False)


@app.route("/faculty/<int:fid>/edit", methods=["GET", "POST"])
@login_required("admin")
def faculty_edit(fid):
    member = db.query("SELECT * FROM faculty WHERE id = ?", (fid,), one=True)
    if member is None:
        abort(404)
    data, errors = dict(member), []
    if request.method == "POST":
        data, errors = read_faculty(request.form)
        if not errors:
            conn = db.get_db()
            try:
                conn.execute("UPDATE faculty SET name=?, email=?, department=?, designation=? WHERE id=?",
                             (data["name"], data["email"], data["department"], data["designation"], fid))
                conn.execute("UPDATE users SET name=?, email=? WHERE faculty_id=?",
                             (data["name"], data["email"], fid))
                conn.commit()
            except sqlite3.IntegrityError:
                conn.rollback()
                errors.append("Another user already uses this email.")
            else:
                flash("Faculty member updated.", "success")
                return redirect(url_for("faculty_list"))
    return render_template("faculty/form.html", member=data, errors=errors, editing=True, fid=fid)


@app.route("/faculty/<int:fid>/delete", methods=["POST"])
@login_required("admin")
def faculty_delete(fid):
    db.execute("DELETE FROM faculty WHERE id = ?", (fid,))
    flash("Faculty member deleted.", "info")
    return redirect(url_for("faculty_list"))


@app.route("/my-profile")
@login_required("faculty", "student")
def my_profile():
    if session["role"] == "student":
        student = db.query("SELECT * FROM students WHERE id = ?", (session["student_id"],), one=True)
        return student_profile_page(student)  # students only ever see their own record
    member = db.query("SELECT * FROM faculty WHERE id = ?", (session["faculty_id"],), one=True)
    return render_template("faculty/profile.html", member=member)


# =====================================================================
# 6. ATTENDANCE
# =====================================================================
@app.route("/attendance/mark", methods=["GET", "POST"])
@login_required("faculty")
def attendance_mark():
    chosen_date = request.values.get("date", date.today().isoformat())
    dept = request.values.get("department", "").strip()

    if request.method == "POST":
        if not valid_date(chosen_date) or chosen_date > date.today().isoformat():
            flash("Please choose a valid date (not in the future).", "danger")
            return redirect(url_for("attendance_mark"))
        valid_ids = {r["id"] for r in db.query("SELECT id FROM students")}
        conn, saved = db.get_db(), 0
        for key, status in request.form.items():
            if key.startswith("status_") and key[7:].isdigit() and int(key[7:]) in valid_ids \
                    and status in ("Present", "Absent"):
                conn.execute(
                    """INSERT INTO attendance (student_id, attendance_date, status) VALUES (?,?,?)
                       ON CONFLICT(student_id, attendance_date) DO UPDATE SET status = excluded.status""",
                    (int(key[7:]), chosen_date, status))
                saved += 1
        conn.commit()
        flash(f"Attendance saved for {saved} student(s) on {chosen_date}.", "success")
        return redirect(url_for("attendance_mark", date=chosen_date, department=dept))

    if not valid_date(chosen_date):
        chosen_date = date.today().isoformat()
    sql = """SELECT s.*, a.status FROM students s
             LEFT JOIN attendance a ON a.student_id = s.id AND a.attendance_date = ?"""
    args = [chosen_date]
    if dept:
        sql += " WHERE s.department = ?"
        args.append(dept)
    students = db.query(sql + " ORDER BY s.name", args)
    return render_template("attendance/mark.html", students=students, chosen_date=chosen_date, dept=dept)


@app.route("/attendance/report")
@login_required("admin", "faculty")
def attendance_report():
    dept = request.args.get("department", "").strip()
    student = request.args.get("student", "").strip()
    date_from = request.args.get("date_from", "").strip()
    date_to = request.args.get("date_to", "").strip()
    status = request.args.get("status", "").strip()
    if date_from and not valid_date(date_from): date_from = ""
    if date_to and not valid_date(date_to): date_to = ""

    # Per-student summary (the filters below only ever add fixed text + ? placeholders)
    join, jargs = "a.student_id = s.id", []
    if date_from:
        join += " AND a.attendance_date >= ?"; jargs.append(date_from)
    if date_to:
        join += " AND a.attendance_date <= ?"; jargs.append(date_to)
    where, wargs = "1=1", []
    if dept:
        where += " AND s.department = ?"; wargs.append(dept)
    if student.isdigit():
        where += " AND s.id = ?"; wargs.append(int(student))
    summary = []
    for r in db.query(f"""SELECT s.id, s.name, s.department, s.semester,
                          COALESCE(SUM(a.status='Present'),0) AS present,
                          COALESCE(SUM(a.status='Absent'),0) AS absent
                          FROM students s LEFT JOIN attendance a ON {join}
                          WHERE {where} GROUP BY s.id ORDER BY s.name""", jargs + wargs):
        total = r["present"] + r["absent"]
        summary.append(dict(r, total=total, pct=percent(r["present"], total)))
    present = sum(r["present"] for r in summary)
    absent = sum(r["absent"] for r in summary)

    # Detailed records
    sql = """SELECT a.attendance_date, a.status, s.id AS sid, s.name, s.department
             FROM attendance a JOIN students s ON s.id = a.student_id WHERE 1=1"""
    args = []
    if dept:
        sql += " AND s.department = ?"; args.append(dept)
    if student.isdigit():
        sql += " AND s.id = ?"; args.append(int(student))
    if date_from:
        sql += " AND a.attendance_date >= ?"; args.append(date_from)
    if date_to:
        sql += " AND a.attendance_date <= ?"; args.append(date_to)
    if status in ("Present", "Absent"):
        sql += " AND a.status = ?"; args.append(status)
    records = db.query(sql + " ORDER BY a.attendance_date DESC, s.name LIMIT 300", args)

    return render_template(
        "attendance/report.html", summary=summary, records=records,
        totals=dict(present=present, absent=absent, total=present + absent,
                    pct=percent(present, present + absent)),
        all_students=db.query("SELECT id, name FROM students ORDER BY name"),
        f=dict(department=dept, student=student, date_from=date_from, date_to=date_to, status=status))


# =====================================================================
# 7. MARKS
# =====================================================================
def read_marks(form):
    data = {"student_id": form.get("student_id", "").strip(),
            "subject": form.get("subject", "").strip(),
            "obtained": form.get("obtained", "").strip(),
            "maximum": form.get("maximum", "").strip()}
    errors = []
    if not data["student_id"].isdigit() or not db.query(
            "SELECT 1 FROM students WHERE id = ?", (data["student_id"],), one=True):
        errors.append("Please select a student.")
    if len(data["subject"]) < 2:
        errors.append("Subject name must be at least 2 characters.")
    try:
        obtained, maximum = float(data["obtained"]), float(data["maximum"])
        if maximum <= 0:
            errors.append("Maximum marks must be greater than 0.")
        elif obtained < 0:
            errors.append("Obtained marks cannot be negative.")
        elif obtained > maximum:
            errors.append("Obtained marks cannot be greater than maximum marks.")
    except ValueError:
        errors.append("Obtained and maximum marks must be numbers.")
    return data, errors


@app.route("/marks")
@login_required("admin", "faculty")
def marks_list():
    sid = request.args.get("student", "").strip()
    subject = request.args.get("subject", "").strip()
    sql = """SELECT m.*, s.name, s.department, ROUND(m.obtained*100.0/m.maximum,1) AS pct
             FROM marks m JOIN students s ON s.id = m.student_id WHERE 1=1"""
    args = []
    if sid.isdigit():
        sql += " AND s.id = ?"; args.append(int(sid))
    if subject:
        sql += " AND m.subject LIKE ?"; args.append(f"%{subject}%")
    return render_template("marks/list.html", marks=db.query(sql + " ORDER BY s.name, m.subject", args),
                           all_students=db.query("SELECT id, name FROM students ORDER BY name"),
                           f=dict(student=sid, subject=subject), readonly=False)


@app.route("/my-marks")
@login_required("student")
def my_marks():
    rows = db.query("""SELECT m.*, s.name, s.department, ROUND(m.obtained*100.0/m.maximum,1) AS pct
                       FROM marks m JOIN students s ON s.id = m.student_id
                       WHERE m.student_id = ? ORDER BY m.subject""", (session["student_id"],))
    return render_template("marks/list.html", marks=rows, all_students=[], f={}, readonly=True)


def marks_form(editing, mark=None, mid=None):
    data, errors = (dict(mark) if mark else {}), []
    if request.method == "POST":
        data, errors = read_marks(request.form)
        if not errors:
            try:
                if editing:
                    db.execute("UPDATE marks SET student_id=?, subject=?, obtained=?, maximum=? WHERE id=?",
                               (data["student_id"], data["subject"], float(data["obtained"]),
                                float(data["maximum"]), mid))
                else:
                    db.execute("INSERT INTO marks (student_id, subject, obtained, maximum) VALUES (?,?,?,?)",
                               (data["student_id"], data["subject"], float(data["obtained"]),
                                float(data["maximum"])))
                flash("Marks saved.", "success")
                return redirect(url_for("marks_list"))
            except sqlite3.IntegrityError:
                errors.append("Marks for this student and subject already exist. Edit them instead.")
    return render_template("marks/form.html", mark=data, errors=errors, editing=editing, mid=mid,
                           all_students=db.query("SELECT id, name FROM students ORDER BY name"))


@app.route("/marks/add", methods=["GET", "POST"])
@login_required("admin", "faculty")
def marks_add():
    return marks_form(False)


@app.route("/marks/<int:mid>/edit", methods=["GET", "POST"])
@login_required("admin", "faculty")
def marks_edit(mid):
    mark = db.query("SELECT * FROM marks WHERE id = ?", (mid,), one=True)
    if mark is None:
        abort(404)
    return marks_form(True, mark, mid)


@app.route("/marks/<int:mid>/delete", methods=["POST"])
@login_required("admin", "faculty")
def marks_delete(mid):
    db.execute("DELETE FROM marks WHERE id = ?", (mid,))
    flash("Marks record deleted.", "info")
    return redirect(url_for("marks_list"))


# =====================================================================
# 8. NOTICES (everyone can read, admin manages)
# =====================================================================
def read_notice(form):
    data = {"title": form.get("title", "").strip(),
            "description": form.get("description", "").strip(),
            "notice_date": form.get("notice_date", "").strip()}
    errors = []
    if len(data["title"]) < 3:
        errors.append("Title must be at least 3 characters.")
    if len(data["description"]) < 5:
        errors.append("Description must be at least 5 characters.")
    if not valid_date(data["notice_date"]):
        errors.append("Please choose a valid date.")
    return data, errors


@app.route("/notices")
@login_required()
def notices_list():
    q = request.args.get("q", "").strip()
    sql, args = "SELECT * FROM notices WHERE 1=1", []
    if q:
        sql += " AND (title LIKE ? OR description LIKE ?)"
        args += [f"%{q}%", f"%{q}%"]
    return render_template("notices/list.html", notices=db.query(sql + " ORDER BY notice_date DESC, id DESC", args), q=q)


def notice_form(editing, notice=None, nid=None):
    data, errors = (dict(notice) if notice else {"notice_date": date.today().isoformat()}), []
    if request.method == "POST":
        data, errors = read_notice(request.form)
        if not errors:
            if editing:
                db.execute("UPDATE notices SET title=?, description=?, notice_date=? WHERE id=?",
                           (data["title"], data["description"], data["notice_date"], nid))
            else:
                db.execute("INSERT INTO notices (title, description, notice_date) VALUES (?,?,?)",
                           (data["title"], data["description"], data["notice_date"]))
            flash("Notice saved.", "success")
            return redirect(url_for("notices_list"))
    return render_template("notices/form.html", notice=data, errors=errors, editing=editing, nid=nid)


@app.route("/notices/add", methods=["GET", "POST"])
@login_required("admin")
def notices_add():
    return notice_form(False)


@app.route("/notices/<int:nid>/edit", methods=["GET", "POST"])
@login_required("admin")
def notices_edit(nid):
    notice = db.query("SELECT * FROM notices WHERE id = ?", (nid,), one=True)
    if notice is None:
        abort(404)
    return notice_form(True, notice, nid)


@app.route("/notices/<int:nid>/delete", methods=["POST"])
@login_required("admin")
def notices_delete(nid):
    db.execute("DELETE FROM notices WHERE id = ?", (nid,))
    flash("Notice deleted.", "info")
    return redirect(url_for("notices_list"))


# =====================================================================
# 9. PUBLIC PAGES AND ERROR HANDLING
# =====================================================================
@app.route("/")
def home():
    return render_template("index.html")


@app.route("/about-cloud")
def about_cloud():
    return render_template("about_cloud.html")


ERRORS = {
    400: ("Request not accepted", "Your form session expired or was invalid. Please go back, refresh the page and try again."),
    403: ("Access denied", "You do not have permission to open this page with your account."),
    404: ("Page not found", "The page you are looking for does not exist or was moved."),
    500: ("Something went wrong", "An unexpected error occurred on the server. Please try again later."),
}


def make_error_handler(code):
    def handler(error):
        title, message = ERRORS[code]
        return render_template("error.html", code=code, title=title, message=message), code
    return handler


for _code in ERRORS:
    app.register_error_handler(_code, make_error_handler(_code))


# =====================================================================
# START (local use). On Render, gunicorn runs "app:app" instead.
# =====================================================================
if __name__ == "__main__":
    app.run(host="0.0.0.0", port=int(os.environ.get("PORT", 5000)),
            debug=os.environ.get("FLASK_DEBUG", "1") == "1")
