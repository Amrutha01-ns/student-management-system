from flask import Flask, request, jsonify, render_template, send_file, redirect, session
from flask_mail import Mail, Message
from datetime import datetime, date
import calendar
import psycopg2
import io
import random
import bcrypt
import requests
import os

from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle
from reportlab.lib import colors
from reportlab.lib.styles import getSampleStyleSheet
from reportlab.lib import pagesizes
import socket
socket.setdefaulttimeout(30)
app = Flask(__name__)

app.secret_key = os.environ.get("SECRET_KEY", "abc123")
otp_store = {}
app.config['MAIL_MAX_EMAILS'] = None
app.config['MAIL_SUPPRESS_SEND'] = False
app.config['MAIL_SERVER']         = 'smtp.gmail.com'
app.config['MAIL_PORT']    = 465
app.config['MAIL_USE_TLS'] = False
app.config['MAIL_USE_SSL'] = True
app.config['MAIL_USERNAME']       = os.environ.get("MAIL_USERNAME", "adminemaila@gmail.com")
app.config['MAIL_PASSWORD']       = os.environ.get("MAIL_PASSWORD", "tajtshstdtjmzshr")
app.config['MAIL_DEFAULT_SENDER'] = os.environ.get("MAIL_USERNAME", "adminemaila@gmail.com")

mail = Mail(app)

print("========== MAIL CONFIG ==========")
print("MAIL_SERVER =", app.config['MAIL_SERVER'])
print("MAIL_PORT =", app.config['MAIL_PORT'])
print("MAIL_USE_TLS =", app.config['MAIL_USE_TLS'])
print("MAIL_USERNAME =", app.config['MAIL_USERNAME'])
print("MAIL_PASSWORD EXISTS =", bool(app.config['MAIL_PASSWORD']))
print("=================================")

def get_db_connection():
    return psycopg2.connect(
        os.environ.get("DATABASE_URL", "postgresql://postgres.snlfgcbehrzhttykeabv:r2wnu8ner67daoxl@aws-0-ap-south-1.pooler.supabase.com:5432/postgres")
    )

def get_session_student_id():
    user_id = session.get("user_id")
    role    = session.get("role")
    if not user_id or role not in {"parent", "student"}:
        return None
    conn = get_db_connection()
    cur  = conn.cursor()
    if role == "parent":
        cur.execute("SELECT linked_student_id FROM users WHERE id = %s", (user_id,))
    else:
        cur.execute("SELECT student_id FROM students WHERE user_id = %s", (user_id,))
    row = cur.fetchone()
    cur.close()
    conn.close()
    return row[0] if row else None

def enforce_student_access(student_id):
    role = session.get("role")
    if role not in {"parent", "student"}:
        return None
    allowed = get_session_student_id()
    if not allowed:
        return jsonify({"status": "error", "message": "No linked student found"}), 403
    if int(student_id) != int(allowed):
        return jsonify({"status": "error", "message": "Unauthorized student access"}), 403
    return None

def build_student_context(student_id):
    conn = get_db_connection()
    cur  = conn.cursor()
    cur.execute("""
        SELECT u.name, u.father_name, u.mother_name, s.roll_number, s.section, s.standard
        FROM students s
        JOIN users u ON u.id = s.user_id
        WHERE s.student_id = %s
    """, (student_id,))
    profile = cur.fetchone()
    if not profile:
        cur.close()
        conn.close()
        return None
    cur.execute("""
        SELECT exam_type, exam_date, kannada, english, physics, chemistry, maths, biology, total_marks
        FROM marks WHERE student_id = %s ORDER BY exam_date DESC LIMIT 1
    """, (student_id,))
    latest_marks = cur.fetchone()
    cur.execute("""
        SELECT
            COUNT(*) FILTER (WHERE status = 'Present') AS present,
            COUNT(*) FILTER (WHERE status = 'Absent')  AS absent,
            COUNT(*)                                    AS total
        FROM attendance WHERE student_id = %s
    """, (student_id,))
    present_count, absent_count, total_days = cur.fetchone()
    cur.execute("""
        SELECT status FROM attendance
        WHERE student_id = %s AND attendance_date = CURRENT_DATE
    """, (student_id,))
    today_row = cur.fetchone()
    cur.close()
    conn.close()
    student_name, father_name, mother_name, roll_number, section, standard = profile
    percentage   = round((present_count / total_days) * 100) if total_days > 0 else 0
    today_status = today_row[0] if today_row else "Not Marked"
    marks_payload = None
    if latest_marks:
        exam_type, exam_date, kannada, english, physics, chemistry, maths, biology, total_marks = latest_marks
        marks_payload = {
            "exam_type": exam_type, "exam_date": str(exam_date),
            "kannada": kannada, "english": english,
            "physics": physics, "chemistry": chemistry,
            "maths": maths, "biology": biology,
            "total": total_marks,
            "percentage": round((total_marks / 600) * 100, 2)
        }
    return {
        "student_id": student_id, "name": student_name,
        "father_name": father_name, "mother_name": mother_name,
        "roll_number": roll_number, "section": section, "standard": standard,
        "class": f"{standard}-{section}",
        "today_attendance_status": today_status,
        "attendance_summary": {
            "present": present_count, "absent": absent_count,
            "total": total_days, "percentage": percentage
        },
        "latest_marks": marks_payload
    }

otp_store = {}

@app.route("/send-otp", methods=["POST"])
def send_otp():
    data  = request.get_json()
    phone = data.get("phone", "").strip()
    if not phone or len(phone) != 10 or not phone.isdigit():
        return jsonify({"status": "error", "message": "Valid 10-digit phone required"})
    otp = str(random.randint(100000, 999999))
    otp_store[phone] = otp
    print(f"OTP for {phone}: {otp}")
    return jsonify({"status": "success", "otp": otp})

@app.route("/verify-otp", methods=["POST"])
def verify_otp():
    data  = request.get_json()
    phone = data.get("phone", "").strip()
    otp   = data.get("otp",   "").strip()
    if otp_store.get(phone) == otp:
        otp_store.pop(phone)
        session['otp_verified'] = True
        return jsonify({"status": "success"})
    return jsonify({"status": "error", "message": "Invalid or expired OTP"})

@app.route("/validate_contact", methods=["POST"])
def validate_contact():
    data  = request.get_json()
    email = data.get("email", "").strip().lower()
    phone = data.get("phone", "").strip()
    role  = data.get("role", "").strip()
    if not email or not phone:
        return jsonify({"valid": False, "message": "Email and phone are required"})
    import re
    email_pattern = r'^[\w\.-]+@[\w\.-]+\.\w{2,}$'
    if not re.match(email_pattern, email):
        return jsonify({"valid": False, "message": "Invalid email format"})
    if not re.match(r'^\d{10}$', phone):
        return jsonify({"valid": False, "message": "Phone must be exactly 10 digits"})
    conn = get_db_connection()
    cur  = conn.cursor()
    cur.execute(
        "SELECT phone FROM users WHERE LOWER(email) = %s AND role = %s",
        (email, role)
    )
    row = cur.fetchone()
    cur.close()
    conn.close()
    if row and row[0] != phone:
        return jsonify({"valid": False, "message": "This email is already registered with a different phone number"})
    return jsonify({"valid": True})

@app.route("/login", methods=["POST"])
def login():
    data     = request.get_json(silent=True) or request.form
    name     = data.get("name", "").strip()
    phone    = data.get("phone", "").strip()
    email    = data.get("email", "").strip().lower()
    role     = data.get("role", "").strip()
    password = data.get("password", "")
    conn = get_db_connection()
    cur  = conn.cursor()
    cur.execute("""
        SELECT id, name, role, password FROM users
        WHERE LOWER(name) = LOWER(%s)
          AND LOWER(email) = LOWER(%s)
          AND role         = %s
    """, (name, email, role))
    user = cur.fetchone()
    if not user:
        cur.close()
        conn.close()
        return jsonify({"status": "error", "message": "No account found. Please register first."})
    user_id, found_name, found_role, hashed_password = user
    if not bcrypt.checkpw(password.encode('utf-8'), hashed_password.encode('utf-8')):
        cur.close()
        conn.close()
        return jsonify({"status": "error", "message": "Incorrect password."})
    session['user_id'] = user_id
    session['role']    = found_role
    session['name']    = found_name
    if found_role == 'student':
        cur.execute("SELECT student_id FROM students WHERE user_id = %s", (user_id,))
        row = cur.fetchone()
        session['student_id'] = row[0] if row else None
    elif found_role == 'parent':
        cur.execute("SELECT linked_student_id FROM users WHERE id = %s", (user_id,))
        row = cur.fetchone()
        session['student_id'] = row[0] if row else None
    else:
        session['student_id'] = None
    cur.close()
    conn.close()
    return jsonify({
        "status": "success", "user_id": user_id,
        "name": found_name, "role": found_role,
        "student_id": session.get('student_id')
    })

@app.route("/reset_password", methods=["POST"])
def reset_password():
    data     = request.get_json()
    email    = data.get("email", "").strip().lower()
    new_pass = data.get("new_password", "")
    if not email or not new_pass:
        return jsonify({"status": "error", "message": "Email and password required"})
    if len(new_pass) < 6:
        return jsonify({"status": "error", "message": "Password too short"})
    hashed = bcrypt.hashpw(new_pass.encode('utf-8'), bcrypt.gensalt()).decode('utf-8')
    conn = get_db_connection()
    cur  = conn.cursor()
    cur.execute("UPDATE users SET password = %s WHERE LOWER(email) = %s", (hashed, email))
    cur.execute("UPDATE students SET password = %s WHERE LOWER(email) = %s", (hashed, email))
    cur.execute("UPDATE teachers SET password = %s WHERE LOWER(email) = %s", (hashed, email))
    cur.execute("UPDATE parents  SET password = %s WHERE LOWER(email) = %s", (hashed, email))
    conn.commit()
    cur.close()
    conn.close()
    return jsonify({"status": "success"})

def _set_session(session, cur, user_id, name, role):
    session['user_id'] = user_id
    session['role']    = role
    session['name']    = name
    if role == 'student':
        cur.execute("SELECT student_id FROM students WHERE user_id = %s", (user_id,))
        r = cur.fetchone()
        session['student_id'] = r[0] if r else None
    elif role == 'parent':
        cur.execute("SELECT linked_student_id FROM users WHERE id = %s", (user_id,))
        r = cur.fetchone()
        session['student_id'] = r[0] if r else None
    else:
        session['student_id'] = None

# ── CHECK EXISTING ──
# No status check — just find if account exists and log them in
@app.route("/check_existing", methods=["POST"])
def check_existing():
    data              = request.get_json()
    name              = data.get("name",              "").strip()
    phone             = data.get("phone",             "").strip()
    email             = data.get("email",             "").strip().lower()
    role              = data.get("role",              "").strip()
    child_roll_number = data.get("child_roll_number", "").strip()

    if not name or not email or not role:
        return jsonify({"exists": False, "message": "All fields required"})

    conn = get_db_connection()
    cur  = conn.cursor()

    cur.execute("""
        SELECT id, name, role FROM users
        WHERE LOWER(name) = LOWER(%s)
          AND LOWER(email) = LOWER(%s)
          AND role = %s
    """, (name, email, role))
    row = cur.fetchone()

    if not row:
        cur.close()
        conn.close()
        return jsonify({"exists": False, "message": "No account found. Please register."})

    user_id, found_name, found_role = row

    if found_role != role:
        cur.close()
        conn.close()
        return jsonify({"exists": False, "message": "No account found for this role."})

    if role == "parent":
        if not child_roll_number:
            cur.close()
            conn.close()
            return jsonify({"exists": False, "message": "Please enter child roll number."})
        cur.execute("""
            SELECT s.roll_number FROM users u
            JOIN students s ON s.student_id = u.linked_student_id
            WHERE u.id = %s
        """, (user_id,))
        linked = cur.fetchone()
        if not linked or str(linked[0]).strip() != child_roll_number:
            cur.close()
            conn.close()
            return jsonify({"exists": False, "roll_mismatch": True, "message": "Roll number does not match."})

    _set_session(session, cur, user_id, found_name, role)
    cur.close()
    conn.close()
    return jsonify({"exists": True, "name": found_name})

# ── REGISTER ──
@app.route("/register", methods=["GET", "POST"])
def register():
    if request.method == "GET":
        return render_template("register.html")

    if not session.get('otp_verified'):
        return jsonify({"status": "error", "message": "OTP verification required"})
    session.pop('otp_verified')

    data        = request.get_json(silent=True) or {}
    name        = data.get("name",        "").strip()
    phone       = data.get("phone",       "").strip()
    email       = data.get("email",       "").strip().lower()
    role        = data.get("role")
    password    = data.get("password",    "")
    father_name = data.get("father_name", "")
    mother_name = data.get("mother_name", "")

    conn = get_db_connection()
    cur  = conn.cursor()

    # Check if account already exists — if so, just log them in
    cur.execute("""
        SELECT id, name, role FROM users
        WHERE LOWER(name) = LOWER(%s)
          AND LOWER(email) = LOWER(%s)
          AND role = %s
    """, (name, email, role))
    existing = cur.fetchone()

    if existing:
        existing_id, existing_name, existing_role = existing
        _set_session(session, cur, existing_id, existing_name, role)
        student_id = session.get('student_id')
        cur.close()
        conn.close()
        return jsonify({
            "status":            "success",
            "name":              existing_name,
            "role":              role,
            "user_id":           existing_id,
            "student_id":        student_id,
            "linked_student_id": student_id
        })

    # ── Brand new user ──
    if role == "student":
        standard    = data.get("standard")
        section     = data.get("section")
        roll_number = data.get("roll_number")
        cur.execute("""
            SELECT student_id FROM students
            WHERE roll_number = %s AND standard = %s AND section = %s
        """, (roll_number, standard, section))
        if cur.fetchone():
            cur.close()
            conn.close()
            return jsonify({"status": "error", "message": "A student with this roll number already exists in this class."})

    hashed_password = bcrypt.hashpw(password.encode("utf-8"), bcrypt.gensalt()).decode("utf-8")

    # status = "approved" so they can log in right away
    cur.execute("""
        INSERT INTO users (name, phone, email, role, password, father_name, mother_name, status)
        VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
        RETURNING id
    """, (name, phone, email, role, hashed_password, father_name, mother_name, "approved"))
    user_id = cur.fetchone()[0]

    student_id = None

    if role == "student":
        cur.execute("""
            INSERT INTO students (user_id, name, phone, email, password, standard, section, roll_number)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
            RETURNING student_id
        """, (user_id, name, phone, email, hashed_password, standard, section, roll_number))
        student_id = cur.fetchone()[0]

    elif role == "teacher":
        cur.execute("""
            INSERT INTO teachers (user_id, name, phone, email, password)
            VALUES (%s, %s, %s, %s, %s)
        """, (user_id, name, phone, email, hashed_password))

    elif role == "parent":
        child_name        = data.get("child_name", "")
        child_roll_number = data.get("child_roll_number")
        parent_standard   = data.get("parent_standard")
        parent_section    = data.get("parent_section")
        linked_student_id = None

        if child_roll_number:
            cur.execute("""
                SELECT student_id FROM students
                WHERE roll_number = %s
                  AND (%s IS NULL OR standard = %s)
                  AND (%s IS NULL OR section  = %s)
            """, (child_roll_number, parent_standard, parent_standard, parent_section, parent_section))
            student_row = cur.fetchone()
            if not student_row:
                conn.rollback()
                cur.close()
                conn.close()
                return jsonify({"status": "error", "message": "Child's roll number not found. Please check and try again."})
            linked_student_id = student_row[0]
            student_id = linked_student_id
            cur.execute("UPDATE users SET linked_student_id = %s WHERE id = %s", (linked_student_id, user_id))

        cur.execute("""
            INSERT INTO parents (user_id, name, phone, email, password, child_name, linked_student_id)
            VALUES (%s, %s, %s, %s, %s, %s, %s)
        """, (user_id, name, phone, email, hashed_password, child_name, linked_student_id))

    conn.commit()

    # Log them in immediately after registration
    session['user_id']    = user_id
    session['role']       = role
    session['name']       = name
    session['student_id'] = student_id

    cur.close()
    conn.close()

    return jsonify({
        "status":            "success",
        "user_id":           user_id,
        "name":              name,
        "role":              role,
        "student_id":        student_id,
        "linked_student_id": student_id
    })

@app.route("/get_students/<standard>/<section>")
def get_students(standard, section):
    conn = get_db_connection()
    cur  = conn.cursor()
    cur.execute("""
        SELECT student_id, name, roll_number FROM students
        WHERE standard = %s AND section = %s
        ORDER BY roll_number
    """, (standard, section))
    rows = cur.fetchall()
    cur.close()
    conn.close()
    return jsonify([{"student_id": r[0], "name": r[1], "roll_number": r[2] or "N/A"} for r in rows])

@app.route("/student_dashboard")
def student_dashboard():
    if 'user_id' not in session: return redirect("/login_page")
    if session.get('role') != 'student': return redirect("/login_page")
    return render_template("student_dashboard.html")

@app.route("/teacher_dashboard")
def teacher_dashboard():
    if 'user_id' not in session: return redirect("/login_page")
    if session.get('role') != 'teacher': return redirect("/login_page")
    return render_template("teacher_dashboard.html")

@app.route("/parent_dashboard")
def parent_dashboard():
    if 'user_id' not in session: return redirect("/login_page")
    if session.get('role') != 'parent': return redirect("/login_page")
    conn = get_db_connection()
    cur  = conn.cursor()
    cur.execute("""
        SELECT announcement_id, title, content, created_at FROM announcements
        WHERE target_role = 'parent' OR target_role = 'all'
        ORDER BY created_at DESC
    """)
    rows = cur.fetchall()
    cur.close()
    conn.close()
    announcements = [{"id": r[0], "title": r[1], "content": r[2], "date": str(r[3])} for r in rows]
    return render_template("parent_dashboard.html", announcements=announcements)

@app.route("/parent_attendance")
def parent_attendance():
    if 'user_id' not in session: return redirect("/login_page")
    return render_template("parent_attendance.html")

@app.route("/admin_dashboard")
def admin_dashboard():
    if 'user_id' not in session: return redirect("/login_page")
    if session.get('role') != 'admin': return redirect("/login_page")
    return render_template("admin_dashboard.html")

@app.route("/me")
def me():
    if 'user_id' not in session:
        return jsonify({"status": "error"}), 401
    active_student_id = get_session_student_id()
    return jsonify({
        "user_id": session['user_id'], "name": session.get("name"),
        "role": session.get('role'), "linked_student_id": active_student_id,
        "student_id": active_student_id
    })

@app.route("/get_student_context", methods=["GET"])
def get_student_context():
    if 'user_id' not in session:
        return jsonify({"status": "error", "message": "Not logged in"}), 401
    role       = session.get("role")
    student_id = session.get("student_id")
    if role in {"parent", "student"}:
        if not student_id:
            return jsonify({"status": "error", "message": "No linked student found"}), 404
    else:
        student_id = request.args.get("student_id", type=int)
        if not student_id:
            return jsonify({"status": "error", "message": "student_id is required"}), 400
    context = build_student_context(student_id)
    if not context:
        return jsonify({"status": "error", "message": "Student not found"}), 404
    return jsonify({"status": "success", "role": role, "student": context,
                    "parent_name": session.get("name") if role == "parent" else None})

@app.route("/get_student_profile/<int:user_id>")
def get_student_profile(user_id):
    if session.get("role") in {"parent", "student"}:
        allowed_student_id = get_session_student_id()
        if not allowed_student_id:
            return jsonify({"status": "error", "message": "No linked student found"}), 403
        conn_check = get_db_connection()
        cur_check  = conn_check.cursor()
        cur_check.execute("SELECT user_id FROM students WHERE student_id = %s", (allowed_student_id,))
        row_check  = cur_check.fetchone()
        cur_check.close()
        conn_check.close()
        if not row_check or row_check[0] != user_id:
            return jsonify({"status": "error", "message": "Unauthorized profile access"}), 403
    conn = get_db_connection()
    cur  = conn.cursor()
    cur.execute("""
        SELECT u.name, u.father_name, u.mother_name, s.roll_number, s.section
        FROM users u LEFT JOIN students s ON s.user_id = u.id WHERE u.id = %s
    """, (user_id,))
    row = cur.fetchone()
    cur.close()
    conn.close()
    if not row: return jsonify({"status": "not_found"})
    return jsonify({"name": row[0], "father_name": row[1], "mother_name": row[2],
                    "roll_number": row[3], "section": row[4]})

@app.route("/get_student_profile_by_student/<int:student_id>")
def get_student_profile_by_student(student_id):
    access_error = enforce_student_access(student_id)
    if access_error: return access_error
    conn = get_db_connection()
    cur  = conn.cursor()
    cur.execute("""
        SELECT u.name, u.father_name, u.mother_name, s.roll_number, s.section, s.standard
        FROM students s JOIN users u ON u.id = s.user_id WHERE s.student_id = %s
    """, (student_id,))
    row = cur.fetchone()
    cur.close()
    conn.close()
    if not row: return jsonify({"status": "not_found"})
    return jsonify({"name": row[0], "father_name": row[1], "mother_name": row[2],
                    "roll_number": row[3], "section": row[4], "standard": row[5]})

@app.route("/teacher_marks")
def teacher_marks():
    return render_template("teacher_marks.html")

@app.route("/add_marks", methods=["POST"])
def add_marks():
    if session.get("role") != "teacher":
        return jsonify({"status": "error", "message": "Unauthorized"}), 403

    data        = request.json
    student_id  = data.get("student_id")
    exam_type   = data.get("exam_type")
    exam_date   = data.get("exam_date")
    kannada     = data.get("kannada",   0)
    english     = data.get("english",   0)
    physics     = data.get("physics",   0)
    chemistry   = data.get("chemistry", 0)
    maths       = data.get("maths",     0)
    biology     = data.get("biology",   0)
    total_marks = kannada + english + physics + chemistry + maths + biology

    conn = get_db_connection()
    cur  = conn.cursor()

    # Look up actual teacher_id from teachers table using session user_id
    user_id = session.get("user_id")
    cur.execute("SELECT teacher_id FROM teachers WHERE user_id = %s", (user_id,))
    teacher_row = cur.fetchone()

    if not teacher_row:
        cur.close()
        conn.close()
        return jsonify({"status": "error", "message": "Teacher record not found. Contact admin."}), 404

    actual_teacher_id = teacher_row[0]

    cur.execute("""
        INSERT INTO marks (student_id, teacher_id, exam_type, exam_date,
             kannada, english, physics, chemistry, maths, biology, total_marks, is_published)
        VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s, FALSE) RETURNING marks_id
    """, (student_id, actual_teacher_id, exam_type, exam_date,
          kannada, english, physics, chemistry, maths, biology, total_marks))

    new_mark_id = cur.fetchone()[0]
    conn.commit()
    cur.close()
    conn.close()
    return jsonify({"status": "success", "message": "Marks saved", "mark_id": new_mark_id})

@app.route("/broadcast_marks", methods=["POST"])
def broadcast_marks():
    if session.get("role") != "teacher":
        return jsonify({"status": "error", "message": "Unauthorized"}), 403
    data       = request.get_json()
    mark_id    = data.get("mark_id")
    student_id = data.get("student_id")
    conn = get_db_connection()
    cur  = conn.cursor()
    if mark_id:
        cur.execute("UPDATE marks SET is_published = TRUE WHERE marks_id = %s AND is_published = FALSE", (mark_id,))
    else:
        cur.execute("""
            UPDATE marks SET is_published = TRUE WHERE marks_id = (
                SELECT marks_id FROM marks WHERE student_id = %s AND is_published = FALSE
                ORDER BY exam_date DESC LIMIT 1)
        """, (student_id,))
    conn.commit()
    updated = cur.rowcount
    cur.close()
    conn.close()
    if updated == 0: return jsonify({"status": "error", "message": "Nothing to broadcast"})
    return jsonify({"status": "success", "message": "Marks broadcasted to student"})

@app.route("/get_marks/<int:student_id>", methods=["GET"])
def get_marks(student_id):
    access_error = enforce_student_access(student_id)
    if access_error: return access_error
    conn = get_db_connection()
    cur  = conn.cursor()
    cur.execute("""
        SELECT exam_type, kannada, english, physics, chemistry, maths, biology, total_marks
        FROM marks WHERE student_id = %s ORDER BY exam_date DESC LIMIT 1
    """, (student_id,))
    row = cur.fetchone()
    cur.close()
    conn.close()
    if not row: return jsonify({"status": "no_marks"})
    exam_type, kannada, english, physics, chemistry, maths, biology, total_marks = row
    percentage = round((total_marks / 600) * 100, 2)
    return jsonify({
        "status": "success", "exam_type": exam_type,
        "subjects": [
            {"subject": "Kannada",   "marks": kannada},
            {"subject": "English",   "marks": english},
            {"subject": "Physics",   "marks": physics},
            {"subject": "Chemistry", "marks": chemistry},
            {"subject": "Maths",     "marks": maths},
            {"subject": "Biology",   "marks": biology},
        ],
        "total": total_marks, "max_total": 600,
        "percentage": percentage, "result": "PASS" if percentage >= 35 else "FAIL"
    })

@app.route("/get_subject_progress/<int:student_id>/<subject>")
def get_subject_progress(student_id, subject):
    access_error = enforce_student_access(student_id)
    if access_error: return access_error
    if subject not in {"kannada", "english", "physics", "chemistry", "maths", "biology"}:
        return jsonify({"error": "Invalid subject"}), 400
    conn = get_db_connection()
    cur  = conn.cursor()
    cur.execute(f"SELECT exam_type, {subject} FROM marks WHERE student_id = %s ORDER BY exam_date", (student_id,))
    rows = cur.fetchall()
    cur.close()
    conn.close()
    return jsonify({"exams": [r[0] for r in rows], "marks": [r[1] for r in rows]})

@app.route("/get_performance_summary/<int:student_id>", methods=["GET"])
def get_performance_summary(student_id):
    access_error = enforce_student_access(student_id)
    if access_error: return access_error
    conn = get_db_connection()
    cur  = conn.cursor()
    cur.execute("""
        SELECT kannada, english, physics, chemistry, maths, biology, total_marks
        FROM marks WHERE student_id = %s ORDER BY exam_date DESC LIMIT 1
    """, (student_id,))
    row = cur.fetchone()
    cur.close()
    conn.close()
    if not row: return jsonify({"status": "no_data"})
    kannada, english, physics, chemistry, maths, biology, total_marks = row
    subjects = [
        {"subject": "Kannada",   "marks": kannada},
        {"subject": "English",   "marks": english},
        {"subject": "Physics",   "marks": physics},
        {"subject": "Chemistry", "marks": chemistry},
        {"subject": "Maths",     "marks": maths},
        {"subject": "Biology",   "marks": biology},
    ]
    percentage = round((total_marks / 600) * 100, 2)
    highest    = max(subjects, key=lambda x: x["marks"])
    lowest     = min(subjects, key=lambda x: x["marks"])
    if percentage >= 85:   grade, remark = "A+", "Excellent Performance"
    elif percentage >= 70: grade, remark = "A",  "Very Good Performance"
    elif percentage >= 50: grade, remark = "B",  "Average Performance"
    else:                  grade, remark = "C",  "Needs Attention"
    return jsonify({"status": "success", "percentage": percentage, "grade": grade, "remark": remark,
                    "highest_subject": highest, "lowest_subject": lowest})

@app.route("/scorecard_embed/<int:student_id>")
def scorecard_embed(student_id):
    access_error = enforce_student_access(student_id)
    if access_error: return access_error
    conn = get_db_connection()
    cur  = conn.cursor()
    cur.execute("""
        SELECT u.name, u.father_name, s.roll_number, s.section, s.standard
        FROM users u LEFT JOIN students s ON s.user_id = u.id WHERE s.student_id = %s
    """, (student_id,))
    student = cur.fetchone()
    cur.execute("""
        SELECT kannada, english, physics, chemistry, maths, biology, exam_type, exam_date, total_marks
        FROM marks WHERE student_id = %s ORDER BY exam_date DESC LIMIT 1
    """, (student_id,))
    data = cur.fetchone()
    cur.close()
    conn.close()
    if not student: return "<p style='color:red;padding:20px;'>Student not found.</p>", 404
    if not data:
        return render_template("scorecard_fragment.html", student_name=student[0],
            father_name=student[1] or "", reg_no=student[2] or "N/A",
            class_name=f"{student[4] or ''} - {student[3] or ''}",
            kannada=0, english=0, physics=0, chemistry=0, maths=0, biology=0,
            total_marks=0, percentage=0, result_status="No Marks Yet", exam_type="N/A", exam_date="N/A")
    kannada, english, physics, chemistry, maths, biology, exam_type, exam_date, total_marks = data
    percentage = round((total_marks / 600) * 100, 2)
    if percentage >= 85:   result_status = "DISTINCTION"
    elif percentage >= 60: result_status = "FIRST CLASS"
    elif percentage >= 50: result_status = "SECOND CLASS"
    elif percentage >= 35: result_status = "PASS"
    else:                  result_status = "FAIL"
    return render_template("scorecard_fragment.html", student_name=student[0],
        father_name=student[1] or "", reg_no=student[2] or "N/A",
        class_name=f"{student[4] or ''} - {student[3] or ''}",
        kannada=kannada, english=english, physics=physics, chemistry=chemistry,
        maths=maths, biology=biology, total_marks=total_marks, percentage=percentage,
        result_status=result_status, exam_type=exam_type, exam_date=exam_date)

@app.route("/mark_attendance", methods=["POST"])
def mark_attendance():
    data       = request.json
    student_id = data.get("student_id")
    status     = data.get("status")
    conn = get_db_connection()
    cur  = conn.cursor()
    cur.execute("""
        INSERT INTO attendance (student_id, attendance_date, status)
        VALUES (%s, CURRENT_DATE, %s)
        ON CONFLICT (student_id, attendance_date) DO UPDATE SET status = EXCLUDED.status
    """, (student_id, status))
    conn.commit()
    cur.close()
    conn.close()
    return jsonify({"status": "success"})

@app.route("/get_attendance/<int:student_id>", methods=["GET"])
def get_attendance(student_id):
    access_error = enforce_student_access(student_id)
    if access_error: return access_error
    conn = get_db_connection()
    cur  = conn.cursor()
    cur.execute("SELECT status FROM attendance WHERE student_id = %s", (student_id,))
    records = cur.fetchall()
    cur.close()
    conn.close()
    if not records: return jsonify({"status": "no_data"})
    total_days   = len(records)
    present_days = sum(1 for r in records if r[0] == "Present")
    percentage   = round((present_days / total_days) * 100, 2)
    performance  = "Good" if percentage >= 75 else "Warning" if percentage >= 50 else "Critical"
    return jsonify({"status": "success", "total_days": total_days,
                    "present_days": present_days, "percentage": percentage, "performance": performance})

@app.route("/get_today_attendance/<int:student_id>")
def get_today_attendance(student_id):
    access_error = enforce_student_access(student_id)
    if access_error: return access_error
    conn = get_db_connection()
    cur  = conn.cursor()
    cur.execute("SELECT status FROM attendance WHERE student_id = %s AND attendance_date = CURRENT_DATE", (student_id,))
    row = cur.fetchone()
    cur.close()
    conn.close()
    if not row: return jsonify({"status": "not_marked"})
    return jsonify({"status": "success", "attendance_status": row[0]})

@app.route("/get_attendance_summary/<int:student_id>")
def get_attendance_summary(student_id):
    access_error = enforce_student_access(student_id)
    if access_error: return access_error
    conn = get_db_connection()
    cur  = conn.cursor()
    cur.execute("""
        SELECT COUNT(*) FILTER (WHERE status = 'Present'),
               COUNT(*) FILTER (WHERE status = 'Absent'), COUNT(*)
        FROM attendance WHERE student_id = %s
    """, (student_id,))
    total_present, total_absent, total_days = cur.fetchone()
    cur.close()
    conn.close()
    percentage = round((total_present / total_days) * 100) if total_days > 0 else 0
    return jsonify({"present": total_present, "absent": total_absent, "percentage": percentage})

@app.route("/get_month_attendance/<int:student_id>/<int:year>/<int:month>", methods=["GET"])
def get_month_attendance(student_id, year, month):
    access_error = enforce_student_access(student_id)
    if access_error: return access_error
    conn = get_db_connection()
    cur  = conn.cursor()
    start_date = f"{year}-{month:02d}-01"
    end_date   = f"{year}-{month:02d}-{calendar.monthrange(year, month)[1]}"
    cur.execute("""
        SELECT attendance_date, status FROM attendance
        WHERE student_id = %s AND attendance_date BETWEEN %s AND %s
    """, (student_id, start_date, end_date))
    records = cur.fetchall()
    cur.close()
    conn.close()
    return jsonify({str(r[0]): r[1] for r in records})

@app.route("/get_parent_student_info/<int:student_id>")
def get_parent_student_info(student_id):
    access_error = enforce_student_access(student_id)
    if access_error: return access_error
    conn = get_db_connection()
    cur  = conn.cursor()
    cur.execute("""
        SELECT u.name, s.standard, s.section, s.roll_number
        FROM students s JOIN users u ON u.id = s.user_id WHERE s.student_id = %s
    """, (student_id,))
    student_row = cur.fetchone()
    parent_name = None
    if session.get("role") == "parent" and session.get("user_id"):
        cur.execute("SELECT name FROM users WHERE id = %s", (session["user_id"],))
        p = cur.fetchone()
        if p: parent_name = p[0]
    cur.close()
    conn.close()
    if not student_row: return jsonify({"status": "error"})
    return jsonify({"student_name": student_row[0], "parent_name": parent_name or "Parent",
                    "standard": student_row[1], "section": student_row[2],
                    "roll_number": student_row[3], "class": f"{student_row[1]}-{student_row[2]}"})

@app.route("/attendence_db")
def attendence_db():
    return render_template("attendence_db.html")

@app.route("/teacher_announcement", methods=["GET"])
def teacher_announcement():
    return render_template("annteach.html")

@app.route("/add_announcement", methods=["POST"])
def add_announcement():
    data           = request.get_json()
    title          = data.get("title")
    content        = data.get("content")
    posted_by      = data.get("posted_by")
    target_role    = data.get("target_role")
    target_section = data.get("target_section")
    conn = get_db_connection()
    cur  = conn.cursor()
    cur.execute("""
        INSERT INTO announcements (title, content, posted_by, target_role, target_section)
        VALUES (%s, %s, %s, %s, %s)
    """, (title, content, posted_by, target_role, target_section))
    conn.commit()
    cur.close()
    conn.close()
    return jsonify({"status": "Announcement posted successfully"})

@app.route("/login_page")
def login_page():
    return render_template("login_page.html")

@app.route("/")
def home():
    return redirect("/login_page")

@app.route("/get_announcements/<role>/<section>")
def get_announcements(role, section):
    conn = get_db_connection()
    cur  = conn.cursor()
    cur.execute("""
        SELECT a.title, a.content, a.created_at, u.name
        FROM announcements a LEFT JOIN users u ON u.id = a.posted_by
        WHERE a.target_role = %s OR a.target_role = 'all'
        ORDER BY a.created_at DESC LIMIT 10
    """, (role,))
    rows = cur.fetchall()
    cur.close()
    conn.close()
    return jsonify([{"title": r[0], "content": r[1], "date": str(r[2]), "posted_by": r[3] or "Teacher"} for r in rows])

@app.route("/view_announcement/<int:id>")
def view_announcement(id):
    conn = get_db_connection()
    cur  = conn.cursor()
    cur.execute("SELECT title, content, posted_by, created_at FROM announcements WHERE announcement_id = %s", (id,))
    row = cur.fetchone()
    cur.close()
    conn.close()
    if not row: return "Announcement not found"
    return render_template("announcement_view.html",
                           announcement={"title": row[0], "content": row[1], "posted_by": row[2], "date": row[3]})

@app.route("/parent_announcements")
def parent_announcements():
    return render_template("parent_announcements.html")

@app.route("/student_announcements")
def student_announcements():
    return render_template("student_announcements.html")

@app.route("/download_marksheet/<int:student_id>")
def download_marksheet(student_id):
    access_error = enforce_student_access(student_id)
    if access_error: return access_error
    conn = get_db_connection()
    cur  = conn.cursor()
    cur.execute("""
        SELECT u.name, u.father_name, u.mother_name
        FROM users u JOIN students s ON s.user_id = u.id WHERE s.student_id = %s
    """, (student_id,))
    student = cur.fetchone()
    cur.execute("""
        SELECT exam_type, kannada, english, physics, chemistry, maths, biology, total_marks
        FROM marks WHERE student_id = %s ORDER BY exam_date DESC LIMIT 1
    """, (student_id,))
    row = cur.fetchone()
    cur.close()
    conn.close()
    if not student or not row: return "No marks available", 404
    name, father, mother = student
    exam_type, kannada, english, physics, chemistry, maths, biology, total_marks = row
    percentage = round((total_marks / 600) * 100, 2)
    result     = "PASS" if percentage >= 35 else "FAIL"
    buffer = io.BytesIO()
    doc    = SimpleDocTemplate(buffer, pagesize=pagesizes.A4)
    styles = getSampleStyleSheet()
    elements = [
        Paragraph("AET SCHOOL OF EXCELLENCE", styles["Title"]), Spacer(1, 20),
        Paragraph(f"Student Name: {name}", styles["Normal"]),
        Paragraph(f"Father Name: {father}", styles["Normal"]),
        Paragraph(f"Mother Name: {mother}", styles["Normal"]),
        Paragraph(f"Exam: {exam_type}", styles["Normal"]), Spacer(1, 20),
    ]
    table_data = [["Subject", "Marks Obtained", "Total Marks"],
                  ["Kannada", kannada, 100], ["English", english, 100],
                  ["Physics", physics, 100], ["Chemistry", chemistry, 100],
                  ["Maths", maths, 100],     ["Biology", biology, 100]]
    table = Table(table_data)
    table.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, 0), colors.grey),
        ("GRID", (0, 0), (-1, -1), 1, colors.black),
        ("ALIGN", (1, 1), (-1, -1), "CENTER"),
    ]))
    elements += [table, Spacer(1, 20),
        Paragraph(f"Total: {total_marks} / 600", styles["Normal"]),
        Paragraph(f"Percentage: {percentage}%", styles["Normal"]),
        Paragraph(f"Result: {result}", styles["Normal"]), Spacer(1, 40),
        Paragraph("Class Teacher Signature", styles["Normal"]), Spacer(1, 20),
        Paragraph("Principal Signature", styles["Normal"]),
    ]
    doc.build(elements)
    buffer.seek(0)
    return send_file(buffer, as_attachment=True, download_name="marksheet.pdf", mimetype="application/pdf")

@app.route("/graph_analysis")
def graph_analysis():
    return render_template("graph_parent.html")

@app.route("/debug_session")
def debug_session():
    return jsonify(dict(session))

@app.route("/logout")
def logout():
    session.clear()
    return redirect("/login_page")

if __name__ == "__main__":
    app.run(debug=True)