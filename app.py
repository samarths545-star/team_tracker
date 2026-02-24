from flask import Flask, render_template, request, redirect
from flask_login import LoginManager, UserMixin, login_user, login_required, logout_user, current_user
import pandas as pd
import sqlite3
from datetime import datetime, timedelta
import os
import re

app = Flask(__name__)
app.secret_key = "supersecretkey"

login_manager = LoginManager()
login_manager.init_app(app)

# =========================================================
# DATABASE (Render Persistent Disk)
# =========================================================

DATA_DIR = "/data"

if not os.path.exists(DATA_DIR):
    os.makedirs(DATA_DIR)

DB_PATH = os.path.join(DATA_DIR, "database.db")

# =========================================================
# USERS
# =========================================================

USERS = {
    "BigBossSteve": {"password": "Masterlogin3217", "role": "attorney"},
    "Samarth": {"password": "Samarth1711", "role": "employee"}
}

EMPLOYEES = ["Kavish", "Chirag", "Sahil", "Tushar"]

# =========================================================
# INIT DATABASE
# =========================================================

def init_db():
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute('''
        CREATE TABLE IF NOT EXISTS records (
            employee TEXT,
            date TEXT,
            total_calls INTEGER,
            total_minutes REAL,
            total_faxes INTEGER,
            fax_minutes REAL,
            score REAL,
            PRIMARY KEY (employee, date)
        )
    ''')
    conn.commit()
    conn.close()

init_db()

# =========================================================
# SAFE DIVISION
# =========================================================

def safe_divide(n, d):
    if d == 0 or d is None:
        return 0
    return n / d

# =========================================================
# NORMALIZATION
# =========================================================

def normalize(value, min_v, max_v):
    if max_v == min_v:
        return 1
    return (value - min_v) / (max_v - min_v)

# =========================================================
# PERFORMANCE ENGINE
# =========================================================

def calculate_employee_performance(emp, all_emps):

    rr = emp.get("Records_received", 0)
    rexp = emp.get("Records_expected", 0)
    rshould = emp.get("Records_should_be_received", 0)
    rdocs = emp.get("Records_if_all_docs_available", 0)
    cases = emp.get("No_of_cases", 0)
    facilities = emp.get("No_of_facilities_total", 0)

    # Raw KPIs
    fulfillment = safe_divide(rr, rshould)
    efficiency = safe_divide(rr, rexp)
    documentation = safe_divide(rr, rdocs)
    case_eff = safe_divide(rr, cases)
    facility_yield = safe_divide(rr, facilities)

    # Normalization
    case_list = [safe_divide(e.get("Records_received", 0), e.get("No_of_cases", 0)) for e in all_emps]
    facility_list = [safe_divide(e.get("Records_received", 0), e.get("No_of_facilities_total", 0)) for e in all_emps]

    norm_case = normalize(case_eff, min(case_list), max(case_list))
    norm_facility = normalize(facility_yield, min(facility_list), max(facility_list))

    final_score = (
        fulfillment * 0.30 +
        efficiency * 0.25 +
        documentation * 0.20 +
        norm_case * 0.15 +
        norm_facility * 0.10
    ) * 100

    return {
        "Record_Fulfillment_Rate": round(fulfillment, 4),
        "Efficiency_Rate": round(efficiency, 4),
        "Documentation_Completion_Rate": round(documentation, 4),
        "Case_Handling_Efficiency": round(case_eff, 4),
        "Facility_Yield_Rate": round(facility_yield, 4),
        "Normalized_Case": round(norm_case, 4),
        "Normalized_Facility": round(norm_facility, 4),
        "Final_Score": round(final_score, 2)
    }

def rank_employees(employee_data):

    results = []

    for emp in employee_data:
        performance = calculate_employee_performance(emp, employee_data)
        results.append({
            "Employee": emp.get("Employee"),
            **performance
        })

    results.sort(key=lambda x: x["Final_Score"], reverse=True)

    for i, emp in enumerate(results):
        emp["Rank"] = i + 1

    return results

# =========================================================
# LOGIN SYSTEM
# =========================================================

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
            return redirect("/dashboard" if USERS[username]["role"] == "attorney" else "/upload_page")

    return render_template("login.html")

@app.route("/logout")
@login_required
def logout():
    logout_user()
    return redirect("/")

# =========================================================
# EMPLOYEE UPLOAD
# =========================================================

@app.route("/upload_page")
@login_required
def upload_page():
    if current_user.role != "employee":
        return redirect("/dashboard")
    return render_template("upload.html", employees=EMPLOYEES)

@app.route("/upload", methods=["POST"])
@login_required
def upload():

    selected_employee = request.form.get("employee")
    call_file = request.files.get("call_csv")
    fax_file = request.files.get("fax_csv")

    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()

    try:
        calls = pd.read_csv(call_file)
        calls = calls[calls["Action Result"] == "Call connected"]
        calls["Duration"] = pd.to_timedelta(calls["Duration"])
        calls["minutes"] = calls["Duration"].dt.total_seconds() / 60

        for date_value in calls["Date"].unique():
            real_date = re.search(r'\d{2}/\d{2}/\d{4}', date_value).group()
            formatted_date = datetime.strptime(real_date, "%m/%d/%Y").strftime("%Y-%m-%d")

            day_calls = calls[calls["Date"] == date_value]
            total_calls = len(day_calls)
            total_minutes = day_calls["minutes"].sum()

            c.execute("""
                INSERT OR REPLACE INTO records
                (employee, date, total_calls, total_minutes, total_faxes, fax_minutes, score)
                VALUES (?, ?, ?, ?, 0, 0, 0)
            """, (selected_employee, formatted_date, total_calls, total_minutes))

    except Exception as e:
        print("Upload Error:", e)

    conn.commit()
    conn.close()

    return redirect("/upload_page")

# =========================================================
# DASHBOARD
# =========================================================

@app.route("/dashboard")
@login_required
def dashboard():

    conn = sqlite3.connect(DB_PATH)
    df = pd.read_sql_query("SELECT * FROM records", conn)
    conn.close()

    if df.empty:
        return render_template("dashboard.html", tables=[])

    summary = df.groupby("employee").agg({
        "total_calls": "sum",
        "total_minutes": "sum",
        "total_faxes": "sum",
        "fax_minutes": "sum"
    }).reset_index()

    employee_data = []

    for _, row in summary.iterrows():
        employee_data.append({
            "Employee": row["employee"],
            "No_of_cases": row["total_calls"],  # example mapping
            "No_of_facilities_total": row["total_calls"],
            "Records_expected": row["total_calls"],
            "Records_received": row["total_faxes"],
            "Records_should_be_received": row["total_calls"],
            "Records_if_all_docs_available": row["total_calls"]
        })

    ranked = rank_employees(employee_data)

    return render_template("dashboard.html", tables=ranked)

# =========================================================
# RUN
# =========================================================

if __name__ == "__main__":
    app.run()