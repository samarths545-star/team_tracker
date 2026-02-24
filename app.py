from flask import Flask, render_template, request, redirect
from flask_login import LoginManager, UserMixin, login_user, login_required, logout_user, current_user
import pandas as pd
import sqlite3
import os

app = Flask(__name__)
app.secret_key = "supersecretkey"

login_manager = LoginManager()
login_manager.init_app(app)

# =========================
# DATABASE (FREE RENDER SAFE)
# =========================

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DB_PATH = os.path.join(BASE_DIR, "database.db")

def init_db():
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute("""
        CREATE TABLE IF NOT EXISTS employee_kpi (
            employee TEXT PRIMARY KEY,
            No_of_cases INTEGER,
            No_of_facilities_total INTEGER,
            Records_expected INTEGER,
            Records_received INTEGER,
            Records_should_be_received INTEGER,
            Correspondence_absence_of_death INTEGER,
            Correspondence_facility_rejection INTEGER,
            Records_if_all_docs_available INTEGER
        )
    """)
    conn.commit()
    conn.close()

init_db()

# =========================
# USERS
# =========================

USERS = {
    "BigBossSteve": {"password": "Masterlogin3217", "role": "attorney"},
    "Samarth": {"password": "Samarth1711", "role": "employee"}
}

# =========================
# SAFE DIVISION
# =========================

def safe_divide(n, d):
    try:
        return n / d if d not in [0, None] else 0
    except:
        return 0

# =========================
# NORMALIZATION
# =========================

def normalize(value, min_v, max_v):
    if max_v == min_v:
        return 1
    return (value - min_v) / (max_v - min_v)

# =========================
# PERFORMANCE ENGINE
# =========================

def calculate_employee_performance(emp, all_emps):

    rr = emp["Records_received"]
    rexp = emp["Records_expected"]
    rshould = emp["Records_should_be_received"]
    rdocs = emp["Records_if_all_docs_available"]
    cases = emp["No_of_cases"]
    facilities = emp["No_of_facilities_total"]

    fulfillment = safe_divide(rr, rshould)
    efficiency = safe_divide(rr, rexp)
    documentation = safe_divide(rr, rdocs)
    case_eff = safe_divide(rr, cases)
    facility_yield = safe_divide(rr, facilities)

    case_list = [safe_divide(e["Records_received"], e["No_of_cases"]) for e in all_emps]
    facility_list = [safe_divide(e["Records_received"], e["No_of_facilities_total"]) for e in all_emps]

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
        "Final_Score": round(final_score, 2)
    }

def rank_employees(employee_list):

    results = []

    for emp in employee_list:
        perf = calculate_employee_performance(emp, employee_list)
        results.append({
            "Employee": emp["employee"],
            **perf
        })

    results.sort(key=lambda x: x["Final_Score"], reverse=True)

    for i, r in enumerate(results):
        r["Rank"] = i + 1

    return results

# =========================
# LOGIN
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

@app.route("/", methods=["GET","POST"])
def login():
    if request.method == "POST":
        u = request.form["username"]
        p = request.form["password"]
        if u in USERS and USERS[u]["password"] == p:
            login_user(User(u, USERS[u]["role"]))
            return redirect("/dashboard" if USERS[u]["role"]=="attorney" else "/upload")
    return render_template("login.html")

@app.route("/logout")
@login_required
def logout():
    logout_user()
    return redirect("/")

# =========================
# EMPLOYEE UPLOAD
# =========================

@app.route("/upload", methods=["GET","POST"])
@login_required
def upload():

    if current_user.role != "employee":
        return redirect("/dashboard")

    if request.method == "POST":

        file = request.files["file"]
        df = pd.read_excel(file)

        conn = sqlite3.connect(DB_PATH)
        c = conn.cursor()

        for _, row in df.iterrows():
            try:
                c.execute("""
                    INSERT OR REPLACE INTO employee_kpi
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                """, (
                    row["Employee"],
                    row.get("No_of_cases",0),
                    row.get("No_of_facilities_total",0),
                    row.get("Records_expected",0),
                    row.get("Records_received",0),
                    row.get("Records_should_be_received",0),
                    row.get("Correspondence_absence_of_death",0),
                    row.get("Correspondence_facility_rejection",0),
                    row.get("Records_if_all_docs_available",0)
                ))
            except Exception as e:
                print("Row Error:", e)

        conn.commit()
        conn.close()

    return render_template("upload.html")

# =========================
# DASHBOARD
# =========================

@app.route("/dashboard")
@login_required
def dashboard():

    if current_user.role != "attorney":
        return redirect("/upload")

    conn = sqlite3.connect(DB_PATH)
    df = pd.read_sql_query("SELECT * FROM employee_kpi", conn)
    conn.close()

    if df.empty:
        return render_template("dashboard.html", tables=[])

    employee_list = df.to_dict(orient="records")

    ranked = rank_employees(employee_list)

    return render_template("dashboard.html", tables=ranked)

# =========================
# RUN
# =========================