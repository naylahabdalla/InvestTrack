from flask import Flask, render_template, request, redirect, url_for, session
from supabase import create_client, Client
import yfinance as yf
import requests
from werkzeug.security import generate_password_hash, check_password_hash
import re
from functools import wraps

url: str = "https://livxzkknhrqusxkyrieq.supabase.co"
key: str = "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJpc3MiOiJzdXBhYmFzZSIsInJlZiI6Imxpdnh6a2tuaHJxdXN4a3lyaWVxIiwicm9sZSI6ImFub24iLCJpYXQiOjE3NzQ1MDk0NjUsImV4cCI6MjA5MDA4NTQ2NX0.b1WV6RtX3suBkTquZiY-4NS8p0QOzViGimAJkrqMr4U"
supabase: Client = create_client(url, key)

app = Flask(__name__, template_folder='../templates', static_folder='../static')
app.secret_key = "investtrack_secret"

# ---------------- PASSWORD CHECK ----------------
def is_strong_password(password):
    if len(password) < 8:
        return False
    if not re.search("[A-Za-z]", password):
        return False
    if not re.search("[0-9]", password):
        return False
    if not re.search("[!@#$%^&*(),.?\":{}|<>]", password):
        return False
    return True


# ---------------- HOME ----------------
@app.route("/")
def home():
    return render_template("index.html", user=session.get("user"))

# ---------------- SIGNUP ----------------
@app.route("/signup", methods=["GET", "POST"])
def signup():
    error = None

    if request.method == "POST":
        username = request.form.get("username", "")
    
        password = request.form["password"]
        confirm = request.form["confirm_password"]

        if password != confirm:
            error = "Passwords do not match"
        elif not is_strong_password(password):
            error = "Password requires 8+ chars, letter, number, and special character"
        else:
            hashed = generate_password_hash(password)

            try:
                supabase.table("users").insert({"username": username, "current_hash": hashed}).execute()

                session["user"] = username
                return redirect("/dashboard")

            except Exception as e:
                err_msg = str(e).lower()
                if "duplicate key value" in err_msg or "unique violation" in err_msg or "23505" in err_msg or "already exists" in err_msg:
                    error = "Username already exists"
                else:
                    error = "An error occurred: " + str(e)


    return render_template("signup.html", error=error)

# ---------------- LOGIN ----------------
@app.route("/login", methods=["GET", "POST"])
def login():
    error = None

    if request.method == "POST":
        username = request.form["username"]
        password = request.form["password"]

        response = supabase.table("users").select("*").eq("username", username).execute()
        users = response.data
        user = users[0] if users else None

        # ✅ SAFE LOGIN CHECK
        if user and user.get("current_hash") and check_password_hash(user.get("current_hash"), password):
            session["user"] = username
            return redirect("/dashboard")
        else:
            error = "Invalid username or password"

    return render_template("login.html", error=error)

# ---------------- DASHBOARD ----------------
@app.route("/dashboard")
def dashboard():
    if "user" not in session:
        return redirect("/login")

    response = supabase.table("investments").select("*").eq("username", session["user"]).execute()
    investments = [(inv["id"], inv["asset_name"], inv["asset_type"], inv["amount"], inv["username"]) for inv in response.data]

    total = sum(float(inv[3]) for inv in investments)

    current = total * 1.23
    gain = current - total
    percent = (gain / total * 100) if total > 0 else 0

    return render_template(
        "dashboard.html", user=session.get("user"),
        investments=investments,
        total=round(total,2),
        current=round(current,2),
        gain=round(gain,2),
        percent=round(percent,2),
        count=len(investments),
        apple=150.0,
        tesla=200.0,
        btc=40000.0,
        eth=2500.0
    )

# ---------------- ADD ----------------
@app.route("/add", methods=["GET", "POST"])
def add():
    if "user" not in session:
        return redirect("/login")

    if request.method == "POST":
        if session.get("is_demo"):
            return redirect("/dashboard")
        
        name = request.form["asset_name"]
        type_ = request.form["asset_type"]
        amount = float(request.form["amount"])

        supabase.table("investments").insert({"asset_name": name, "asset_type": type_, "amount": amount, "username": session["user"]}).execute()

        return redirect("/dashboard")

    return render_template("add_investment.html", user=session.get("user"))

@app.route("/logout")
def logout():
    session.pop("user", None)
    session.pop("is_demo", None)
    return redirect("/")

# ---------------- DEMO MODE ----------------
@app.route("/demo")
def demo():
    session["user"] = "demo_user"
    session["is_demo"] = True
    return redirect("/dashboard")

def demo_guard(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if session.get("is_demo"):
            return redirect("/dashboard")
        return f(*args, **kwargs)
    return decorated_function

@app.route("/analytics")
def analytics():

    if "user" not in session:
        return redirect("/login")

    response = supabase.table("investments").select("*").eq("username", session["user"]).execute()
    investments = [(inv["id"], inv["asset_name"], inv["asset_type"], inv["amount"], inv["username"]) for inv in response.data]

    total = sum(float(inv[3]) for inv in investments)

    current = total * 1.23
    gain = current - total
    percent = round((gain / total) * 100, 2) if total > 0 else 0

    labels = []
    values = []

    asset_totals = {}
    for inv in investments:
        name = inv[1]
        amount = float(inv[3])
        asset_totals[name] = asset_totals.get(name, 0) + amount

    for name, value in asset_totals.items():
        labels.append(name)
        values.append(round(value, 2))

    return render_template(
        "analytics.html",
        user=session.get("user"),
        total=round(total,2),
        current=round(current,2),
        gain=round(gain,2),
        percent=percent,
        labels=labels,
        values=values
    )

@app.route("/feedback", methods=["GET", "POST"])
def feedback():

    if "user" not in session:
        return redirect("/login")

    if request.method == "POST":
        if session.get("is_demo"):
            return redirect("/dashboard")
            
        message = request.form["message"]

        supabase.table("feedback").insert({"username": session["user"], "message": message}).execute()

        return redirect("/dashboard")

    return render_template("feedback.html", user=session.get("user"))

@app.route("/learn")
def learn():

    if "user" not in session:
        return redirect("/login")

    return render_template("learn.html", user=session.get("user"))
@app.route("/portfolio")
def portfolio():
    if "user" not in session: return redirect("/login")
    response = supabase.table("investments").select("*").eq("username", session["user"]).execute()
    investments = [(inv["id"], inv["asset_name"], inv["asset_type"], inv["amount"], inv["username"]) for inv in response.data]
    total = sum(float(inv[3]) for inv in investments)
    return render_template("portfolio.html", user=session.get("user"), investments=investments, total=round(total, 2))

@app.route("/delete/<int:id>")
def delete(id):
    if "user" not in session: return redirect("/login")
    if session.get("is_demo"): return redirect("/dashboard")
    supabase.table("investments").delete().eq("id", id).eq("username", session["user"]).execute()
    return redirect("/portfolio")

@app.route("/currency", methods=["GET", "POST"])
def currency():
    if "user" not in session: return redirect("/login")
    result = None
    if request.method == "POST":
        try:
            amount = float(request.form.get("amount", 0))
        except ValueError:
            amount = 0
        from_curr = request.form.get("from_currency")
        to_curr = request.form.get("to_currency")
        rates = {"USD": 1.0, "EUR": 0.92, "GBP": 0.79, "TRY": 31.0, "JPY": 150.0}
        if from_curr in rates and to_curr in rates:
            result = round(amount / rates[from_curr] * rates[to_curr], 2)
    return render_template("currency.html", user=session.get("user"), result=result)

@app.route("/course/<path:name>")
def course(name):
    if "user" not in session: return redirect("/login")
    content_map = {
        "basics": "Learn the fundamentals of investing...",
        "stocks": "Understand how the stock market works...",
        "diversification": "Discover how spreading your investments minimizes risk...",
        "currency": "Learn about global currency and exchange rates..."
    }
    content = content_map.get(name.lower(), "Detailed content coming soon!")
    return render_template("course.html", user=session.get("user"), title=name.title(), content=content)

@app.route("/quiz/<path:name>", methods=["GET", "POST"])
def quiz(name):
    if "user" not in session: return redirect("/login")
    score = None
    if request.method == "POST":
        ans1 = request.form.get("q1")
        ans2 = request.form.get("q2")
        ans3 = request.form.get("q3")
        score = sum([ans1 == "b", ans2 == "b", ans3 == "b"])
    return render_template("quiz.html", user=session.get("user"), score=score)

# ---------------- RUN ----------------
if __name__ == "__main__":
    app.run(debug=True)
