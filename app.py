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
login_manager.login_view = "/"

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
        date TEXT,
        total_calls INTEGER DEFAULT 0,
        connected_calls INTEGER DEFAULT 0,
        call_minutes REAL DEFAULT 0,
        total_faxes INTEGER DEFAULT 0,
        fax_minutes REAL DEFAULT 0,
        records_received INTEGER DEFAULT 0,
        records_requested INTEGER DEFAULT 0,
        correspondence_received INTEGER DEFAULT 0,
        cases INTEGER DEFAULT 0,
        facilities INTEGER DEFAULT 0,
        summons_efile_count INTEGER DEFAULT 0,
        summons_served_count INTEGER DEFAULT 0
    )
    """)

    conn.commit()
    conn.close()

init_db()

# ================= USERS =================

USERS = {
    "BigBossSteve": {"password": "masterlogin3217", "display": "Steve"},
    "Samarth": {"password": "samarth1511", "display": "Samarth"},
    "Pragati": {"password": "pragati1711", "display": "Pragati"}
}

EMPLOYEES = ["Kavish", "Chirag", "Sahil", "Tushar"]

class User(UserMixin):
    def __init__(self, id):
        self.id = id
        self.display = USERS[id]["display"]

@login_manager.user_loader
def load_user(user_id):
    if user_id in USERS:
        return User(user_id)
    return None

# ================= LOGIN =================

@app.route("/", methods=["GET","POST"])
def login():
    if request.method == "POST":
        u = request.form["username"]
        p = request.form["password"]
        if u in USERS and USERS[u]["password"] == p:
            login_user(User(u))
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

    start_date = request.args.get("start_date")
    end_date = request.args.get("end_date")

    conn = sqlite3.connect(DB_PATH)

    query = "SELECT * FROM analytics"
    params = []

    if start_date and end_date:
        query += " WHERE date BETWEEN ? AND ?"
        params = [start_date, end_date]

    df = pd.read_sql_query(query, conn, params=params)
    conn.close()

    if df.empty:
        return render_template("master_dashboard.html",
                               employees=EMPLOYEES,
                               data=[],
                               user=current_user.display)

    df = df.groupby("employee").sum(numeric_only=True).reset_index()

    # Performance Score Formula
    df["score"] = (
        df["connected_calls"] * 2 +
        df["call_minutes"]/10 +
        df["total_faxes"] * 3 +
        df["records_received"] * 2 +
        df["correspondence_received"] * 1.5 +
        df["summons_efile_count"] * 2 +
        df["summons_served_count"] * 3
    )

    df = df.sort_values("score", ascending=False)
    df["Rank"] = range(1, len(df)+1)

    data = df.to_dict(orient="records")

    return render_template("master_dashboard.html",
                           employees=EMPLOYEES,
                           data=data,
                           user=current_user.display)

# ================= SAFE INSERT =================

def insert_data(employee, **kwargs):
    conn = sqlite3.connect(DB_PATH)
    today = datetime.now().strftime("%Y-%m-%d")

    columns = ", ".join(["employee", "date"] + list(kwargs.keys()))
    placeholders = ", ".join(["?"] * (2 + len(kwargs)))

    values = [employee, today] + list(kwargs.values())

    conn.execute(f"INSERT INTO analytics ({columns}) VALUES ({placeholders})", values)
    conn.commit()
    conn.close()

# ================= UPLOAD CALL =================

@app.route("/upload_call", methods=["POST"])
@login_required
def upload_call():

    employee = request.form["employee"]
    file = request.files["file"]

    df = pd.read_csv(file)

    total_calls = len(df)
    connected_calls = len(df[df["Action Result"]=="Connected"]) if "Action Result" in df.columns else 0

    call_minutes = 0
    if "Duration" in df.columns:
        df["Duration"] = pd.to_timedelta(df["Duration"], errors="coerce")
        call_minutes = df["Duration"].dt.total_seconds().sum()/60

    insert_data(employee,
                total_calls=total_calls,
                connected_calls=connected_calls,
                call_minutes=call_minutes)

    return redirect("/dashboard")

# ================= UPLOAD FAX =================

@app.route("/upload_fax", methods=["POST"])
@login_required
def upload_fax():

    employee = request.form["employee"]
    file = request.files["file"]

    df = pd.read_csv(file)

    total_faxes = len(df)
    fax_minutes = total_faxes * 20

    insert_data(employee,
                total_faxes=total_faxes,
                fax_minutes=fax_minutes)

    return redirect("/dashboard")

# ================= UPLOAD SUMMONS =================

@app.route("/upload_summons", methods=["POST"])
@login_required
def upload_summons():

    employee = request.form["employee"]
    file = request.files["file"]

    df = pd.read_excel(file)

    efile_count = df["Date of e-Filing"].notna().sum() if "Date of e-Filing" in df.columns else 0
    served_count = df["Summons Served by Process Server"].notna().sum() if "Summons Served by Process Server" in df.columns else 0

    insert_data(employee,
                summons_efile_count=efile_count,
                summons_served_count=served_count)

    return redirect("/dashboard")

# ================= UPLOAD CONSOLIDATED =================

@app.route("/upload_consolidated", methods=["POST"])
@login_required
def upload_consolidated():

    file = request.files["file"]
    df = pd.read_excel(file)

    for _, row in df.iterrows():

        employee = row.get("Employee")
        if not employee:
            continue

        insert_data(
            employee,
            records_received=row.get("No. of Records Received (MR & MB)",0),
            records_requested=row.get("Total No. of Records Requested",0),
            correspondence_received=row.get("No. of Correspondence Received",0),
            cases=row.get("No. of cases",0),
            facilities=row.get("No. of Facilities",0)
        )

    return redirect("/dashboard")

if __name__ == "__main__":
    app.run(debug=True)