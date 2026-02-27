from flask import Flask, render_template, request, redirect, url_for, flash
from flask_login import LoginManager, UserMixin, login_user, login_required, logout_user, current_user
import pandas as pd
import sqlite3
import os
from datetime import datetime
from werkzeug.utils import secure_filename
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt

app = Flask(__name__)
app.secret_key = "supersecretkey"

login_manager = LoginManager()
login_manager.init_app(app)
login_manager.login_view = "/"

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DB_PATH = os.path.join(BASE_DIR, "database.db")
STATIC_PATH = os.path.join(BASE_DIR, "static")
UPLOAD_FOLDER = os.path.join(BASE_DIR, "uploads")

os.makedirs(UPLOAD_FOLDER, exist_ok=True)
os.makedirs(STATIC_PATH, exist_ok=True)

app.config["UPLOAD_FOLDER"] = UPLOAD_FOLDER

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
    "Samarth": {"password": "samarth1511", "display": "Samarth"},
    "BigBossSteve": {"password": "masterlogin3217", "display": "Steve"},
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

# ================= EXCEL PROCESSING =================

def process_excel_upload(filepath):
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()

    try:
        df_daily = pd.read_excel(filepath, sheet_name="Daily Update")
        df_daily.columns = df_daily.columns.str.lower().str.strip()

        date_col = [c for c in df_daily.columns if 'date' in c][0]
        name_col = [c for c in df_daily.columns if 'name' in c][0]
        calls_col = [c for c in df_daily.columns if 'calls' in c][0]
        records_col = [c for c in df_daily.columns if 'records received' in c][0]
        fax_col = [c for c in df_daily.columns if 'fax' in c][0]

        df_daily = df_daily.dropna(subset=[name_col])
        df_daily = df_daily[~df_daily[name_col].str.contains("Total|Name", case=False, na=False)]
        df_daily["clean_name"] = df_daily[name_col].str.split().str[0]
        df_daily = df_daily[df_daily["clean_name"].isin(EMPLOYEES)]

        for _, row in df_daily.iterrows():
            emp = row["clean_name"]
            date_val = str(row[date_col]).split(" ")[0]

            calls = pd.to_numeric(row[calls_col], errors="coerce") or 0
            faxes = pd.to_numeric(row[fax_col], errors="coerce") or 0
            records = pd.to_numeric(row[records_col], errors="coerce") or 0

            cursor.execute("SELECT id FROM analytics WHERE employee=? AND date=?", (emp, date_val))
            result = cursor.fetchone()

            if result:
                cursor.execute("""
                    UPDATE analytics 
                    SET total_calls=?, total_faxes=?, records_received=? 
                    WHERE id=?
                """, (calls, faxes, records, result[0]))
            else:
                cursor.execute("""
                    INSERT INTO analytics (employee, date, total_calls, total_faxes, records_received)
                    VALUES (?, ?, ?, ?, ?)
                """, (emp, date_val, calls, faxes, records))

        conn.commit()

    finally:
        conn.close()

# ================= ROUTES =================

@app.route("/", methods=["GET","POST"])
def login():
    if request.method == "POST":
        u = request.form["username"]
        p = request.form["password"]

        if u in USERS and USERS[u]["password"] == p:
            login_user(User(u))
            return redirect("/dashboard")
        else:
            flash("Invalid username or password")

    return render_template("login.html")

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

    df["final_score"] = df["total_calls"] + df["records_received"]
    df = df.sort_values("final_score", ascending=False)
    df["Rank"] = range(1, len(df)+1)

    plt.figure()
    plt.bar(df["employee"], df["final_score"])
    plt.title("Employee Performance")
    plt.savefig(os.path.join(STATIC_PATH, "bar_chart.png"))
    plt.close()

    return render_template("master_dashboard.html",
                           employees=EMPLOYEES,
                           data=df.to_dict(orient="records"),
                           user=current_user.display,
                           bar_chart="bar_chart.png")

@app.route("/upload", methods=["POST"])
@login_required
def upload_file():

    if "file" not in request.files:
        return redirect(url_for("dashboard"))

    file = request.files["file"]

    if file.filename == "":
        return redirect(url_for("dashboard"))

    if file and file.filename.endswith((".xlsx", ".xls")):
        filename = secure_filename(file.filename)
        filepath = os.path.join(app.config["UPLOAD_FOLDER"], filename)
        file.save(filepath)

        process_excel_upload(filepath)
        os.remove(filepath)

    return redirect(url_for("dashboard"))

@app.route("/logout")
@login_required
def logout():
    logout_user()
    return redirect("/")

if __name__ == "__main__":
    app.run(debug=True)