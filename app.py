from flask import Flask, render_template, request, redirect, jsonify
from flask_login import LoginManager, UserMixin, login_user, login_required, logout_user, current_user
import pandas as pd
import sqlite3
import os
import json
from datetime import datetime

app = Flask(__name__)
app.secret_key = "supersecretkey"

login_manager = LoginManager()
login_manager.init_app(app)

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DB_PATH = os.path.join(BASE_DIR, "database.db")

# ================= DATABASE INIT =================

def init_db():
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()

    # Performance history
    c.execute("""
        CREATE TABLE IF NOT EXISTS performance_history (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            employee TEXT,
            date TEXT,
            No_of_cases INTEGER,
            No_of_facilities_total INTEGER,
            Records_expected INTEGER,
            Records_received INTEGER,
            Records_should_be_received INTEGER,
            Records_if_all_docs_available INTEGER
        )
    """)

    # Cases
    c.execute("""
        CREATE TABLE IF NOT EXISTS cases (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            case_name TEXT,
            facility TEXT
        )
    """)

    # Defendants
    c.execute("""
        CREATE TABLE IF NOT EXISTS defendants (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            case_id INTEGER,
            defendant_name TEXT,
            served INTEGER DEFAULT 0
        )
    """)

    conn.commit()
    conn.close()

init_db()

# ================= USERS =================

USERS = {
    "BigBossSteve": {"password": "Masterlogin3217", "role": "attorney"},
    "Samarth": {"password": "Samarth1711", "role": "employee"}
}

class User(UserMixin):
    def __init__(self, id, role):
        self.id = id
        self.role = role

@login_manager.user_loader
def load_user(user_id):
    if user_id in USERS:
        return User(user_id, USERS[user_id]["role"])
    return None

# ================= HELPERS =================

def safe_divide(n, d):
    try:
        return float(n) / float(d) if d and float(d) != 0 else 0.0
    except:
        return 0.0

def normalize(value, min_v, max_v):
    if max_v == min_v:
        return 1
    return (value - min_v) / (max_v - min_v)

def get_summons_rate():
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute("SELECT COUNT(*) FROM defendants")
    total = c.fetchone()[0]
    c.execute("SELECT COUNT(*) FROM defendants WHERE served=1")
    served = c.fetchone()[0]
    conn.close()
    return safe_divide(served, total)

# ================= PERFORMANCE =================

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

    base_score = (
        fulfillment * 0.30 +
        efficiency * 0.25 +
        documentation * 0.20 +
        norm_case * 0.15 +
        norm_facility * 0.10
    ) * 100

    summons_bonus = get_summons_rate() * 10  # 10% impact

    final_score = base_score + summons_bonus

    return {
        "Employee": emp["employee"],
        "Final_Score": round(final_score,2),
        "Summons_Rate": round(get_summons_rate()*100,1)
    }

def rank_employees(employee_list):
    results = []
    for emp in employee_list:
        results.append(calculate_employee_performance(emp, employee_list))
    results.sort(key=lambda x: x["Final_Score"], reverse=True)
    for i, r in enumerate(results):
        r["Rank"] = i + 1
    return results

# ================= LOGIN =================

@app.route("/", methods=["GET","POST"])
def login():
    if request.method == "POST":
        u = request.form["username"]
        p = request.form["password"]
        if u in USERS and USERS[u]["password"] == p:
            login_user(User(u, USERS[u]["role"]))
            return redirect("/dashboard")
    return render_template("login.html")

@app.route("/logout")
@login_required
def logout():
    logout_user()
    return redirect("/")

# ================= DASHBOARD =================

@app.route("/dashboard")
@login_required
def dashboard():

    conn = sqlite3.connect(DB_PATH)
    df = pd.read_sql_query("SELECT * FROM performance_history", conn)
    conn.close()

    if df.empty:
        return render_template("dashboard.html", tables=[])

    grouped = df.groupby("employee").sum(numeric_only=True).reset_index()
    ranked = rank_employees(grouped.to_dict(orient="records"))

    return render_template("dashboard.html",
                           tables=ranked,
                           chart_data=json.dumps(ranked))

# ================= CREATE CASE =================

@app.route("/create_case", methods=["POST"])
@login_required
def create_case():

    case_name = request.form["case_name"]
    facility = request.form["facility"]

    suffix = "(TT)" if facility=="Temple Terrace" else "(FM)"
    full_case_name = f"{case_name}{suffix}"

    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()

    c.execute("INSERT INTO cases (case_name, facility) VALUES (?,?)",
              (full_case_name, facility))
    case_id = c.lastrowid

    if facility == "Fort Myers":
        defendants = """AMERICAN CONTRACT SYSTEMS, INC., a Foreign Corporation;
O&M HALYARD, INC., a Foreign Corporation;
ACCENDRA HEALTH, INC. F/K/A OWENS & MINOR, INC., a Foreign Corporation;
CROCI REAL ESTATE, LLC, a Florida Limited Liability Company;
LEESAR, INC., a Florida Corporation;
PHILIP FLEISCHHACKER;
ROBERT COOK;
PENNY WALLS;"""
    else:
        defendants = """AMERICAN CONTRACT SYSTEMS, INC., a Foreign Corporation;
O&M HALYARD, INC., a Foreign Corporation;
ACCENDRA HEALTH, INC. F/K/A OWENS & MINOR, INC., a Foreign Corporation;
BAYCARE HEALTH SYSTEM, INC., a Florida Non-Profit Corporation;
BAYCARE INTEGRATED SERVICE CENTER, LLC, a Florida Limited Liability Company;
PHILIP FLEISCHHACKER;
SREAN LY;"""

    for d in defendants.split(";"):
        name = d.strip()
        if name:
            c.execute("INSERT INTO defendants (case_id, defendant_name) VALUES (?,?)",
                      (case_id, name))

    conn.commit()
    conn.close()

    return redirect("/summons")

# ================= SUMMONS =================

@app.route("/summons")
@login_required
def summons():

    conn = sqlite3.connect(DB_PATH)
    cases = pd.read_sql_query("SELECT * FROM cases", conn)
    defendants = pd.read_sql_query("SELECT * FROM defendants", conn)
    conn.close()

    return render_template("summons.html",
                           cases=cases.to_dict(orient="records"),
                           defendants=defendants.to_dict(orient="records"))

@app.route("/toggle_served/<int:def_id>")
@login_required
def toggle_served(def_id):

    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute("UPDATE defendants SET served = CASE WHEN served=1 THEN 0 ELSE 1 END WHERE id=?",(def_id,))
    conn.commit()
    conn.close()

    return redirect("/summons")

if __name__ == "__main__":
    app.run(debug=True)