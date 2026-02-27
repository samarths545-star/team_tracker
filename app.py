from flask import Flask, render_template, request, redirect
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

UPLOAD_FOLDER = os.path.join(BASE_DIR, 'uploads')
os.makedirs(UPLOAD_FOLDER, exist_ok=True)
os.makedirs(STATIC_PATH, exist_ok=True)
app.config['UPLOAD_FOLDER'] = UPLOAD_FOLDER

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

# ================= DATA EXTRACTION =================

def process_excel_upload(filepath):

    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()

    try:
        # ================= DAILY UPDATE =================
        df_daily = pd.read_excel(filepath, sheet_name="Daily Update", header=0)
        df_daily.columns = df_daily.columns.str.lower().str.strip()

        date_col = [c for c in df_daily.columns if 'date' in c][0]
        name_col = [c for c in df_daily.columns if 'name' in c][0]
        calls_col = [c for c in df_daily.columns if 'calls' in c][0]
        records_col = [c for c in df_daily.columns if 'records received' in c][0]
        fax_col = [c for c in df_daily.columns if 'fax' in c][0]

        df_daily = df_daily.dropna(subset=[name_col])
        df_daily = df_daily[~df_daily[name_col].str.contains("Total|Name", na=False, case=False)]

        df_daily['clean_name'] = df_daily[name_col].astype(str).str.strip().str.split().str[0]
        df_daily = df_daily[df_daily['clean_name'].isin(EMPLOYEES)]

        for _, row in df_daily.iterrows():
            emp = row['clean_name']
            date_val = str(row[date_col]).split(' ')[0]

            calls = pd.to_numeric(row[calls_col], errors='coerce')
            faxes = pd.to_numeric(row[fax_col], errors='coerce')
            records = pd.to_numeric(row[records_col], errors='coerce')

            cursor.execute("SELECT id FROM analytics WHERE employee=? AND date=?", (emp, date_val))
            result = cursor.fetchone()

            if result:
                cursor.execute("""
                    UPDATE analytics SET total_calls=?, total_faxes=?, records_received=? 
                    WHERE id=?
                """, (
                    calls if pd.notna(calls) else 0,
                    faxes if pd.notna(faxes) else 0,
                    records if pd.notna(records) else 0,
                    result[0]
                ))
            else:
                cursor.execute("""
                    INSERT INTO analytics (employee, date, total_calls, total_faxes, records_received)
                    VALUES (?, ?, ?, ?, ?)
                """, (
                    emp,
                    date_val,
                    calls if pd.notna(calls) else 0,
                    faxes if pd.notna(faxes) else 0,
                    records if pd.notna(records) else 0
                ))

        # ================= CONSOLIDATED UPDATE =================
        df_cons = pd.read_excel(filepath, sheet_name="Consolidated Update", header=None)

        df_cons[0] = df_cons[0].ffill()
        totals = df_cons[df_cons[1].astype(str).str.strip().str.lower() == 'total'].copy()

        totals['clean_name'] = totals[0].astype(str).str.strip().str.split().str[0]
        totals = totals[totals['clean_name'].isin(EMPLOYEES)]

        today = datetime.now().strftime("%Y-%m-%d")

        for _, row in totals.iterrows():
            emp = row['clean_name']

            cases = pd.to_numeric(row[2], errors='coerce')
            facilities = pd.to_numeric(row[3], errors='coerce')
            expected = pd.to_numeric(row[9], errors='coerce')  # Correct column
            records_if_all = pd.to_numeric(row[11], errors='coerce')  # Correct column

            cursor.execute("SELECT id FROM analytics WHERE employee=? AND date=?", (emp, today))
            result = cursor.fetchone()

            if result:
                cursor.execute("""
                    UPDATE analytics 
                    SET cases=?, facilities_total=?, expected_records=?, records_if_all_docs=? 
                    WHERE id=?
                """, (
                    cases if pd.notna(cases) else 0,
                    facilities if pd.notna(facilities) else 0,
                    expected if pd.notna(expected) else 0,
                    records_if_all if pd.notna(records_if_all) else 0,
                    result[0]
                ))
            else:
                cursor.execute("""
                    INSERT INTO analytics 
                    (employee, date, cases, facilities_total, expected_records, records_if_all_docs)
                    VALUES (?, ?, ?, ?, ?, ?)
                """, (
                    emp,
                    today,
                    cases if pd.notna(cases) else 0,
                    facilities if pd.notna(facilities) else 0,
                    expected if pd.notna(expected) else 0,
                    records_if_all if pd.notna(records_if_all) else 0
                ))

        conn.commit()

    finally:
        conn.close()

# ================= UPLOAD =================

@app.route("/upload", methods=["POST"])
@login_required
def upload_file():

    if 'file' not in request.files:
        return redirect("/dashboard")

    file = request.files['file']

    if file.filename == '':
        return redirect("/dashboard")

    if file and file.filename.endswith(('.xlsx', '.xls')):
        filename = secure_filename(file.filename)
        filepath = os.path.join(app.config['UPLOAD_FOLDER'], filename)
        file.save(filepath)

        process_excel_upload(filepath)

        os.remove(filepath)

    return redirect("/dashboard")

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

    # Safe max calculations
    max_comm = df["call_minutes"].max() or 1
    max_cases = df["cases"].max() or 1

    df["call_efficiency"] = df["connected_calls"] / df["total_calls"].replace(0, 1)
    df["record_fulfillment"] = df["records_received"] / df["expected_records"].replace(0, 1)
    df["doc_completion"] = df["records_received"] / df["records_if_all_docs"].replace(0, 1)
    df["communication_time"] = df["call_minutes"] + df["fax_minutes"]

    df["communication_score"] = (
        df["call_efficiency"] * 40 +
        (df["communication_time"] / max_comm) * 60
    )

    df["records_score"] = (
        df["record_fulfillment"] * 50 +
        df["doc_completion"] * 50
    )

    df["operational_score"] = (
        (df["cases"] / max_cases) * 50 +
        (1 - (df["correspondence_received"] / df["facilities_total"].replace(0, 1))) * 50
    )

    df["final_score"] = (
        df["communication_score"] * 0.30 +
        df["records_score"] * 0.30 +
        df["operational_score"] * 0.40
    )

    df["final_score"] = df["final_score"].clip(upper=100)

    df = df.sort_values("final_score", ascending=False)
    df["Rank"] = range(1, len(df)+1)

    plt.figure()
    plt.bar(df["employee"], df["final_score"])
    plt.title("Employee Final Performance Score")
    plt.savefig(os.path.join(STATIC_PATH, "bar_chart.png"))
    plt.close()

    return render_template("master_dashboard.html",
                           employees=EMPLOYEES,
                           data=df.to_dict(orient="records"),
                           user=current_user.display,
                           bar_chart="bar_chart.png")

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

if __name__ == "__main__":
    app.run(debug=True)