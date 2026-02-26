from flask import Flask, render_template, request, redirect, url_for
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
        total_calls INTEGER,
        connected_calls INTEGER,
        call_minutes REAL,
        total_faxes INTEGER,
        fax_minutes REAL,
        score REAL
    )
    """)

    c.execute("""
    CREATE TABLE IF NOT EXISTS cases (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        case_name TEXT,
        facility TEXT,
        created_by TEXT
    )
    """)

    c.execute("""
    CREATE TABLE IF NOT EXISTS defendants (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        case_id INTEGER,
        defendant_name TEXT,
        drafted INTEGER DEFAULT 0,
        efiled INTEGER DEFAULT 0,
        served INTEGER DEFAULT 0
    )
    """)

    conn.commit()
    conn.close()

init_db()

# ================= USERS =================

USERS = {
    "Steve": {"password": "Masterlogin3217", "role": "attorney"},
    "Samarth": {"password": "samarth1511", "role": "master"},
    "Pragati": {"password": "pragati1711", "role": "master"},
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

@app.route("/", methods=["GET", "POST"])
def login():
    if request.method == "POST":
        username = request.form["username"]
        password = request.form["password"]

        if username in USERS and USERS[username]["password"] == password:
            login_user(User(username, USERS[username]["role"]))

            # Proper redirect
            if USERS[username]["role"] in ["attorney", "master"]:
                return redirect("/attorney_dashboard")
            else:
                return redirect("/employee_dashboard")

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
    if current_user.role not in ["employee", "master"]:
        return redirect("/attorney_dashboard")
    return render_template("employee_dashboard.html")

# ================= ATTORNEY DASHBOARD =================

@app.route("/attorney_dashboard")
@login_required
def attorney_dashboard():

    if current_user.role not in ["attorney", "master"]:
        return redirect("/employee_dashboard")

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

    if current_user.role not in ["employee", "master"]:
        return redirect("/attorney_dashboard")

    file = request.files["file"]
    df = pd.read_csv(file)

    total_calls = len(df)
    connected_calls = len(df[df["Action Result"]=="Connected"]) if "Action Result" in df.columns else 0

    if "Duration" in df.columns:
        df["Duration"] = pd.to_timedelta(df["Duration"])
        call_minutes = df["Duration"].dt.total_seconds().sum()/60
    else:
        call_minutes = 0

    score = (connected_calls * 2) + (call_minutes / 10)

    save_analytics(current_user.id, total_calls, connected_calls, call_minutes, 0, 0, score)

    return redirect("/employee_dashboard")

# ================= FAX UPLOAD =================

@app.route("/upload_fax", methods=["POST"])
@login_required
def upload_fax():

    if current_user.role not in ["employee", "master"]:
        return redirect("/attorney_dashboard")

    file = request.files["file"]
    df = pd.read_csv(file)

    total_faxes = len(df[df["Direction"]=="Outgoing"]) if "Direction" in df.columns else len(df)
    fax_minutes = total_faxes * 20

    score = total_faxes * 3

    save_analytics(current_user.id, 0, 0, 0, total_faxes, fax_minutes, score)

    return redirect("/employee_dashboard")

def save_analytics(emp, calls, connected, call_min, faxes, fax_min, score):
    conn = sqlite3.connect(DB_PATH)
    conn.execute("""
    INSERT INTO analytics
    (employee,total_calls,connected_calls,call_minutes,total_faxes,fax_minutes,score)
    VALUES (?,?,?,?,?,?,?)
    """,(emp,calls,connected,call_min,faxes,fax_min,score))
    conn.commit()
    conn.close()

# ================= SUMMONS =================

@app.route("/summons")
@login_required
def summons():
    conn = sqlite3.connect(DB_PATH)
    cases = pd.read_sql_query("SELECT * FROM cases", conn)
    conn.close()
    return render_template("summons.html", cases=cases.to_dict(orient="records"))

@app.route("/create_case", methods=["POST"])
@login_required
def create_case():

    case_name = request.form["case_name"]
    facility = request.form["facility"]

    suffix = "(TT)" if facility=="Temple Terrace" else "(FM)"
    full_case_name = f"{case_name}{suffix}"

    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()

    c.execute("INSERT INTO cases (case_name,facility,created_by) VALUES (?,?,?)",
              (full_case_name, facility, current_user.id))

    conn.commit()
    conn.close()

    return redirect("/summons")

# ================= RUN =================

if __name__ == "__main__":
    app.run(debug=True)