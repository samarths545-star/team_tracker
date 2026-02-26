from flask import Flask, render_template, request, redirect, jsonify
import pandas as pd
import numpy as np
import os

app = Flask(__name__)
app.secret_key = "supersecretkey"

# ================= SAFE DIVIDE =================

def safe_divide(n, d):
    try:
        return n / d if d not in [0, None, np.nan] else 0
    except:
        return 0

# =========================================================
# MAIN PERFORMANCE PROCESSOR FUNCTION
# =========================================================

def process_employee_performance(file_path):

    # ================= STEP 1 — CLEANING =================

    # Read messy Excel (ignore first header row)
    df = pd.read_excel(file_path, header=1)

    # Forward fill Employee Name column
    if "Name" in df.columns:
        df["Name"] = df["Name"].ffill()
    else:
        raise Exception("Column 'Name' not found in sheet.")

    # Remove rows where Campaign = Total
    if "Campaign" in df.columns:
        df = df[df["Campaign"].astype(str).str.strip() != "Total"]

    # Rename columns safely
    column_mapping = {
        "Name": "Employee_Name",
        "Campaign": "Campaign",
        "No. of cases": "No_of_Cases",
        "PORTAL (Datavant/MRO etc.)": "Portal_Requests",
        "Via Fax/Email (Turnaround time-15 days to 60 days)": "Fax_Email_Requests",
        "Total": "Total_Requests_Sent",
        "No. of Records Received (MR & MB)": "Records_Received",
        "Absence of Death certificate/ Kinship/HIPAA signature discrepancy etc.": "Correspondence_Received",
        "Expected": "Expected_Records",
        "Shall be receiving (Barring Facility Rejection)": "Shall_Receive",
        "No. of Records would have received if all the docs available": "Would_Have_Received"
    }

    df = df.rename(columns=column_mapping)

    # Keep only required columns (ignore others safely)
    required_cols = [
        "Employee_Name", "Campaign", "No_of_Cases",
        "Portal_Requests", "Fax_Email_Requests",
        "Total_Requests_Sent", "Records_Received",
        "Correspondence_Received",
        "Expected_Records", "Shall_Receive",
        "Would_Have_Received"
    ]

    df = df[[col for col in required_cols if col in df.columns]]

    # Convert numeric columns safely
    numeric_cols = df.columns.drop(["Employee_Name", "Campaign"])

    for col in numeric_cols:
        df[col] = pd.to_numeric(df[col], errors="coerce").fillna(0)

    cleaned_df = df.copy()

    # ================= STEP 2 — AGGREGATION =================

    summary_df = df.groupby("Employee_Name").agg({
        "No_of_Cases": "sum",
        "Total_Requests_Sent": "sum",
        "Records_Received": "sum",
        "Correspondence_Received": "sum",
        "Expected_Records": "sum",
        "Shall_Receive": "sum"
    }).reset_index()

    summary_df.rename(columns={
        "No_of_Cases": "total_cases",
        "Total_Requests_Sent": "total_requests",
        "Records_Received": "records_received",
        "Correspondence_Received": "correspondence_received",
        "Expected_Records": "expected_records",
        "Shall_Receive": "shall_receive"
    }, inplace=True)

    # ================= STEP 3 — METRICS =================

    summary_df["record_success_rate"] = summary_df.apply(
        lambda x: safe_divide(x["records_received"], x["expected_records"]) * 100, axis=1
    )

    summary_df["efficiency_rate"] = summary_df.apply(
        lambda x: safe_divide(x["records_received"], x["total_requests"]), axis=1
    )

    summary_df["followup_index"] = summary_df.apply(
        lambda x: safe_divide(x["correspondence_received"], x["total_requests"]), axis=1
    )

    summary_df["pending_records"] = (
        summary_df["expected_records"] - summary_df["records_received"]
    )

    summary_df["facility_loss"] = (
        summary_df["expected_records"] - summary_df["shall_receive"]
    )

    summary_df["performance_score"] = (
        (summary_df["record_success_rate"] * 0.4)
        + (summary_df["efficiency_rate"] * 100 * 0.3)
        + ((1 - summary_df["followup_index"]) * 100 * 0.2)
        + ((safe_divide(summary_df["records_received"], summary_df["total_cases"]) * 10) * 0.1)
    )

    # Normalize to 100
    max_score = summary_df["performance_score"].max()
    if max_score > 0:
        summary_df["performance_score"] = (
            summary_df["performance_score"] / max_score * 100
        )

    summary_df["performance_score"] = summary_df["performance_score"].round(2)

    # ================= STEP 4 — ASSIGN GRADE =================

    def assign_grade(score):
        if score >= 90:
            return "A+"
        elif score >= 80:
            return "A"
        elif score >= 70:
            return "B"
        elif score >= 60:
            return "C"
        else:
            return "Needs Improvement"

    summary_df["grade"] = summary_df["performance_score"].apply(assign_grade)

    # ================= STEP 5 — JSON OUTPUT =================

    json_output = summary_df.to_dict(orient="records")

    return cleaned_df, summary_df, json_output

# =========================================================
# FLASK ROUTES
# =========================================================

@app.route("/")
def home():
    return render_template("upload.html")

@app.route("/upload", methods=["POST"])
def upload():

    file = request.files["file"]
    file_path = os.path.join("uploads", file.filename)

    os.makedirs("uploads", exist_ok=True)
    file.save(file_path)

    cleaned_df, summary_df, json_output = process_employee_performance(file_path)

    return render_template(
        "dashboard.html",
        tables=summary_df.to_dict(orient="records"),
        json_data=json_output
    )

# Optional JSON API endpoint
@app.route("/api/performance")
def api_performance():
    return jsonify({"message": "Upload consolidated file first."})

# =========================================================

if __name__ == "__main__":
    app.run(debug=True)