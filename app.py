from flask import Flask, request, jsonify, render_template, send_file, redirect
from datetime import datetime, date
import calendar
import psycopg2
import io

from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle
from reportlab.lib import colors
from reportlab.lib.styles import getSampleStyleSheet
from reportlab.lib import pagesizes

app = Flask(__name__)

# -------------------- DATABASE CONNECTION --------------------

def get_db_connection():
    return psycopg2.connect(
        host="localhost",
        database="sms_db",
        user="postgres",
        password="f25ns@2029"
    )

# -------------------- HOME --------------------

@app.route("/")
def home():
    return redirect("/login_page")

# -------------------- AUTH ROUTES --------------------

@app.route("/login_page")
def login_page():
    return render_template("login.html")

@app.route("/login", methods=["POST"])
def login():
    data = request.get_json(silent=True) or request.form

    email    = data.get("email")
    password = data.get("password")

    conn = get_db_connection()
    cur  = conn.cursor()

    cur.execute("""
        SELECT id, name, role, section
        FROM users
        WHERE email = %s AND password = %s
    """, (email, password))

    user = cur.fetchone()
    cur.close()
    conn.close()

    if not user:
        return jsonify({"status": "error", "message": "Invalid credentials"})

    return jsonify({
        "status":  "success",
        "id":      user[0],
        "name":    user[1],
        "role":    user[2],
        "section": user[3]
    })

@app.route("/register", methods=["GET", "POST"])
def register():
    if request.method == "GET":
        return render_template("register.html")

    # Accept JSON or form data
    data = request.get_json(silent=True)

    if data:
        name         = data.get("name")
        phone        = data.get("phone")
        role         = data.get("role")
        password     = data.get("password")
        father_name  = data.get("father_name")
        mother_name  = data.get("mother_name")
        email        = data.get("email")
    else:
        name         = request.form.get("name")
        phone        = request.form.get("phone")
        role         = request.form.get("role")
        password     = request.form.get("password")
        father_name  = request.form.get("father_name")
        mother_name  = request.form.get("mother_name")
        email        = request.form.get("email")

    conn = get_db_connection()
    cur  = conn.cursor()

    cur.execute("""
        INSERT INTO users (name, phone, role, password, father_name, mother_name, email)
        VALUES (%s, %s, %s, %s, %s, %s, %s)
        RETURNING id
    """, (name, phone, role, password, father_name, mother_name, email))

    user_id = cur.fetchone()[0]
    conn.commit()
    cur.close()
    conn.close()

    return jsonify({
        "status":  "success",
        "role":    role,
        "user_id": user_id
    })

@app.route("/logout")
def logout():
    return redirect("/login_page")

# -------------------- DASHBOARD ROUTES --------------------

@app.route("/student_dashboard")
def student_dashboard():
    return render_template("student_dashboard.html")

@app.route("/teacher_dashboard")
def teacher_dashboard():
    return render_template("teacher_dashboard.html")

@app.route("/parent_dashboard")
def parent_dashboard():
    conn = get_db_connection()
    cur  = conn.cursor()

    cur.execute("""
        SELECT announcement_id, title, content, created_at
        FROM announcements
        WHERE target_role = 'parent' OR target_role = 'all'
        ORDER BY created_at DESC
    """)

    rows = cur.fetchall()
    cur.close()
    conn.close()

    announcements = [
        {"id": r[0], "title": r[1], "content": r[2], "date": str(r[3])}
        for r in rows
    ]

    return render_template("parent_dashboard.html", announcements=announcements)

@app.route("/admin_dashboard")
def admin_dashboard():
    return render_template("admin_dashboard.html")

# -------------------- STUDENT PROFILE --------------------

@app.route("/get_student_profile/<int:user_id>")
def get_student_profile(user_id):
    conn = get_db_connection()
    cur  = conn.cursor()

    cur.execute("""
        SELECT name, father_name, mother_name
        FROM users
        WHERE id = %s
    """, (user_id,))

    row = cur.fetchone()
    cur.close()
    conn.close()

    if not row:
        return jsonify({"status": "not_found"})

    return jsonify({
        "name":        row[0],
        "father_name": row[1],
        "mother_name": row[2]
    })

# -------------------- MARKS --------------------

@app.route("/teacher_marks")
def teacher_marks():
    return render_template("teacher_marks.html")

@app.route("/add_marks", methods=["POST"])
def add_marks():
    data = request.json

    student_id  = data.get("student_id")
    exam_type   = data.get("exam_type")
    kannada     = data.get("kannada")
    english     = data.get("english")
    physics     = data.get("physics")
    chemistry   = data.get("chemistry")
    maths       = data.get("maths")
    biology     = data.get("biology")

    conn = get_db_connection()
    cur  = conn.cursor()

    cur.execute("""
        INSERT INTO marks
            (student_id, exam_type, kannada, english, physics, chemistry, maths, biology)
        VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
    """, (student_id, exam_type, kannada, english, physics, chemistry, maths, biology))

    conn.commit()
    cur.close()
    conn.close()

    return jsonify({"status": "Marks added successfully"})

@app.route("/get_marks/<int:student_id>", methods=["GET"])
def get_marks(student_id):
    conn = get_db_connection()
    cur  = conn.cursor()

    cur.execute("""
        SELECT exam_type, kannada, english, physics, chemistry, maths, biology
        FROM marks
        WHERE student_id = %s
        ORDER BY id DESC
        LIMIT 1
    """, (student_id,))

    row = cur.fetchone()
    cur.close()
    conn.close()

    if not row:
        return jsonify({"status": "no_marks"})

    exam_type, kannada, english, physics, chemistry, maths, biology = row

    subjects = [
        {"subject": "Kannada",   "marks": kannada,   "total": 100},
        {"subject": "English",   "marks": english,   "total": 100},
        {"subject": "Physics",   "marks": physics,   "total": 100},
        {"subject": "Chemistry", "marks": chemistry, "total": 100},
        {"subject": "Maths",     "marks": maths,     "total": 100},
        {"subject": "Biology",   "marks": biology,   "total": 100},
    ]

    total      = sum([kannada, english, physics, chemistry, maths, biology])
    max_total  = 600
    percentage = round((total / max_total) * 100, 2)
    result     = "PASS" if percentage >= 35 else "FAIL"

    return jsonify({
        "status":    "success",
        "exam_type": exam_type,
        "subjects":  subjects,
        "total":     total,
        "max_total": max_total,
        "percentage": percentage,
        "result":    result
    })

@app.route("/get_subject_progress/<int:student_id>/<subject>")
def get_subject_progress(student_id, subject):
    # Whitelist subjects to prevent SQL injection
    allowed = {"kannada", "english", "physics", "chemistry", "maths", "biology"}
    if subject not in allowed:
        return jsonify({"error": "Invalid subject"}), 400

    conn = get_db_connection()
    cur  = conn.cursor()

    cur.execute(f"""
        SELECT exam_type, {subject}
        FROM marks
        WHERE student_id = %s
        ORDER BY id
    """, (student_id,))

    rows = cur.fetchall()
    cur.close()
    conn.close()

    return jsonify({
        "exams": [r[0] for r in rows],
        "marks": [r[1] for r in rows]
    })

@app.route("/get_performance_summary/<int:student_id>", methods=["GET"])
def get_performance_summary(student_id):
    conn = get_db_connection()
    cur  = conn.cursor()

    cur.execute("""
        SELECT kannada, english, physics, chemistry, maths, biology
        FROM marks
        WHERE student_id = %s
        ORDER BY id DESC
        LIMIT 1
    """, (student_id,))

    row = cur.fetchone()
    cur.close()
    conn.close()

    if not row:
        return jsonify({"status": "no_data"})

    subject_names = ["Kannada", "English", "Physics", "Chemistry", "Maths", "Biology"]
    subjects = [{"subject": name, "marks": marks} for name, marks in zip(subject_names, row)]

    total      = sum(row)
    max_total  = len(row) * 100
    percentage = round((total / max_total) * 100, 2)

    highest = max(subjects, key=lambda x: x["marks"])
    lowest  = min(subjects, key=lambda x: x["marks"])

    if percentage >= 85:
        grade, remark = "A+", "Excellent Performance"
    elif percentage >= 70:
        grade, remark = "A", "Very Good Performance"
    elif percentage >= 50:
        grade, remark = "B", "Average Performance"
    else:
        grade, remark = "C", "Needs Attention"

    return jsonify({
        "status":          "success",
        "percentage":      percentage,
        "grade":           grade,
        "remark":          remark,
        "highest_subject": highest,
        "lowest_subject":  lowest
    })

# -------------------- SCORECARD --------------------

@app.route("/scorecard/<int:student_id>")
def scorecard(student_id):
    conn = get_db_connection()
    cur  = conn.cursor()

    cur.execute("""
        SELECT name, father_name
        FROM users
        WHERE id = %s
    """, (student_id,))
    student = cur.fetchone()

    cur.execute("""
        SELECT kannada, english, physics, chemistry, maths, biology, exam_type
        FROM marks
        WHERE student_id = %s
        ORDER BY id DESC
        LIMIT 1
    """, (student_id,))
    data = cur.fetchone()

    cur.close()
    conn.close()

    if not data or not student:
        return "No marks available"

    kannada, english, physics, chemistry, maths, biology, exam_type = data
    total      = kannada + english + physics + chemistry + maths + biology
    percentage = round((total / 600) * 100, 2)

    if percentage >= 85:
        result_status = "DISTINCTION"
    elif percentage >= 60:
        result_status = "FIRST CLASS"
    elif percentage >= 50:
        result_status = "SECOND CLASS"
    elif percentage >= 35:
        result_status = "PASS"
    else:
        result_status = "FAIL"

    return render_template(
        "scorecard_parent.html",
        student_name  = student[0],
        father_name   = student[1],
        reg_no        = f"AET{student_id:03d}",
        class_name    = "PUC",
        kannada       = kannada,
        english       = english,
        physics       = physics,
        chemistry     = chemistry,
        maths         = maths,
        biology       = biology,
        total_marks   = total,
        percentage    = percentage,
        result_status = result_status,
        exam_type     = exam_type
    )

# -------------------- DOWNLOAD MARKSHEET --------------------

@app.route("/download_marksheet/<int:student_id>")
def download_marksheet(student_id):
    conn = get_db_connection()
    cur  = conn.cursor()

    cur.execute("""
        SELECT name, father_name, mother_name
        FROM users
        WHERE id = %s
    """, (student_id,))
    student = cur.fetchone()

    cur.execute("""
        SELECT exam_type, kannada, english, physics, chemistry, maths, biology
        FROM marks
        WHERE student_id = %s
        ORDER BY id DESC
        LIMIT 1
    """, (student_id,))
    row = cur.fetchone()

    cur.close()
    conn.close()

    if not student or not row:
        return "No marks available", 404

    name, father, mother = student
    exam_type, kannada, english, physics, chemistry, maths, biology = row

    subjects = [
        ["Kannada",   kannada,   100],
        ["English",   english,   100],
        ["Physics",   physics,   100],
        ["Chemistry", chemistry, 100],
        ["Maths",     maths,     100],
        ["Biology",   biology,   100],
    ]

    total      = sum([kannada, english, physics, chemistry, maths, biology])
    max_total  = 600
    percentage = round((total / max_total) * 100, 2)
    result     = "PASS" if percentage >= 35 else "FAIL"

    buffer = io.BytesIO()
    doc    = SimpleDocTemplate(buffer, pagesize=pagesizes.A4)
    styles = getSampleStyleSheet()

    elements = [
        Paragraph("AET SCHOOL OF EXCELLENCE", styles["Title"]),
        Spacer(1, 20),
        Paragraph(f"Student Name: {name}",   styles["Normal"]),
        Paragraph(f"Father Name: {father}",  styles["Normal"]),
        Paragraph(f"Mother Name: {mother}",  styles["Normal"]),
        Paragraph(f"Exam: {exam_type}",      styles["Normal"]),
        Spacer(1, 20),
    ]

    table_data = [["Subject", "Marks Obtained", "Total Marks"]] + subjects
    table = Table(table_data)
    table.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, 0), colors.grey),
        ("GRID",       (0, 0), (-1, -1), 1, colors.black),
        ("ALIGN",      (1, 1), (-1, -1), "CENTER"),
    ]))

    elements += [
        table,
        Spacer(1, 20),
        Paragraph(f"Total: {total} / {max_total}", styles["Normal"]),
        Paragraph(f"Percentage: {percentage}%",    styles["Normal"]),
        Paragraph(f"Result: {result}",             styles["Normal"]),
        Spacer(1, 40),
        Paragraph("Class Teacher Signature",       styles["Normal"]),
        Spacer(1, 20),
        Paragraph("Principal Signature",           styles["Normal"]),
    ]

    doc.build(elements)
    buffer.seek(0)

    return send_file(
        buffer,
        as_attachment=True,
        download_name="marksheet.pdf",
        mimetype="application/pdf"
    )

# -------------------- ATTENDANCE --------------------

@app.route("/mark_attendance", methods=["POST"])
def mark_attendance():
    data = request.json

    student_id = data["student_id"]
    att_date   = data["date"]
    status     = data["status"]

    conn = get_db_connection()
    cur  = conn.cursor()

    cur.execute("""
        INSERT INTO attendance (student_id, attendance_date, status)
        VALUES (%s, %s, %s)
        ON CONFLICT (student_id, attendance_date) DO UPDATE SET status = EXCLUDED.status
    """, (student_id, att_date, status))

    conn.commit()
    cur.close()
    conn.close()

    return jsonify({"message": "Attendance recorded"})

@app.route("/get_attendance/<int:student_id>", methods=["GET"])
def get_attendance(student_id):
    conn = get_db_connection()
    cur  = conn.cursor()

    cur.execute("""
        SELECT status
        FROM attendance
        WHERE student_id = %s
    """, (student_id,))

    records = cur.fetchall()
    cur.close()
    conn.close()

    if not records:
        return jsonify({"status": "no_data"})

    total_days   = len(records)
    present_days = sum(1 for r in records if r[0].lower() == "present")
    percentage   = round((present_days / total_days) * 100, 2)

    if percentage >= 75:
        performance = "Good"
    elif percentage >= 50:
        performance = "Warning"
    else:
        performance = "Critical"

    return jsonify({
        "status":       "success",
        "total_days":   total_days,
        "present_days": present_days,
        "percentage":   percentage,
        "performance":  performance
    })

@app.route("/get_today_attendance/<int:student_id>", methods=["GET"])
def get_today_attendance(student_id):
    today = date.today()

    conn = get_db_connection()
    cur  = conn.cursor()

    cur.execute("""
        SELECT status
        FROM attendance
        WHERE student_id = %s AND attendance_date = %s
    """, (student_id, today))

    record = cur.fetchone()
    cur.close()
    conn.close()

    if not record:
        return jsonify({"status": "not_marked", "message": "Attendance not marked for today"})

    return jsonify({"status": "success", "attendance_status": record[0]})

@app.route("/get_month_attendance/<int:student_id>/<int:year>/<int:month>", methods=["GET"])
def get_month_attendance(student_id, year, month):
    conn = get_db_connection()
    cur  = conn.cursor()

    start_date = f"{year}-{month:02d}-01"
    last_day   = calendar.monthrange(year, month)[1]
    end_date   = f"{year}-{month:02d}-{last_day}"

    cur.execute("""
        SELECT attendance_date, status
        FROM attendance
        WHERE student_id = %s AND attendance_date BETWEEN %s AND %s
    """, (student_id, start_date, end_date))

    records = cur.fetchall()
    cur.close()
    conn.close()

    return jsonify({str(r[0]): r[1] for r in records})

@app.route("/get_attendance_summary/<int:student_id>")
def get_attendance_summary(student_id):
    conn = get_db_connection()
    cur  = conn.cursor()

    cur.execute("""
        SELECT
            COUNT(*) FILTER (WHERE status = 'Present') AS total_present,
            COUNT(*) FILTER (WHERE status = 'Absent')  AS total_absent,
            COUNT(*)                                    AS total_days
        FROM attendance
        WHERE student_id = %s
    """, (student_id,))

    result = cur.fetchone()
    cur.close()
    conn.close()

    total_present, total_absent, total_days = result
    percentage = round((total_present / total_days) * 100) if total_days > 0 else 0

    return jsonify({
        "present":    total_present,
        "absent":     total_absent,
        "percentage": percentage
    })

# -------------------- ATTENDANCE DB PAGE --------------------

@app.route("/attendence_db")
def attendence_db():
    return render_template("attendence_db.html")

# -------------------- ANNOUNCEMENTS --------------------

@app.route("/teacher_announcement", methods=["GET", "POST"])
def teacher_announcement():
    if request.method == "POST":
        title   = request.form["title"]
        message = request.form["message"]

        conn = get_db_connection()
        cur  = conn.cursor()

        cur.execute("""
            INSERT INTO announcements
                (title, content, posted_by, target_role, target_section, created_at)
            VALUES (%s, %s, %s, %s, %s, CURRENT_TIMESTAMP)
        """, (title, message, "teacher", "parent", "A"))

        conn.commit()
        cur.close()
        conn.close()

        return redirect("/teacher_announcement")

    return render_template("teacher_announcement.html")

@app.route("/add_announcement", methods=["POST"])
def add_announcement():
    data = request.get_json()

    title          = data.get("title")
    content        = data.get("content")
    posted_by      = data.get("posted_by")
    target_role    = data.get("target_role")
    target_section = data.get("target_section")

    conn = get_db_connection()
    cur  = conn.cursor()

    cur.execute("""
        INSERT INTO announcements
            (title, content, posted_by, target_role, target_section, created_at)
        VALUES (%s, %s, %s, %s, %s, CURRENT_TIMESTAMP)
    """, (title, content, posted_by, target_role, target_section))

    conn.commit()
    cur.close()
    conn.close()

    return jsonify({"status": "Announcement posted successfully"})

@app.route("/get_announcements/<role>/<section>")
def get_announcements(role, section):
    conn = get_db_connection()
    cur  = conn.cursor()

    cur.execute("""
        SELECT title, content, created_at
        FROM announcements
        WHERE target_role = %s
           OR (target_role = 'student' AND target_section = %s)
        ORDER BY created_at DESC
        LIMIT 10
    """, (role, section))

    rows = cur.fetchall()
    cur.close()
    conn.close()

    return jsonify([
        {"title": r[0], "content": r[1], "date": str(r[2])}
        for r in rows
    ])

@app.route("/view_announcement/<int:id>")
def view_announcement(id):
    conn = get_db_connection()
    cur  = conn.cursor()

    cur.execute("""
        SELECT title, content, posted_by, created_at
        FROM announcements
        WHERE announcement_id = %s
    """, (id,))

    row = cur.fetchone()
    cur.close()
    conn.close()

    if not row:
        return "Announcement not found"

    return render_template("announcement_view.html", announcement={
        "title":     row[0],
        "content":   row[1],
        "posted_by": row[2],
        "date":      row[3]
    })

# -------------------- GRAPH --------------------

@app.route("/graph_analysis")
def graph_analysis():
    return render_template("graph_parent.html")

# -------------------- RUN SERVER --------------------

if __name__ == "__main__":
    app.run(debug=True)
