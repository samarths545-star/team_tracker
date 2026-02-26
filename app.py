from flask import Flask, render_template, request, redirect
from flask_login import LoginManager, UserMixin, login_user, login_required, logout_user, current_user
import pandas as pd
import sqlite3
import os

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
        total_calls INTEGER DEFAULT 0,
        connected_calls INTEGER DEFAULT 0,
        call_minutes REAL DEFAULT 0,
        total_faxes INTEGER DEFAULT 0,
        fax_minutes REAL DEFAULT 0,
        records_received INTEGER DEFAULT 0,
        cases INTEGER DEFAULT 0,
        facilities INTEGER DEFAULT 0,
        summons_efile_count INTEGER DEFAULT 0,
        summons_served_count INTEGER DEFAULT 0,
        score REAL DEFAULT 0
    )
    """)

    conn.commit()
    conn.close()

init_db()

# ================= USERS =================

USERS = {
    "Samarth": {"password": "samarth1511"},
    "Pragati": {"password": "pragati1711"}
}

EMPLOYEES = ["Kavish", "Chirag", "Sahil", "Tushar"]

class User(UserMixin):
    def __init__(self, id):
        self.id = id

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
    conn = sqlite3.connect(DB_PATH)
    df = pd.read_sql_query("SELECT * FROM analytics", conn)
    conn.close()

    if not df.empty:
        df = df.groupby("employee").sum(numeric_only=True).reset_index()

        df["score"] = (
            df["connected_calls"] * 2 +
            df["call_minutes"]/10 +
            df["total_faxes"] * 3 +
            df["records_received"] * 2 +
            df["summons_efile_count"] * 2 +
            df["summons_served_count"] * 3
        )

        df = df.sort_values("score", ascending=False)
        df["Rank"] = range(1, len(df)+1)
        data = df.to_dict(orient="records")
    else:
        data = []

    return render_template("master_dashboard.html",
                           employees=EMPLOYEES,
                           data=data)

# ================= CONSOLIDATED =================

@app.route("/upload_consolidated", methods=["POST"])
@login_required
def upload_consolidated():

    file = request.files["file"]
    df = pd.read_excel(file)

    conn = sqlite3.connect(DB_PATH)

    for _, row in df.iterrows():
        employee = row["Employee"]
        records = row.get("No. of Records Received (MR & MB)",0)
        cases = row.get("No. of cases",0)
        facilities = row.get("No. of Facilities",0)

        conn.execute("""
        INSERT INTO analytics (employee, records_received, cases, facilities)
        VALUES (?,?,?,?)
        """,(employee,records,cases,facilities))

    conn.commit()
    conn.close()

    return redirect("/dashboard")

# ================= CALL =================

@app.route("/upload_call", methods=["POST"])
@login_required
def upload_call():

    employee = request.form["employee"]
    file = request.files["file"]
    df = pd.read_csv(file)

    total_calls = len(df)
    connected_calls = len(df[df["Action Result"]=="Connected"]) if "Action Result" in df.columns else 0

    df["Duration"] = pd.to_timedelta(df["Duration"])
    call_minutes = df["Duration"].dt.total_seconds().sum()/60

    conn = sqlite3.connect(DB_PATH)
    conn.execute("""
    INSERT INTO analytics (employee,total_calls,connected_calls,call_minutes)
    VALUES (?,?,?,?)
    """,(employee,total_calls,connected_calls,call_minutes))
    conn.commit()
    conn.close()

    return redirect("/dashboard")

# ================= FAX =================

@app.route("/upload_fax", methods=["POST"])
@login_required
def upload_fax():

    employee = request.form["employee"]
    file = request.files["file"]
    df = pd.read_csv(file)

    total_faxes = len(df)
    fax_minutes = total_faxes * 20

    conn = sqlite3.connect(DB_PATH)
    conn.execute("""
    INSERT INTO analytics (employee,total_faxes,fax_minutes)
    VALUES (?,?,?)
    """,(employee,total_faxes,fax_minutes))
    conn.commit()
    conn.close()

    return redirect("/dashboard")

# ================= SUMMONS =================

@app.route("/upload_summons", methods=["POST"])
@login_required
def upload_summons():

    employee = request.form["employee"]
    file = request.files["file"]
    df = pd.read_excel(file)

    summons_efile_count = df["Date of e-Filing"].notna().sum()
    summons_served_count = df["Summons Served by Process Server"].notna().sum()

    conn = sqlite3.connect(DB_PATH)
    conn.execute("""
    INSERT INTO analytics (employee,summons_efile_count,summons_served_count)
    VALUES (?,?,?)
    """,(employee,summons_efile_count,summons_served_count))
    conn.commit()
    conn.close()

    return redirect("/dashboard")

if __name__ == "__main__":
    app.run(debug=True)