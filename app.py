from flask import Flask, render_template, request, redirect, url_for, flash, session, send_from_directory
from werkzeug.utils import secure_filename
import os
import sqlite3
import smtplib
from email.message import EmailMessage
import pandas as pd
import schedule
import time
import threading
from datetime import datetime

db_initialized = False




# -------------------- CONFIG --------------------
app = Flask(__name__)
app.secret_key = "supersecretkey"

UPLOAD_FOLDER = os.path.join(os.path.dirname(__file__), "uploads")
os.makedirs(UPLOAD_FOLDER, exist_ok=True)
app.config["UPLOAD_FOLDER"] = UPLOAD_FOLDER

ALLOWED_EXTENSIONS = {"png", "jpg", "jpeg", "gif", "pdf"}

def allowed_file(filename):
    return "." in filename and filename.rsplit(".", 1)[1].lower() in ALLOWED_EXTENSIONS

# -------------------- DATABASE --------------------
DATABASE = os.path.join(os.path.dirname(__file__), "users.db")


def get_db_connection():
    conn = sqlite3.connect(DATABASE)
    conn.row_factory = sqlite3.Row
    return conn

def check_user_db(username, password):
    conn = get_db_connection()
    cursor = conn.cursor()

    cursor.execute(
        "SELECT * FROM users WHERE LOWER(username)=LOWER(?) AND password=?",
        (username.strip(), password.strip())
    )

    user = cursor.fetchone()
    conn.close()
    return user


# Ensure maintenance_history table exists
def create_maintenance_table():
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS maintenance_history (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            username TEXT NOT NULL,
            full_name TEXT NOT NULL,
            room_number TEXT NOT NULL,
            amount REAL NOT NULL,
            details TEXT,
            screenshot TEXT,
            submitted_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)
    conn.commit()
    conn.close()





#contact Table 
def create_contact_table():
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS contact_messages (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL,
            email TEXT NOT NULL,
            phone TEXT,
            message TEXT NOT NULL,
            submitted_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)
    conn.commit()
    conn.close()




def init_users_table():
    conn = sqlite3.connect(DATABASE)
    cursor = conn.cursor()
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS users (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            username TEXT NOT NULL,
            password TEXT NOT NULL
        )
    """)
    conn.commit()
    conn.close()

@app.before_request
def initialize_database_once():
    global db_initialized
    if not db_initialized:
        create_maintenance_table()
        create_contact_table()
        init_users_table()
        db_initialized = True



#----------------------email function-----------------------
def send_contact_email(name, email, phone, message):
    ADMIN_EMAIL = "sumitjadhao202@gmail.com"        # 🔴 admin email
    SENDER_EMAIL = "amy975017@gmail.com"   # 🔴 sender gmail
    APP_PASSWORD = "lnwk uxtg vtdb fnjl"     # 🔴 gmail app password

    msg = EmailMessage()
    msg["Subject"] = "New Contact Message - GreenLeaf Residency"
    msg["From"] = SENDER_EMAIL
    msg["To"] = ADMIN_EMAIL

    msg.set_content(f"""
New Contact Message Received

Name   : {name}
Email  : {email}
Phone  : {phone}

Message:
{message}
""")

    with smtplib.SMTP_SSL("smtp.gmail.com", 465) as server:
        server.login(SENDER_EMAIL, APP_PASSWORD)
        server.send_message(msg)


#----------------------Excel generate function-----------------------
def generate_maintenance_excel():
    conn = get_db_connection()
    df = pd.read_sql_query("SELECT * FROM maintenance_history", conn)
    conn.close()

    filename = f"maintenance_report_{datetime.now().date()}.xlsx"
    df.to_excel(filename, index=False)

    return filename

#-----------------------excel email function----------------------
def send_maintenance_excel(file_path):
    ADMIN_EMAIL = "sumitjadhao202@gmail.com"
    SENDER_EMAIL = "amy975017@gmail.com"
    APP_PASSWORD = "lnwk uxtg vtdb fnjl"

    msg = EmailMessage()
    msg["Subject"] = "Daily Maintenance Report - GreenLeaf Residency"
    msg["From"] = SENDER_EMAIL
    msg["To"] = ADMIN_EMAIL
    msg.set_content("Attached is the automatic maintenance report.")

    with open(file_path, "rb") as f:
        msg.add_attachment(
            f.read(),
            maintype="application",
            subtype="vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            filename=file_path
        )

    with smtplib.SMTP_SSL("smtp.gmail.com", 465) as server:
        server.login(SENDER_EMAIL, APP_PASSWORD)
        server.send_message(msg)
#-------------------------automatic schedule function----------------------
def daily_maintenance_job():
    file = generate_maintenance_excel()
    send_maintenance_excel(file)

# -------------------- ROUTES --------------------

@app.route("/")
def root():
    return redirect(url_for("login"))

# Login Page
@app.route("/login", methods=["GET", "POST"])
def login():
    if request.method == "POST":
        username = request.form["username"]
        password = request.form["password"]

        # Static admin login
        if username == "admin" and password == "1234":
            session["user"] = "admin"
            flash("Admin Login Successful ✅", "success")
            return redirect(url_for("home"))

        # Database login
        user = check_user_db(username, password)
        if user:
            session["user"] = user["username"]
            flash("Login Successful ✅", "success")
            return redirect(url_for("home"))

        else:
            flash("Invalid username or password ❌", "error")
            return redirect(url_for("login"))

    return render_template("login.html")

# Home / Index Page
@app.route("/home")
def home():
    if "user" not in session:
        flash("Please login first ❌", "error")
        return redirect(url_for("login"))
    return render_template("index.html", user=session["user"])

# Dashboard Page
@app.route("/dashboard")
def dashboard():
    if "user" not in session:
        flash("Please login first ❌", "error")
        return redirect(url_for("login"))
    return render_template("dashboard.html", user=session["user"])

# Logout
@app.route("/logout")
def logout():
    session.pop("user", None)
    flash("Logged out successfully ✅", "success")
    return redirect(url_for("login"))

# -------------------- Maintenance Form --------------------
@app.route("/maintenance", methods=["GET", "POST"])
def maintenance():
    if "user" not in session:
        flash("Please login first ❌", "error")
        return redirect(url_for("login"))

    if request.method == "POST":
        full_name = request.form["full_name"]
        room_no = request.form["room_no"]
        amount = request.form["amount"]
        details = request.form.get("details", "")
        file = request.files.get("screenshot")

        filename = None
        if file and allowed_file(file.filename):
            filename = secure_filename(file.filename)
            file.save(os.path.join(app.config["UPLOAD_FOLDER"], filename))

        # Database me save (ab submitted_at auto insert hoga)
                # ✅ Correct query with submitted_at date
        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute("""
            INSERT INTO maintenance_history
            (username, full_name, room_number, amount, details, screenshot, submitted_at)
            VALUES (?, ?, ?, ?, ?, ?, datetime('now','localtime'))
        """, (session["user"], full_name, room_no, amount, details, filename))
        conn.commit()
        conn.close()


        flash("Maintenance payment submitted ✅", "success")
        return redirect(url_for("home"))

    return render_template("maintenance.html")

# Serve uploaded files
@app.route("/uploads/<filename>")
def uploaded_file(filename):
    return send_from_directory(app.config["UPLOAD_FOLDER"], filename)

# -------------------- Maintenance History --------------------
@app.route("/history")
def  maintenance_history():
    if "user" not in session:
        flash("Please login first ❌", "error")
        return redirect(url_for("login"))

    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM maintenance_history WHERE username=?", (session["user"],))
    records = cursor.fetchall()
    conn.close()

    return render_template("history.html", records=records, user=session["user"])

# -------------------- Contact Form --------------------
@app.route("/contact", methods=["POST"])
def contact():
    if "user" not in session:
        flash("Please login first ❌", "error")
        return redirect(url_for("login"))

    name = request.form["name"]
    email = request.form["email"]
    phone = request.form.get("phone", "")
    message = request.form["message"]

    # 1️⃣ DB me save
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("""
        INSERT INTO contact_messages (name, email, phone, message)
        VALUES (?, ?, ?, ?)
    """, (name, email, phone, message))
    conn.commit()
    conn.close()

    # 2️⃣ Admin ko email send
    send_contact_email(name, email, phone, message)

    flash("Message sent successfully to admin ✅", "success")
    return redirect(url_for("home"))

# ⏰ TEMPORARY TEST: every 1 minute
schedule.every().days.at("00:00").do(daily_maintenance_job)

def run_scheduler():
    while True:
        schedule.run_pending()
        time.sleep(60)

threading.Thread(target=run_scheduler, daemon=True).start() 



# -------------------- RUN APP --------------------
if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port)
