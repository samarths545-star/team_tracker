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
import traceback

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
        call_minutes REAL DEFAULT 0,
        total_faxes INTEGER DEFAULT 0,
        fax_minutes REAL DEFAULT 0,
        cases INTEGER DEFAULT 0,
        facilities_total INTEGER DEFAULT 0,
        records_received INTEGER DEFAULT 0,
        expected_records INTEGER DEFAULT 0,
        shall_be_receiving INTEGER DEFAULT 0,
        correspondence_received INTEGER DEFAULT 0,
        summons_efile INTEGER DEFAULT 0,
        summons_served INTEGER DEFAULT 0,
        denials_received INTEGER DEFAULT 0
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

# ================= HELPER FUNCTIONS =================

def safe_numeric(val):
    """Safely convert value to numeric, return 0 if fails"""
    if pd.isna(val) or val == "":
        return 0
    try:
        return float(val)
    except:
        return 0

def find_column(df, keywords):
    """Find column by keywords (flexible matching)"""
    cols_lower = df.columns.str.lower().str.strip()
    for keyword in (keywords if isinstance(keywords, list) else [keywords]):
        for idx, col in enumerate(cols_lower):
            if keyword.lower() in col:
                return df.columns[idx]
    return None

# ================= FILE PROCESSING =================

def process_consolidated(filepath, employee):
    """Process Consolidated Excel sheet"""
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    
    try:
        # Try to read the first sheet
        df = pd.read_excel(filepath, sheet_name=0)
        df.columns = df.columns.str.lower().str.strip()
        
        print(f"Processing Consolidated for {employee}")
        print(f"Columns: {list(df.columns)}")
        
        # Find relevant columns
        cases_col = find_column(df, ['cases', 'case'])
        facilities_col = find_column(df, ['facilities', 'total'])
        records_col = find_column(df, ['records received', 'records'])
        expected_col = find_column(df, ['expected'])
        shall_col = find_column(df, ['shall', 'receiving'])
        correspondence_col = find_column(df, ['correspondence', 'death'])
        efile_col = find_column(df, ['efile', 'e-file', 'e_file'])
        served_col = find_column(df, ['served', 'summons'])
        denials_col = find_column(df, ['denial', 'denials'])
        
        # Get or create record for today
        date_val = datetime.now().strftime("%Y-%m-%d")
        cursor.execute("SELECT id FROM analytics WHERE employee=? AND date=?", (employee, date_val))
        result = cursor.fetchone()
        
        # Aggregate the data (sum all rows, skip total rows)
        cases_sum = 0
        facilities_sum = 0
        records_sum = 0
        expected_sum = 0
        shall_sum = 0
        correspondence_sum = 0
        efile_sum = 0
        served_sum = 0
        denials_sum = 0
        
        for _, row in df.iterrows():
            # Skip total rows
            if 'total' in str(row.iloc[0]).lower():
                continue
            
            if cases_col:
                cases_sum += int(safe_numeric(row[cases_col]))
            if facilities_col:
                facilities_sum += int(safe_numeric(row[facilities_col]))
            if records_col:
                records_sum += int(safe_numeric(row[records_col]))
            if expected_col:
                expected_sum += int(safe_numeric(row[expected_col]))
            if shall_col:
                shall_sum += int(safe_numeric(row[shall_col]))
            if correspondence_col:
                correspondence_sum += int(safe_numeric(row[correspondence_col]))
            if efile_col:
                efile_sum += int(safe_numeric(row[efile_col]))
            if served_col:
                served_sum += int(safe_numeric(row[served_col]))
            if denials_col:
                denials_sum += int(safe_numeric(row[denials_col]))
        
        if result:
            cursor.execute("""
                UPDATE analytics 
                SET cases=?, facilities_total=?, records_received=?, expected_records=?, 
                    shall_be_receiving=?, correspondence_received=?, summons_efile=?, 
                    summons_served=?, denials_received=?
                WHERE id=?
            """, (cases_sum, facilities_sum, records_sum, expected_sum, shall_sum, 
                  correspondence_sum, efile_sum, served_sum, denials_sum, result[0]))
        else:
            cursor.execute("""
                INSERT INTO analytics 
                (employee, date, cases, facilities_total, records_received, expected_records,
                 shall_be_receiving, correspondence_received, summons_efile, summons_served, denials_received)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (employee, date_val, cases_sum, facilities_sum, records_sum, expected_sum, shall_sum,
                  correspondence_sum, efile_sum, served_sum, denials_sum))
        
        conn.commit()
        print(f"✓ Consolidated data processed for {employee}")
        
    except Exception as e:
        print(f"Error processing Consolidated: {e}")
        traceback.print_exc()
    finally:
        conn.close()

def process_calls(filepath, employee):
    """Process Call Log (Excel or CSV)"""
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    
    try:
        # Read file (handle both Excel and CSV)
        if filepath.endswith('.csv'):
            df = pd.read_csv(filepath)
        else:
            df = pd.read_excel(filepath)
        
        df.columns = df.columns.str.lower().str.strip()
        
        print(f"Processing Calls for {employee}")
        print(f"Columns: {list(df.columns)}")
        
        # Find duration column
        duration_col = find_column(df, ['duration'])
        
        if duration_col is None:
            print("⚠ Duration column not found in call log")
            return
        
        # Sum total call minutes (ignore names, use selected employee)
        total_minutes = 0
        for _, row in df.iterrows():
            duration = str(row[duration_col]).strip()
            # Parse time format like "0:03:35" or "03:35"
            try:
                parts = duration.split(':')
                if len(parts) == 3:
                    total_minutes += int(parts[0]) * 60 + int(parts[1]) + int(parts[2]) / 60
                elif len(parts) == 2:
                    total_minutes += int(parts[0]) + int(parts[1]) / 60
            except:
                pass
        
        total_calls = len(df)  # Count of rows
        
        # Get or create record for today
        date_val = datetime.now().strftime("%Y-%m-%d")
        cursor.execute("SELECT id FROM analytics WHERE employee=? AND date=?", (employee, date_val))
        result = cursor.fetchone()
        
        if result:
            cursor.execute("""
                UPDATE analytics 
                SET total_calls=?, call_minutes=?
                WHERE id=?
            """, (total_calls, total_minutes, result[0]))
        else:
            cursor.execute("""
                INSERT INTO analytics (employee, date, total_calls, call_minutes)
                VALUES (?, ?, ?, ?)
            """, (employee, date_val, total_calls, total_minutes))
        
        conn.commit()
        print(f"✓ Call data processed: {total_calls} calls, {total_minutes:.1f} minutes for {employee}")
        
    except Exception as e:
        print(f"Error processing Calls: {e}")
        traceback.print_exc()
    finally:
        conn.close()

def process_faxes(filepath, employee):
    """Process Fax Log (Excel or CSV)"""
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    
    try:
        # Read file (handle both Excel and CSV)
        if filepath.endswith('.csv'):
            df = pd.read_csv(filepath)
        else:
            df = pd.read_excel(filepath)
        
        df.columns = df.columns.str.lower().str.strip()
        
        print(f"Processing Faxes for {employee}")
        print(f"Columns: {list(df.columns)}")
        
        # Count total faxes
        total_faxes = len(df)
        
        # Calculate fax minutes: each fax = 20 minutes
        fax_minutes = total_faxes * 20
        
        # Get or create record for today
        date_val = datetime.now().strftime("%Y-%m-%d")
        cursor.execute("SELECT id FROM analytics WHERE employee=? AND date=?", (employee, date_val))
        result = cursor.fetchone()
        
        if result:
            cursor.execute("""
                UPDATE analytics 
                SET total_faxes=?, fax_minutes=?
                WHERE id=?
            """, (total_faxes, fax_minutes, result[0]))
        else:
            cursor.execute("""
                INSERT INTO analytics (employee, date, total_faxes, fax_minutes)
                VALUES (?, ?, ?, ?)
            """, (employee, date_val, total_faxes, fax_minutes))
        
        conn.commit()
        print(f"✓ Fax data processed: {total_faxes} faxes ({fax_minutes} minutes) for {employee}")
        
    except Exception as e:
        print(f"Error processing Faxes: {e}")
        traceback.print_exc()
    finally:
        conn.close()

# ================= SCORING & INSIGHTS =================

def calculate_scores(df):
    """Calculate performance scores"""
    
    # Scoring formula
    df["communication_score"] = df["call_minutes"] + df["fax_minutes"]
    df["records_score"] = df["records_received"] * 2
    df["legal_score"] = (df["summons_efile"] * 5) + (df["summons_served"] * 5)
    
    df["final_score"] = df["communication_score"] + df["records_score"] + df["legal_score"]
    
    # Grade calculation
    def get_grade(score):
        if score >= 500:
            return "A+"
        elif score >= 400:
            return "A"
        elif score >= 300:
            return "B"
        elif score >= 200:
            return "C"
        else:
            return "D"
    
    df["Grade"] = df["final_score"].apply(get_grade)
    
    return df

def generate_insights(df):
    """Generate text insights for each employee"""
    insights = {}
    avg_calls = df["call_minutes"].mean() if len(df) > 0 else 0
    avg_fax = df["fax_minutes"].mean() if len(df) > 0 else 0
    avg_records = df["records_received"].mean() if len(df) > 0 else 0
    
    for _, row in df.iterrows():
        emp = row["employee"]
        comments = []
        
        if row["call_minutes"] < avg_calls * 0.8 and avg_calls > 0:
            comments.append(f"Call time below average")
        
        if row["fax_minutes"] < avg_fax * 0.8 and avg_fax > 0:
            comments.append(f"Faxes below average")
        
        if row["records_received"] < avg_records * 0.8 and avg_records > 0:
            comments.append(f"Records received below average")
        
        if not comments:
            comments.append("✓ Performing at or above average")
        
        insights[emp] = " | ".join(comments)
    
    return insights

# ================= ROUTES =================

@app.route("/", methods=["GET","POST"])
def login():
    if request.method == "POST":
        u = request.form.get("username", "")
        p = request.form.get("password", "")

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
                               user=current_user.display,
                               insights={})

    # Group by employee and sum
    df = df.groupby("employee").sum(numeric_only=True).reset_index()
    
    # Calculate scores
    df = calculate_scores(df)
    df = df.sort_values("final_score", ascending=False)
    df["Rank"] = range(1, len(df)+1)
    
    # Generate insights
    insights = generate_insights(df)
    
    # Create visualizations
    fig, axes = plt.subplots(2, 2, figsize=(14, 10))
    
    # Bar chart - Final Score
    axes[0, 0].bar(df["employee"], df["final_score"], color='steelblue')
    axes[0, 0].set_title("Final Performance Score")
    axes[0, 0].set_ylabel("Score")
    axes[0, 0].tick_params(axis='x', rotation=45)
    
    # Bar chart - Communication vs Records vs Legal
    x = range(len(df))
    axes[0, 1].bar([i - 0.25 for i in x], df["communication_score"], width=0.25, label='Communication')
    axes[0, 1].bar([i for i in x], df["records_score"], width=0.25, label='Records')
    axes[0, 1].bar([i + 0.25 for i in x], df["legal_score"], width=0.25, label='Legal')
    axes[0, 1].set_xticks(x)
    axes[0, 1].set_xticklabels(df["employee"], rotation=45)
    axes[0, 1].set_title("Score Breakdown by Category")
    axes[0, 1].legend()
    
    # Bar chart - Call vs Fax Minutes
    axes[1, 0].bar([i - 0.2 for i in x], df["call_minutes"], width=0.4, label='Call Minutes')
    axes[1, 0].bar([i + 0.2 for i in x], df["fax_minutes"], width=0.4, label='Fax Minutes')
    axes[1, 0].set_xticks(x)
    axes[1, 0].set_xticklabels(df["employee"], rotation=45)
    axes[1, 0].set_title("Communication Time Breakdown")
    axes[1, 0].legend()
    
    # Pie chart - Distribution
    axes[1, 1].pie(df["final_score"], labels=df["employee"], autopct='%1.1f%%')
    axes[1, 1].set_title("Score Distribution")
    
    plt.tight_layout()
    plt.savefig(os.path.join(STATIC_PATH, "dashboard_charts.png"), dpi=100, bbox_inches='tight')
    plt.close()

    return render_template("master_dashboard.html",
                           employees=EMPLOYEES,
                           data=df.to_dict(orient="records"),
                           user=current_user.display,
                           insights=insights,
                           bar_chart="dashboard_charts.png")

@app.route("/upload", methods=["POST"])
@login_required
def upload_file():
    employee = request.form.get("employee")
    
    if not employee or employee not in EMPLOYEES:
        flash("Please select a valid employee")
        return redirect(url_for("dashboard"))
    
    try:
        # Process Consolidated (required)
        if 'consolidated' in request.files and request.files['consolidated'].filename:
            file = request.files['consolidated']
            filename = secure_filename(file.filename)
            filepath = os.path.join(app.config["UPLOAD_FOLDER"], filename)
            file.save(filepath)
            process_consolidated(filepath, employee)
            os.remove(filepath)
            flash(f"✓ Consolidated data uploaded for {employee}")
        
        # Process Calls (optional)
        if 'calls' in request.files and request.files['calls'].filename:
            file = request.files['calls']
            filename = secure_filename(file.filename)
            filepath = os.path.join(app.config["UPLOAD_FOLDER"], filename)
            file.save(filepath)
            process_calls(filepath, employee)
            os.remove(filepath)
            flash(f"✓ Call log uploaded for {employee}")
        
        # Process Faxes (optional)
        if 'faxes' in request.files and request.files['faxes'].filename:
            file = request.files['faxes']
            filename = secure_filename(file.filename)
            filepath = os.path.join(app.config["UPLOAD_FOLDER"], filename)
            file.save(filepath)
            process_faxes(filepath, employee)
            os.remove(filepath)
            flash(f"✓ Fax log uploaded for {employee}")
        
    except Exception as e:
        flash(f"Error processing files: {str(e)}")
        print(traceback.format_exc())

    return redirect(url_for("dashboard"))

@app.route("/logout")
@login_required
def logout():
    logout_user()
    return redirect("/")

if __name__ == "__main__":
    app.run(debug=True)