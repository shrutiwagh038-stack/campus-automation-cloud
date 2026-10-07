"""
db.py - Database helper for the Campus Automation System.

Everything that talks to the database lives here, so app.py stays clean.
SQLite is used for the academic prototype. The database file location can be
changed with the DATABASE_PATH environment variable.
"""
import os
import sqlite3

from flask import g
from werkzeug.security import generate_password_hash

BASE_DIR = os.path.abspath(os.path.dirname(__file__))
DATABASE = os.environ.get("DATABASE_PATH", os.path.join(BASE_DIR, "campus.db"))


# ---------------------------------------------------------------
# Connection helpers
# ---------------------------------------------------------------
def connect():
    """Open a new connection (foreign keys switched ON - SQLite needs this every time)."""
    conn = sqlite3.connect(DATABASE)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


def get_db():
    """One connection per web request, closed automatically afterwards."""
    if "db" not in g:
        g.db = connect()
    return g.db


def close_db(error=None):
    conn = g.pop("db", None)
    if conn is not None:
        conn.close()


def query(sql, args=(), one=False):
    """Run a SELECT. Returns a list of rows, or a single row if one=True."""
    cur = get_db().execute(sql, args)
    rows = cur.fetchall()
    cur.close()
    if one:
        return rows[0] if rows else None
    return rows


def execute(sql, args=()):
    """Run INSERT / UPDATE / DELETE and save it. Returns the cursor."""
    conn = get_db()
    cur = conn.execute(sql, args)
    conn.commit()
    return cur


# ---------------------------------------------------------------
# Database structure (6 tables)
# ---------------------------------------------------------------
SCHEMA = """
CREATE TABLE IF NOT EXISTS students (
    id         INTEGER PRIMARY KEY AUTOINCREMENT,
    name       TEXT NOT NULL,
    email      TEXT NOT NULL UNIQUE,
    department TEXT NOT NULL,
    semester   INTEGER NOT NULL CHECK (semester BETWEEN 1 AND 8)
);

CREATE TABLE IF NOT EXISTS faculty (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    name        TEXT NOT NULL,
    email       TEXT NOT NULL UNIQUE,
    department  TEXT NOT NULL,
    designation TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS users (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    name          TEXT NOT NULL,
    email         TEXT NOT NULL UNIQUE,
    password_hash TEXT NOT NULL,
    role          TEXT NOT NULL CHECK (role IN ('admin', 'faculty', 'student')),
    student_id    INTEGER REFERENCES students(id) ON DELETE CASCADE,
    faculty_id    INTEGER REFERENCES faculty(id)  ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS attendance (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    student_id      INTEGER NOT NULL REFERENCES students(id) ON DELETE CASCADE,
    attendance_date TEXT NOT NULL,
    status          TEXT NOT NULL CHECK (status IN ('Present', 'Absent')),
    UNIQUE (student_id, attendance_date)
);

CREATE TABLE IF NOT EXISTS marks (
    id         INTEGER PRIMARY KEY AUTOINCREMENT,
    student_id INTEGER NOT NULL REFERENCES students(id) ON DELETE CASCADE,
    subject    TEXT NOT NULL,
    obtained   REAL NOT NULL,
    maximum    REAL NOT NULL,
    CHECK (maximum > 0 AND obtained >= 0 AND obtained <= maximum),
    UNIQUE (student_id, subject)
);

CREATE TABLE IF NOT EXISTS notices (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    title       TEXT NOT NULL,
    description TEXT NOT NULL,
    notice_date TEXT NOT NULL
);
"""


def init_db():
    """Create tables (if missing) and add demo data on the very first start.

    Seeding on start matters on Render's free plan, where the disk is
    temporary and the database file can be recreated after a restart.
    """
    conn = connect()
    conn.executescript(SCHEMA)
    conn.commit()
    if conn.execute("SELECT COUNT(*) FROM users").fetchone()[0] == 0:
        seed_demo_data(conn)
    conn.close()


# ---------------------------------------------------------------
# Demo data (only inserted when the database is empty)
# ---------------------------------------------------------------
def seed_demo_data(conn):
    admin_pw = os.environ.get("ADMIN_PASSWORD", "Admin@123")
    conn.execute(
        "INSERT INTO users (name, email, password_hash, role) VALUES (?,?,?,?)",
        ("System Administrator", "admin@campus.edu", generate_password_hash(admin_pw), "admin"),
    )

    faculty = [
        ("Dr. Meera Kulkarni", "meera@campus.edu", "Data Science", "Professor"),
        ("Prof. Rahul Deshmukh", "rahul@campus.edu", "Computer Science", "Assistant Professor"),
    ]
    for name, email, dept, desig in faculty:
        cur = conn.execute(
            "INSERT INTO faculty (name, email, department, designation) VALUES (?,?,?,?)",
            (name, email, dept, desig),
        )
        conn.execute(
            "INSERT INTO users (name, email, password_hash, role, faculty_id) VALUES (?,?,?,?,?)",
            (name, email, generate_password_hash("Faculty@123"), "faculty", cur.lastrowid),
        )

    students = [
        ("Shruti Wagh", "shruti@campus.edu", "Data Science", 2),
        ("Aarav Patil", "aarav@campus.edu", "Data Science", 2),
        ("Neha Joshi", "neha@campus.edu", "Computer Science", 4),
        ("Rohan More", "rohan@campus.edu", "Information Technology", 3),
        ("Priya Shinde", "priya@campus.edu", "Data Science", 2),
    ]
    student_ids = []
    for name, email, dept, sem in students:
        cur = conn.execute(
            "INSERT INTO students (name, email, department, semester) VALUES (?,?,?,?)",
            (name, email, dept, sem),
        )
        student_ids.append(cur.lastrowid)
        conn.execute(
            "INSERT INTO users (name, email, password_hash, role, student_id) VALUES (?,?,?,?,?)",
            (name, email, generate_password_hash("Student@123"), "student", cur.lastrowid),
        )

    # A few days of sample attendance (simple repeating pattern, not random)
    from datetime import date, timedelta
    for sid in student_ids:
        for day in range(1, 11):
            d = (date.today() - timedelta(days=day)).isoformat()
            status = "Absent" if (sid + day) % 5 == 0 else "Present"
            conn.execute(
                "INSERT INTO attendance (student_id, attendance_date, status) VALUES (?,?,?)",
                (sid, d, status),
            )

    sample_marks = [("Machine Learning", 78, 100), ("Cloud Computing", 85, 100), ("Statistics", 41, 50)]
    for sid in student_ids:
        for i, (subject, got, mx) in enumerate(sample_marks):
            conn.execute(
                "INSERT INTO marks (student_id, subject, obtained, maximum) VALUES (?,?,?,?)",
                (sid, subject, min(got + sid - i, mx), mx),
            )

    notices = [
        ("Welcome to Campus Automation", "This portal gives students, faculty and administrators one central place for attendance, marks and notices.", date.today().isoformat()),
        ("Mid-Semester Examination Schedule", "Mid-semester exams begin next month. Detailed timetable will be shared on this portal.", date.today().isoformat()),
    ]
    conn.executemany("INSERT INTO notices (title, description, notice_date) VALUES (?,?,?)", notices)
    conn.commit()
