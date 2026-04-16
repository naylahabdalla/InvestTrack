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

app = Flask(__name__)
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
    investments_raw = response.data
    
    total_invested = 0
    total_current_value = 0
    
    display_investments = []
    for inv in investments_raw:
        initial = float(inv.get("amount") or 0)
        status = inv.get("status", "Active")
        
        if status == "Sold":
            current_price = float(inv.get("sell_price") or initial)
        else:
            current_price = float(inv.get("current_value") or initial)
            
        total_invested += initial
        total_current_value += current_price
        
        gain = current_price - initial
        per = (gain / initial * 100) if initial > 0 else 0
        
        display_investments.append({
            "id": inv["id"],
            "asset_name": inv["asset_name"],
            "asset_type": inv["asset_type"],
            "amount": initial,
            "status": status,
            "current_price": current_price,
            "gain": gain,
            "percent": per
        })

    gain_total = total_current_value - total_invested
    percent_total = (gain_total / total_invested * 100) if total_invested > 0 else 0

    return render_template(
        "dashboard.html", user=session.get("user"),
        investments=display_investments,
        total=round(total_invested, 2),
        current=round(total_current_value, 2),
        gain=round(gain_total, 2),
        percent=round(percent_total, 2),
        count=len(display_investments),
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
        status = request.form.get("status", "Active")
        
        data = {
            "asset_name": name, 
            "asset_type": type_, 
            "amount": amount, 
            "username": session["user"],
            "status": status
        }
        
        if status == "Sold":
            data["sell_price"] = float(request.form.get("sell_price") or amount)
        else:
            data["current_value"] = float(request.form.get("current_value") or amount)

        supabase.table("investments").insert(data).execute()

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
    investments_raw = response.data
    
    total_invested = 0
    total_current_value = 0
    asset_totals = {}
    
    for inv in investments_raw:
        initial = float(inv.get("amount") or 0)
        status = inv.get("status", "Active")
        
        if status == "Sold":
            current_price = float(inv.get("sell_price") or initial)
        else:
            current_price = float(inv.get("current_value") or initial)
            
        total_invested += initial
        total_current_value += current_price
        
        name = inv["asset_name"]
        asset_totals[name] = asset_totals.get(name, 0) + current_price

    gain_total = total_current_value - total_invested
    percent_total = (gain_total / total_invested * 100) if total_invested > 0 else 0

    labels = list(asset_totals.keys())
    values = [round(v, 2) for v in asset_totals.values()]

    return render_template(
        "analytics.html",
        user=session.get("user"),
        total=round(total_invested, 2),
        current=round(total_current_value, 2),
        gain=round(gain_total, 2),
        percent=round(percent_total, 2),
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
            
        topic = request.form.get("topic", "General")
        raw_message = request.form["message"]
        message = f"[{topic}] {raw_message}"

        supabase.table("feedback").insert({"username": session["user"], "message": message}).execute()

        return redirect("/dashboard")

    return render_template("feedback.html", user=session.get("user"))

@app.route("/learn")
def learn():
    if "user" not in session:
        return redirect("/login")
        
    completed_courses = session.get('completed_courses', [])
    completed_quizzes = session.get('completed_quizzes', [])
    
    # Calculate progress for 4 courses and 2 quizzes
    course_progress = len(completed_courses)
    quiz_progress = len(completed_quizzes)
    
    skill_map = ["Beginner", "Novice", "Intermediate", "Advanced", "Expert"]
    skill_index = min((course_progress + quiz_progress), len(skill_map) - 1)
    
    stats = {
        "completed": course_progress + quiz_progress,
        "total_modules": 6,
        "skill": skill_map[skill_index],
        "courses_done": completed_courses,
        "quizzes_done": completed_quizzes
    }

    return render_template("learn.html", user=session.get("user"), stats=stats)

@app.route("/portfolio")
def portfolio():
    if "user" not in session: return redirect("/login")
    response = supabase.table("investments").select("*").eq("username", session["user"]).execute()
    investments_raw = response.data
    
    display_investments = []
    total_invested = 0
    
    for inv in investments_raw:
        initial = float(inv.get("amount") or 0)
        status = inv.get("status", "Active")
        
        if status == "Sold":
            current_price = float(inv.get("sell_price") or initial)
        else:
            current_price = float(inv.get("current_value") or initial)
            
        total_invested += initial
        gain = current_price - initial
        per = (gain / initial * 100) if initial > 0 else 0
        
        display_investments.append({
            "id": inv["id"],
            "asset_name": inv["asset_name"],
            "asset_type": inv["asset_type"],
            "amount": initial,
            "status": status,
            "current_price": current_price,
            "gain": gain,
            "percent": per
        })
        
    return render_template("portfolio.html", user=session.get("user"), investments=display_investments, total=round(total_invested, 2))

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
    converted_amount = None
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
            converted_amount = f"{result:,.2f}"
    return render_template("currency.html", user=session.get("user"), result=converted_amount)
    if "user" not in session:
        return redirect("/login")
        
    completed_courses = session.get('completed_courses', [])
    completed_quizzes = session.get('completed_quizzes', [])
    
    # Calculate progress for 4 courses and 2 quizzes
    course_progress = len(completed_courses)
    quiz_progress = len(completed_quizzes)
    
    skill_map = ["Beginner", "Novice", "Intermediate", "Advanced", "Expert"]
    skill_index = min((course_progress + quiz_progress), len(skill_map) - 1)
    
    stats = {
        "completed": course_progress + quiz_progress,
        "total_modules": 6,
        "skill": skill_map[skill_index],
        "courses_done": completed_courses,
        "quizzes_done": completed_quizzes
    }

    return render_template("learn.html", user=session.get("user"), stats=stats)

@app.route("/course/<path:name>")
def course(name):
    if "user" not in session: return redirect("/login")
    
    completed_courses = session.get('completed_courses', [])
    if name not in completed_courses:
        completed_courses.append(name.lower())
        session['completed_courses'] = completed_courses
        session.modified = True

    content_map = {
        "basics": {
            "title": "Investment Basics",
            "desc": "Before buying any asset, you must understand the rules of the game.",
            "modules": [
                {"name": "What is an Investment?", "body": "An asset acquired with the goal of generating income or appreciation."},
                {"name": "Risk vs Reward", "body": "Higher potential returns usually come with higher risk. Understanding your risk tolerance is key."},
                {"name": "Compound Interest", "body": "The 8th wonder of the world. Earning interest on your interest over time."}
            ]
        },
        "stocks": {
            "title": "Stock Market",
            "desc": "Own a piece of your favorite companies.",
            "modules": [
                {"name": "What is a Stock?", "body": "A share representing a fraction of ownership in a corporation."},
                {"name": "How to Buy", "body": "You purchase stocks through brokerage accounts. Price fluctuates based on supply and demand."},
                {"name": "Dividends", "body": "A distribution of profits by a corporation to its shareholders."}
            ]
        },
        "diversification": {
            "title": "Diversification",
            "desc": "Don't put all your eggs in one basket.",
            "modules": [
                {"name": "Asset Allocation", "body": "Dividing your portfolio among different asset categories, such as stocks, bonds, and cash."},
                {"name": "Why it Works", "body": "Different assets react differently to market events, reducing overall drag on your portfolio."},
                {"name": "Mutual Funds & ETFs", "body": "Baskets of investments that offer instant diversification for new investors."}
            ]
        },
        "currency": {
            "title": "Currency & Exchange",
            "desc": "The global market that never sleeps.",
            "modules": [
                {"name": "Forex Market", "body": "The Foreign Exchange market where global currencies are traded."},
                {"name": "Exchange Rates", "body": "The value of one currency for the purpose of conversion to another (e.g. EUR/USD)."},
                {"name": "Crypto", "body": "Digital or virtual currency secured by cryptography, operating independently of a central bank."}
            ]
        }
    }
    
    course_data = content_map.get(name.lower(), {
        "title": name.title(), "desc": "Detailed content coming soon!", "modules": []
    })
    return render_template("course.html", user=session.get("user"), course=course_data)

@app.route("/quiz/<path:name>", methods=["GET", "POST"])
def quiz(name):
    if "user" not in session: return redirect("/login")
    
    score = None
    passed = False
    
    quizzes = {
        "basics": {
            "title": "Investment Fundamentals Test",
            "questions": [
                {"q": "What is compound interest?", "opts": {"a": "Interest on standard loans", "b": "Earning interest on interest", "c": "A fixed yearly rate"}, "ans": "b"},
                {"q": "What is the primary relationship between risk and reward?", "opts": {"a": "Higher risk usually implies higher potential reward", "b": "Higher risk means lower potential reward", "c": "There is no relationship"}, "ans": "a"},
                {"q": "Which of these is generally considered the safest investment?", "opts": {"a": "Cryptocurrency", "b": "Government Bonds", "c": "Startup Stocks"}, "ans": "b"}
            ]
        },
        "stocks": {
            "title": "Stock Market Test",
            "questions": [
                {"q": "What does buying a stock signify?", "opts": {"a": "Loaning money to a company", "b": "Partial ownership of a company", "c": "A guaranteed yearly payout"}, "ans": "b"},
                {"q": "What is a dividend?", "opts": {"a": "A company profit shared with stockholders", "b": "A penalty fee for selling early", "c": "A type of corporate bond"}, "ans": "a"},
                {"q": "What does ETF stand for?", "opts": {"a": "Estimated Trading Fund", "b": "Exchange-Traded Fund", "c": "Equity Trust Federation"}, "ans": "b"}
            ]
        }
    }
    
    quiz_data = quizzes.get(name.lower(), quizzes["basics"])
    
    if request.method == "POST":
        score = 0
        for i, q in enumerate(quiz_data["questions"]):
            user_ans = request.form.get(f"q{i}")
            if user_ans == q["ans"]:
                score += 1
                
        if score == len(quiz_data["questions"]):
            passed = True
            completed_quizzes = session.get('completed_quizzes', [])
            if name.lower() not in completed_quizzes:
                completed_quizzes.append(name.lower())
                session['completed_quizzes'] = completed_quizzes
                session.modified = True
                
    return render_template("quiz.html", user=session.get("user"), quiz=quiz_data, score=score, passed=passed, total=len(quiz_data["questions"]))

# ---------------- RUN ----------------
if __name__ == "__main__":
    app.run(debug=True)