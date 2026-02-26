from flask import Flask, render_template, request, redirect, url_for, flash
from flask_login import LoginManager, UserMixin, login_user, login_required, logout_user, current_user
from flask_mail import Mail, Message
from itsdangerous import URLSafeTimedSerializer
import pandas as pd
import sqlite3
import os

app = Flask(__name__)
app.secret_key = "supersecretkey"

# ================= EMAIL CONFIG =================
app.config['MAIL_SERVER'] = 'smtp.gmail.com'
app.config['MAIL_PORT'] = 587
app.config['MAIL_USE_TLS'] = True
app.config['MAIL_USERNAME'] = 'samarth@draftandcraft.com'
app.config['MAIL_PASSWORD'] = 'YOUR_EMAIL_PASSWORD'  # CHANGE THIS
mail = Mail(app)

serializer = URLSafeTimedSerializer(app.secret_key)

# ================= LOGIN =================

login_manager = LoginManager()
login_manager.init_app(app)

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DB_PATH = os.path.join(BASE_DIR, "database.db")

# ================= USERS =================

USERS = {
    "Steve": {"password": "Masterlogin3217", "role": "attorney"},
    "Kavish": {"password": "1234", "role": "employee"},
    "Chirag": {"password": "1234", "role": "employee"},
    "Sahil": {"password": "1234", "role": "employee"},
    "Tushar": {"password": "1234", "role": "employee"},
    "Samarth": {"password": "samarth1511", "role": "master"},
    "Pragati": {"password": "pragati1711", "role": "master"}
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
            return redirect("/dashboard")
        flash("Invalid credentials")
    return render_template("login.html")

@app.route("/logout")
@login_required
def logout():
    logout_user()
    return redirect("/")

# ================= DASHBOARD ROUTING =================

@app.route("/dashboard")
@login_required
def dashboard():

    if current_user.role in ["attorney","master"]:
        return redirect("/attorney_dashboard")
    else:
        return redirect("/employee_dashboard")

# ================= FORGOT PASSWORD =================

@app.route("/forgot_password", methods=["GET","POST"])
def forgot_password():
    if request.method == "POST":
        email = "samarth@draftandcraft.com"

        token = serializer.dumps(email, salt="password-reset")

        reset_link = url_for("reset_password", token=token, _external=True)

        msg = Message("Password Reset",
                      sender="samarth@draftandcraft.com",
                      recipients=[email])
        msg.body = f"Click this link to reset password:\n\n{reset_link}"

        mail.send(msg)

        flash("Reset link sent to email.")
        return redirect("/")

    return render_template("forgot_password.html")

@app.route("/reset_password/<token>", methods=["GET","POST"])
def reset_password(token):
    try:
        email = serializer.loads(token, salt="password-reset", max_age=3600)
    except:
        return "Link expired"

    if request.method == "POST":
        new_password = request.form["password"]
        USERS["Samarth"]["password"] = new_password
        flash("Password updated.")
        return redirect("/")

    return render_template("reset_password.html")

# ================= EXISTING ROUTES KEPT =================
# (Your employee_dashboard, attorney_dashboard, uploads, summons stay unchanged)