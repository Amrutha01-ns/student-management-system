console.log("attendence JS loaded");
let attendanceData = {};

async function loadStudents() {
    const className = document.getElementById("classSelect").value;
    const section = document.getElementById("sectionSelect").value;

    if (!className || !section) {
        alert("Select class and section");
        return;
    }

    const response = await fetch(`/get_students_by_class/${className}/${section}`);
    const data = await response.json();

    const table = document.getElementById("attendanceTable");
    const tbody = table.querySelector("tbody");

    tbody.innerHTML = "";
    attendanceData = {};

    data.students.forEach(student => {
        const row = document.createElement("tr");

        row.innerHTML = `
            <td>${student.roll_number}</td>
            <td>${student.name}</td>
            <td>
                <button class="present-btn" onclick="markAttendance(${student.id}, 'Present')">Present</button>
                <button class="absent-btn" onclick="markAttendance(${student.id}, 'Absent')">Absent</button>
            </td>
        `;

        tbody.appendChild(row);
    });

    table.style.display = "table";
    document.getElementById("submitAttendanceBtn").style.display = "block";
}

function markAttendance(studentId, status) {
    attendanceData[studentId] = status;
}

async function submitAttendance() {

    for (const studentId in attendanceData) {
        await fetch("/add_attendance", {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({
                student_id: studentId,
                teacher_id: 1, // Later dynamic
                date: new Date().toISOString().split("T")[0],
                status: attendanceData[studentId]
            })
        });
    }

    alert("Attendance Submitted Successfully 🚀");
}
let marksSheetData = {};

async function loadStudentsForMarks() {

    const className = document.getElementById("marksClass").value;
    const section = document.getElementById("marksSectionSelect").value;

    if (!className || !section) {
        alert("Select class and section");
        return;
    }

    const response = await fetch(`/get_students_by_class/${className}/${section}`);
    const data = await response.json();

    const container = document.getElementById("marksSheetContainer");
    container.innerHTML = "";
    marksSheetData = {};

    data.students.forEach(student => {

        const card = document.createElement("div");
        card.className = "marks-card";

        card.innerHTML = `
            <h4>${student.roll_number} - ${student.name}</h4>

            ${generateSubjectInput(student.id, "kannada")}
            ${generateSubjectInput(student.id, "english")}
            ${generateSubjectInput(student.id, "physics")}
            ${generateSubjectInput(student.id, "chemistry")}
            ${generateSubjectInput(student.id, "maths")}
            ${generateSubjectInput(student.id, "biology")}
        `;

        container.appendChild(card);
    });

    document.getElementById("submitMarksBtn").style.display = "block";
}

function generateSubjectInput(studentId, subject) {
    return `
        <div class="subject-row">
            <label>${subject.toUpperCase()}</label>
            <input type="number" min="0" max="100"
                onchange="setMarks(${studentId}, '${subject}', this.value)">
            <button class="absent-btn"
                onclick="setAbsent(${studentId}, '${subject}')">AB</button>
        </div>
    `;
}

function setMarks(studentId, subject, value) {
    if (!marksSheetData[studentId]) marksSheetData[studentId] = {};
    marksSheetData[studentId][subject] = value;
}

function setAbsent(studentId, subject) {
    if (!marksSheetData[studentId]) marksSheetData[studentId] = {};
    marksSheetData[studentId][subject] = "AB";
}

async function submitMarksSheet() {

    const className = document.getElementById("marksClass").value;
    const section = document.getElementById("marksSectionSelect").value;
    const examName = document.getElementById("examName").value;

    for (const studentId in marksSheetData) {

        await fetch("/add_full_marks", {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({
                student_id: studentId,
                teacher_id: 1,
                class: className,
                section: section,
                exam_name: examName,
                ...marksSheetData[studentId]
            })
        });
    }

    alert("Marks Sheet Submitted Successfully 🚀");
}