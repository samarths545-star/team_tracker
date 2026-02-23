from flask import Flask, render_template, request, redirect
from flask_login import LoginManager, UserMixin, login_user, login_required, logout_user, current_user
import pandas as pd
import sqlite3
from datetime import datetime, timedelta
import re
import os

app = Flask(__name__)
app.secret_key = "supersecretkey"

login_manager = LoginManager()
login_manager.init_app(app)

# Persistent DB (Render compatible)
DB_PATH = os.environ.get("DB_PATH", "/data/database.db")

USERS = {
    "BigBossSteve": {"password": "Masterlogin3217", "role": "attorney"},
    "Samarth": {"password": "Samarth1711", "role": "employee"}
}

EMPLOYEES = ["Kavish", "Chirag", "Sahil", "Tushar"]

# ---------------- DATABASE ----------------
def init_db():
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute('''CREATE TABLE IF NOT EXISTS records (
                    employee TEXT,
                    date TEXT,
                    total_calls INTEGER,
                    total_minutes REAL,
                    total_faxes INTEGER,
                    fax_minutes REAL,
                    score REAL,
                    PRIMARY KEY (employee, date)
                )''')
    conn.commit()
    conn.close()

init_db()

# ---------------- LOGIN ----------------
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
            if USERS[username]["role"] == "employee":
                return redirect("/upload_page")
            else:
                return redirect("/dashboard")

    return render_template("login.html")

@app.route("/logout")
@login_required
def logout():
    logout_user()
    return redirect("/")

# ---------------- EMPLOYEE PAGE ----------------
@app.route("/upload_page")
@login_required
def upload_page():
    if current_user.role != "employee":
        return redirect("/dashboard")
    return render_template("upload.html", employees=EMPLOYEES)

# ---------------- UPLOAD LOGIC ----------------
@app.route("/upload", methods=["POST"])
@login_required
def upload():

    if current_user.role != "employee":
        return redirect("/dashboard")

    selected_employee = request.form.get("employee")
    call_file = request.files.get("call_csv")
    fax_file = request.files.get("fax_csv")

    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()

    # CALL CSV
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
        print("Call Error:", e)

    # FAX CSV
    try:
        faxes = pd.read_csv(fax_file)

        for date_value in faxes["Date"].unique():
            real_date = re.search(r'\d{2}/\d{2}/\d{4}', date_value).group()
            formatted_date = datetime.strptime(real_date, "%m/%d/%Y").strftime("%Y-%m-%d")

            day_faxes = faxes[faxes["Date"] == date_value]
            total_faxes = len(day_faxes)
            fax_minutes = total_faxes * 20
            score = fax_minutes

            c.execute("""
                UPDATE records
                SET total_faxes=?, fax_minutes=?, score=?
                WHERE employee=? AND date=?
            """, (total_faxes, fax_minutes, score, selected_employee, formatted_date))

    except Exception as e:
        print("Fax Error:", e)

    conn.commit()
    conn.close()

    return redirect("/upload_page")

# ---------------- ATTORNEY DASHBOARD ----------------
@app.route("/dashboard")
@login_required
def dashboard():

    if current_user.role != "attorney":
        return redirect("/upload_page")

    period = request.args.get("period")
    selected_date = request.args.get("date")
    start_date = request.args.get("start_date")
    end_date = request.args.get("end_date")

    conn = sqlite3.connect(DB_PATH)
    df = pd.read_sql_query("SELECT * FROM records", conn)
    conn.close()

    if df.empty:
        return render_template("dashboard.html", tables=[], labels=[], scores=[])

    df["date"] = pd.to_datetime(df["date"])

    # Specific Date
    if selected_date:
        df = df[df["date"] == pd.to_datetime(selected_date)]

    # Date Range
    elif start_date and end_date:
        df = df[(df["date"] >= pd.to_datetime(start_date)) &
                (df["date"] <= pd.to_datetime(end_date))]

    # Period Filter
    elif period:
        cutoff = datetime.now() - timedelta(days=int(period))
        df = df[df["date"] >= cutoff]

    summary = df.groupby("employee").agg({
        "total_calls": "sum",
        "total_minutes": "sum",
        "total_faxes": "sum",
        "fax_minutes": "sum",
        "score": "sum"
    }).reset_index()

    summary = summary.sort_values(by="score", ascending=False)

    labels = summary["employee"].tolist()
    scores = summary["score"].tolist()

    return render_template("dashboard.html",
                           tables=summary.to_dict(orient="records"),
                           labels=labels,
                           scores=scores)