# =========================
# FULL PRODUCTION APP
# =========================

from flask import Flask, render_template, request, redirect, send_file
from flask_login import LoginManager, UserMixin, login_user, login_required, logout_user, current_user
import pandas as pd
import sqlite3
from datetime import datetime, timedelta
import os
import smtplib
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer
from reportlab.lib.styles import getSampleStyleSheet
from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
import matplotlib.pyplot as plt
import io
import base64

# =========================
# APP CONFIG
# =========================

app = Flask(__name__)
app.secret_key = "supersecretkey"

login_manager = LoginManager()
login_manager.init_app(app)

DATA_DIR = "/data"
DB_PATH = os.path.join(DATA_DIR, "database.db")

DB_PATH = os.path.join(DATA_DIR, "database.db")

# =========================
# USERS
# =========================

USERS = {
    "BigBossSteve": {"password": "Masterlogin3217", "role": "attorney"},
    "Samarth": {"password": "Samarth1711", "role": "employee"}
}

EMPLOYEES = ["Kavish", "Chirag", "Sahil", "Tushar"]

# =========================
# DATABASE
# =========================

def init_db():
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute('''
        CREATE TABLE IF NOT EXISTS records (
            employee TEXT,
            date TEXT,
            records_expected INTEGER,
            records_received INTEGER,
            no_of_cases INTEGER,
            no_of_facilities_total INTEGER,
            records_should_be_received INTEGER,
            records_if_all_docs_available INTEGER
        )
    ''')
    conn.commit()
    conn.close()

init_db()

# =========================
# SAFE DIVISION
# =========================

def safe_divide(n, d):
    return n / d if d not in [0, None] else 0

def normalize(value, min_v, max_v):
    if max_v == min_v:
        return 1
    return (value - min_v) / (max_v - min_v)

# =========================
# PERFORMANCE ENGINE
# =========================

def calculate_scores(data):

    rr = data["records_received"]
    rexp = data["records_expected"]
    rshould = data["records_should_be_received"]
    rdocs = data["records_if_all_docs_available"]
    cases = data["no_of_cases"]
    facilities = data["no_of_facilities_total"]

    fulfillment = safe_divide(rr, rshould)
    efficiency = safe_divide(rr, rexp)
    documentation = safe_divide(rr, rdocs)
    case_eff = safe_divide(rr, cases)
    facility_yield = safe_divide(rr, facilities)

    return fulfillment, efficiency, documentation, case_eff, facility_yield

def generate_ranking():

    conn = sqlite3.connect(DB_PATH)
    df = pd.read_sql_query("SELECT * FROM records", conn)
    conn.close()

    summary = df.groupby("employee").sum().reset_index()

    employees = []

    for _, row in summary.iterrows():

        data = row.to_dict()

        f, e, d, c, fy = calculate_scores(data)

        employees.append({
            "Employee": row["employee"],
            "Fulfillment": f,
            "Efficiency": e,
            "Documentation": d,
            "CaseEff": c,
            "FacilityYield": fy
        })

    case_list = [x["CaseEff"] for x in employees]
    facility_list = [x["FacilityYield"] for x in employees]

    for emp in employees:
        norm_case = normalize(emp["CaseEff"], min(case_list), max(case_list))
        norm_fac = normalize(emp["FacilityYield"], min(facility_list), max(facility_list))

        score = (
            emp["Fulfillment"] * 0.30 +
            emp["Efficiency"] * 0.25 +
            emp["Documentation"] * 0.20 +
            norm_case * 0.15 +
            norm_fac * 0.10
        ) * 100

        emp["Score"] = round(score, 2)

        if score >= 85:
            emp["Category"] = "Excellent"
        elif score >= 70:
            emp["Category"] = "Good"
        else:
            emp["Category"] = "Needs Improvement"

    employees.sort(key=lambda x: x["Score"], reverse=True)

    for i, emp in enumerate(employees):
        emp["Rank"] = i + 1

    return employees

# =========================
# PDF GENERATION
# =========================

def generate_pdf_report(data):

    file_path = "performance_report.pdf"
    doc = SimpleDocTemplate(file_path, pagesize=A4)
    styles = getSampleStyleSheet()
    elements = []

    elements.append(Paragraph("<b>Monthly Performance Report</b>", styles["Heading1"]))
    elements.append(Spacer(1, 20))

    for emp in data:
        text = f"""
        <b>{emp['Employee']}</b><br/>
        Score: {emp['Score']}<br/>
        Rank: {emp['Rank']}<br/>
        Category: {emp['Category']}<br/><br/>
        """
        elements.append(Paragraph(text, styles["Normal"]))
        elements.append(Spacer(1, 12))

    doc.build(elements)
    return file_path

# =========================
# EMAIL AUTOMATION
# =========================

def send_email_report(data):

    sender = os.environ.get("EMAIL_USER")
    password = os.environ.get("EMAIL_PASS")
    receiver = "attorney@email.com"

    message = MIMEMultipart()
    message["From"] = sender
    message["To"] = receiver
    message["Subject"] = "Monthly Performance Report"

    body = "Performance Summary:\n\n"

    for emp in data:
        body += f"{emp['Employee']} - Score: {emp['Score']} - Rank: {emp['Rank']}\n"

    message.attach(MIMEText(body, "plain"))

    server = smtplib.SMTP("smtp.gmail.com", 587)
    server.starttls()
    server.login(sender, password)
    server.sendmail(sender, receiver, message.as_string())
    server.quit()

# =========================
# LOGIN SYSTEM
# =========================

class User(UserMixin):
    def __init__(self, id, role):
        self.id = id
        self.role = role

@login_manager.user_loader
def load_user(user_id):
    if user_id in USERS:
        return User(user_id, USERS[user_id]["role"])
    return None

@app.route("/", methods=["GET", "POST"])
def login():
    if request.method == "POST":
        username = request.form["username"]
        password = request.form["password"]

        if username in USERS and USERS[username]["password"] == password:
            login_user(User(username, USERS[username]["role"]))
            return redirect("/dashboard" if USERS[username]["role"] == "attorney" else "/upload")

    return render_template("login.html")

@app.route("/logout")
@login_required
def logout():
    logout_user()
    return redirect("/")

# =========================
# DASHBOARD
# =========================

@app.route("/dashboard")
@login_required
def dashboard():

    if current_user.role != "attorney":
        return redirect("/upload")

    ranking = generate_ranking()

    # Trend graph
    names = [x["Employee"] for x in ranking]
    scores = [x["Score"] for x in ranking]

    plt.figure()
    plt.bar(names, scores)
    plt.title("Performance Ranking")
    plt.ylabel("Score")

    img = io.BytesIO()
    plt.savefig(img, format='png')
    img.seek(0)
    graph_url = base64.b64encode(img.getvalue()).decode()

    return render_template("dashboard.html", data=ranking, graph=graph_url)

# =========================
# PDF ROUTE
# =========================

@app.route("/download_pdf")
@login_required
def download_pdf():

    ranking = generate_ranking()
    file_path = generate_pdf_report(ranking)
    return send_file(file_path, as_attachment=True)

# =========================
# EMAIL ROUTE
# =========================

@app.route("/send_email")
@login_required
def email_report():
    ranking = generate_ranking()
    send_email_report(ranking)
    return redirect("/dashboard")

# =========================
# RUN
# =========================

if __name__ == "__main__":
    app.run()