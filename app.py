from flask import Flask, render_template, request, redirect
from flask_login import LoginManager, UserMixin, login_user, login_required, logout_user, current_user
import pandas as pd
import sqlite3
import os
from datetime import datetime

app = Flask(__name__)
app.secret_key = "supersecretkey"

login_manager = LoginManager()
login_manager.init_app(app)

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DB_PATH = os.path.join(BASE_DIR, "database.db")

# ================= DATABASE =================

def init_db():
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()

    c.execute("""
    CREATE TABLE IF NOT EXISTS analytics (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        employee TEXT,
        total_calls INTEGER,
        connected_calls INTEGER,
        call_minutes REAL,
        total_faxes INTEGER,
        fax_minutes REAL,
        records_received INTEGER,
        correspondence_received INTEGER,
        cases INTEGER,
        facilities INTEGER,
        score REAL
    )
    """)

    conn.commit()
    conn.close()

init_db()

# ================= USERS =================

USERS = {
    "BigBossSteve": {"password": "Masterlogin3217", "role": "attorney"},
    "Kavish": {"password": "1234", "role": "employee"},
    "Chirag": {"password": "1234", "role": "employee"},
    "Sahil": {"password": "1234", "role": "employee"},
    "Tushar": {"password": "1234", "role": "employee"}
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

# ================= LOGIN =================

@app.route("/", methods=["GET","POST"])
def login():
    if request.method == "POST":
        u = request.form["username"]
        p = request.form["password"]
        if u in USERS and USERS[u]["password"] == p:
            login_user(User(u, USERS[u]["role"]))
            return redirect("/attorney_dashboard" if USERS[u]["role"]=="attorney" else "/employee_dashboard")
    return render_template("login.html")

@app.route("/logout")
@login_required
def logout():
    logout_user()
    return redirect("/")

# ================= EMPLOYEE DASHBOARD =================

@app.route("/employee_dashboard")
@login_required
def employee_dashboard():
    if current_user.role != "employee":
        return redirect("/attorney_dashboard")
    return render_template("employee_dashboard.html")

# ================= ATTORNEY DASHBOARD =================

@app.route("/attorney_dashboard")
@login_required
def attorney_dashboard():

    conn = sqlite3.connect(DB_PATH)
    df = pd.read_sql_query("SELECT * FROM analytics", conn)
    conn.close()

    if df.empty:
        return render_template("attorney_dashboard.html", data=[])

    df = df.sort_values("score", ascending=False)
    df["Rank"] = range(1, len(df)+1)

    return render_template("attorney_dashboard.html",
                           data=df.to_dict(orient="records"))

# ================= CALL UPLOAD =================

@app.route("/upload_call", methods=["POST"])
@login_required
def upload_call():

    file = request.files["file"]
    df = pd.read_csv(file)

    total_calls = len(df)
    connected_calls = len(df[df["Action Result"]=="Connected"]) if "Action Result" in df.columns else 0

    df["Duration"] = pd.to_timedelta(df["Duration"])
    call_minutes = df["Duration"].dt.total_seconds().sum()/60

    save_temp("call", total_calls, connected_calls, call_minutes)

    return redirect("/employee_dashboard")

# ================= FAX UPLOAD =================

@app.route("/upload_fax", methods=["POST"])
@login_required
def upload_fax():

    file = request.files["file"]
    df = pd.read_csv(file)

    total_faxes = len(df[df["Direction"]=="Outgoing"])
    fax_minutes = total_faxes * 20  # 20 minute rule

    save_temp("fax", total_faxes, 0, fax_minutes)

    return redirect("/employee_dashboard")

# ================= CONSOLIDATED UPLOAD =================

@app.route("/upload_consolidated", methods=["POST"])
@login_required
def upload_consolidated():

    file = request.files["file"]
    df = pd.read_excel(file)

    records_received = df["No. of Records Received (MR & MB)"].sum()
    correspondence_received = df["No. of Correspondence Received "].sum()
    cases = df["No. of cases"].sum()
    facilities = df["No. of Facilities"].sum()

    calculate_final_score(records_received, correspondence_received, cases, facilities)

    return redirect("/employee_dashboard")

# ================= PERFORMANCE LOGIC =================

temp_storage = {}

def save_temp(type_name, val1, val2, val3):
    if current_user.id not in temp_storage:
        temp_storage[current_user.id] = {}

    if type_name=="call":
        temp_storage[current_user.id]["total_calls"]=val1
        temp_storage[current_user.id]["connected_calls"]=val2
        temp_storage[current_user.id]["call_minutes"]=val3
    elif type_name=="fax":
        temp_storage[current_user.id]["total_faxes"]=val1
        temp_storage[current_user.id]["fax_minutes"]=val3

def calculate_final_score(records_received, correspondence_received, cases, facilities):

    data = temp_storage.get(current_user.id, {})

    total_calls = data.get("total_calls",0)
    connected_calls = data.get("connected_calls",0)
    call_minutes = data.get("call_minutes",0)
    total_faxes = data.get("total_faxes",0)
    fax_minutes = data.get("fax_minutes",0)

    connection_rate = connected_calls/total_calls if total_calls else 0
    productivity = records_received/(cases if cases else 1)

    score = (
        connection_rate*20 +
        (call_minutes/60)*10 +
        (total_faxes*2) +
        (records_received*3) +
        (correspondence_received*2) +
        productivity*10
    )

    conn = sqlite3.connect(DB_PATH)
    conn.execute("""
    INSERT INTO analytics
    (employee,total_calls,connected_calls,call_minutes,total_faxes,fax_minutes,
     records_received,correspondence_received,cases,facilities,score)
    VALUES (?,?,?,?,?,?,?,?,?,?,?)
    """,(current_user.id,total_calls,connected_calls,call_minutes,
         total_faxes,fax_minutes,records_received,correspondence_received,
         cases,facilities,score))
    conn.commit()
    conn.close()