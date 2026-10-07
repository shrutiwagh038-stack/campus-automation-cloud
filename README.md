# Campus Automation System

A cloud-hosted web application for centralized college management. Administrators, faculty and
students log in with different roles to manage records, attendance, marks and notices.
Built as an MSc Data Science academic project for the **Cloud Computing** subject.

## Features
- **Landing page** and **About Cloud Deployment** page
- **Login with 3 roles** (Admin, Faculty, Student) - hashed passwords, session login, role-protected routes
- **Admin**: dashboard with charts, manage students, faculty, marks, notices, view attendance
- **Faculty**: dashboard, mark attendance, attendance reports, manage students, upload marks, notices, profile
- **Student**: dashboard, own profile, own attendance %, own marks, notices
- Search and filters (students, faculty, notices, attendance, marks)
- Validation (e.g. obtained marks cannot exceed maximum marks), delete confirmation, friendly 400/403/404/500 pages

## Technology stack
| Layer | Technology |
|---|---|
| Backend | Python, Flask |
| Frontend | HTML5, CSS3, Bootstrap 5, Chart.js (loaded from CDN) |
| Database | SQLite (prototype) - PostgreSQL recommended for production |
| Cloud | GitHub + Render (gunicorn web server) |

## System architecture
```
User -> Web Browser -> Internet -> Render Cloud -> Flask Application -> Database
```

## Database (6 tables)
| Table | Purpose | Relationships |
|---|---|---|
| users | login accounts (hashed password, role) | `student_id` -> students, `faculty_id` -> faculty |
| students | name, email, department, semester | - |
| faculty | name, email, department, designation | - |
| attendance | one row per student per date (Present/Absent) | `student_id` -> students (UNIQUE per date) |
| marks | subject, obtained, maximum | `student_id` -> students (UNIQUE per subject) |
| notices | title, description, date | - |

Deleting a student also deletes their login, attendance and marks (`ON DELETE CASCADE`).

## Run locally (VS Code)
```bash
# 1. open the project folder in VS Code, then open Terminal > New Terminal
python -m venv venv

# 2. activate it
venv\Scripts\activate          # Windows
source venv/bin/activate       # Mac / Linux

# 3. install packages and start
pip install -r requirements.txt
python app.py
```
Open http://127.0.0.1:5000 . An internet connection is needed because Bootstrap and Chart.js load from a CDN.

**Demo logins** (created automatically on first run):
| Role | Email | Password |
|---|---|---|
| Admin | admin@campus.edu | Admin@123 |
| Faculty | meera@campus.edu | Faculty@123 |
| Student | shruti@campus.edu | Student@123 |

New students/faculty added by the admin get an automatic login; the temporary password is shown once.
To reset everything, stop the app and delete `campus.db`.

## Deploy on Render
1. Push this project to GitHub.
2. Render dashboard -> **New + -> Web Service** -> connect the GitHub repository.
3. Build Command: `pip install -r requirements.txt`
4. Start Command: `gunicorn app:app`
5. Environment variables: `SECRET_KEY` = any long random text, optional `ADMIN_PASSWORD` = your own admin password.
6. Create the service. Every `git push` to GitHub redeploys automatically.

> **Important:** on Render's free plan the disk is temporary, so `campus.db` can reset after a restart/redeploy
> (demo data is recreated automatically). For permanent data use a managed PostgreSQL database.

## Project screenshots
_Add screenshots here (landing page, admin dashboard, attendance, marks)._

## Limitations
- SQLite is a single file - fine for a prototype, not for many simultaneous users.
- Single small server instance: the *concept* of cloud scalability is explained, not demonstrated.
- No password reset / email features. Demo passwords must be changed before real use.

## Future scope
PostgreSQL migration, persistent cloud storage, password change/reset, timetable and fee modules,
exportable PDF/Excel reports, email/SMS notifications, automated tests.
