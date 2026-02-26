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
        cases INTEGER DEFAULT 0,
        facilities_total INTEGER DEFAULT 0,
        records_received INTEGER DEFAULT 0,
        expected_records INTEGER DEFAULT 0,
        records_if_all_docs INTEGER DEFAULT 0,
        correspondence_received INTEGER DEFAULT 0,
        summons_efile INTEGER DEFAULT 0,
        summons_served INTEGER DEFAULT 0
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

# ================= SAFE FILE READER =================

def safe_read(file):
    filename = file.filename.lower()
    try:
        if filename.endswith(".csv"):
            return pd.read_csv(file)
        else:
            return pd.read_excel(file, engine="openpyxl")
    except Exception as e:
        print("FILE READ ERROR:", e)
        return pd.DataFrame()

# ================= SAFE INSERT =================

def insert_record(employee, **kwargs):
    conn = sqlite3.connect(DB_PATH)
    today = datetime.now().strftime("%Y-%m-%d")

    columns = ", ".join(["employee","date"] + list(kwargs.keys()))
    placeholders = ", ".join(["?"]*(2+len(kwargs)))
    values = [employee,today] + list(kwargs.values())

    conn.execute(f"INSERT INTO analytics ({columns}) VALUES ({placeholders})", values)
    conn.commit()
    conn.close()

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

    if df.empty:
        return render_template("master_dashboard.html",
                               employees=EMPLOYEES,
                               data=[],
                               user=current_user.display)

    df = df.groupby("employee").sum(numeric_only=True).reset_index()

    # ================= KPIs =================

    df["call_efficiency"] = df["connected_calls"] / df["total_calls"].replace(0,1)
    df["communication_time"] = df["call_minutes"] + df["fax_minutes"]
    df["record_fulfillment"] = df["records_received"] / df["expected_records"].replace(0,1)
    df["doc_completion"] = df["records_received"] / df["records_if_all_docs"].replace(0,1)
    df["summons_effectiveness"] = df["summons_served"] / df["summons_efile"].replace(0,1)

    df["score"] = (
        df["call_efficiency"] * 25 +
        df["communication_time"] * 0.1 +
        df["record_fulfillment"] * 25 +
        df["doc_completion"] * 15 +
        df["summons_effectiveness"] * 20
    )

    df = df.sort_values("score", ascending=False)
    df["Rank"] = range(1, len(df)+1)

    return render_template("master_dashboard.html",
                           employees=EMPLOYEES,
                           data=df.to_dict(orient="records"),
                           user=current_user.display)

# ================= UPLOAD CALL =================

@app.route("/upload_call", methods=["POST"])
@login_required
def upload_call():

    emp = request.form["employee"]
    df = safe_read(request.files["file"])

    if df.empty:
        return redirect("/dashboard")

    total_calls = len(df)
    connected = len(df[df.get("Action Result","")=="Connected"]) if "Action Result" in df.columns else 0

    minutes = 0
    if "Duration" in df.columns:
        df["Duration"] = pd.to_timedelta(df["Duration"], errors="coerce")
        minutes = df["Duration"].dt.total_seconds().sum()/60

    insert_record(emp,
                  total_calls=total_calls,
                  connected_calls=connected,
                  call_minutes=minutes)

    return redirect("/dashboard")

# ================= UPLOAD FAX =================

@app.route("/upload_fax", methods=["POST"])
@login_required
def upload_fax():

    emp = request.form["employee"]
    df = safe_read(request.files["file"])

    if df.empty:
        return redirect("/dashboard")

    total = len(df)
    minutes = total * 20

    insert_record(emp,total_faxes=total,fax_minutes=minutes)
    return redirect("/dashboard")

# ================= UPLOAD SUMMONS =================

@app.route("/upload_summons", methods=["POST"])
@login_required
def upload_summons():

    emp = request.form["employee"]
    df = safe_read(request.files["file"])

    if df.empty:
        return redirect("/dashboard")

    efile = df["Date of e-Filing"].notna().sum() if "Date of e-Filing" in df.columns else 0
    served = df["Summons Served by Process Server"].notna().sum() if "Summons Served by Process Server" in df.columns else 0

    insert_record(emp,summons_efile=efile,summons_served=served)
    return redirect("/dashboard")

# ================= UPLOAD CONSOLIDATED =================

@app.route("/upload_consolidated", methods=["POST"])
@login_required
def upload_consolidated():

    try:
        df = pd.read_excel(request.files["file"], header=[0,1])
    except Exception as e:
        print("Excel read error:", e)
        return redirect("/dashboard")

    df.columns = [' '.join([str(i) for i in col if str(i) != 'nan']).strip() for col in df.columns]
    df = df.fillna("")

    for _, row in df.iterrows():

        if "Total" not in str(row):
            continue

        emp = row.get("Name", "")
        if not emp:
            continue

        try:
            cases = int(row.filter(like="No. of cases").values[0])
        except:
            cases = 0

        try:
            facilities = int(row.filter(like="Total").values[0])
        except:
            facilities = 0

        try:
            records = int(row.filter(like="No. of Records Received").values[0])
        except:
            records = 0

        try:
            expected = int(row.filter(like="Expected").values[0])
        except:
            expected = 0

        try:
            records_if_all = int(row.filter(like="No. of Records would have received").values[0])
        except:
            records_if_all = 0

        try:
            corr_cols = row.filter(like="Correspondence")
            correspondence = sum(pd.to_numeric(corr_cols, errors="coerce").fillna(0))
        except:
            correspondence = 0

        insert_record(
            emp,
            cases=cases,
            facilities_total=facilities,
            records_received=records,
            expected_records=expected,
            records_if_all_docs=records_if_all,
            correspondence_received=correspondence
        )

    return redirect("/dashboard")

if __name__ == "__main__":
    app.run(debug=True)