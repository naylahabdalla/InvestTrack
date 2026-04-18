from flask import Flask, render_template, request, redirect, url_for, session
from supabase import create_client, Client
import requests
from werkzeug.security import generate_password_hash, check_password_hash
import re
from functools import wraps
import os
import pyotp
import stripe
from datetime import datetime, timedelta

url: str = "https://livxzkknhrqusxkyrieq.supabase.co"
key: str = "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJpc3MiOiJzdXBhYmFzZSIsInJlZiI6Imxpdnh6a2tuaHJxdXN4a3lyaWVxIiwicm9sZSI6ImFub24iLCJpYXQiOjE3NzQ1MDk0NjUsImV4cCI6MjA5MDA4NTQ2NX0.b1WV6RtX3suBkTquZiY-4NS8p0QOzViGimAJkrqMr4U"
supabase: Client = create_client(url, key)

app = Flask(__name__)
app.secret_key = "investtrack_secret"

# ✅ Configure template and static folders for Vercel & Local
base_dir = os.path.dirname(os.path.abspath(__file__))
template_dir = os.path.join(base_dir, 'templates')
static_dir = os.path.join(base_dir, 'static')

# If running from api/index.py, the folders are one level up
if not os.path.exists(template_dir):
    template_dir = os.path.join(os.path.dirname(base_dir), 'templates')
if not os.path.exists(static_dir):
    static_dir = os.path.join(os.path.dirname(base_dir), 'static')

app.template_folder = template_dir
app.static_folder = static_dir

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

# ---------------- HELPER: LIVE PRICES ----------------
def fetch_live_prices(investments_raw, include_overview=False):
    active_tickers = set(
        inv.get("ticker").strip().upper() 
        for inv in investments_raw 
        if inv.get("status") != "Sold" and inv.get("ticker")
    )
    if include_overview:
        active_tickers.update({"AAPL", "TSLA", "BTC-USD", "ETH-USD"})

    live_prices = {}
    headers = {'User-Agent': 'Mozilla/5.0'}
    for t in active_tickers:
        try:
            url = f"https://query1.finance.yahoo.com/v8/finance/chart/{t}"
            res = requests.get(url, headers=headers, timeout=5)
            data = res.json()
            price = data['chart']['result'][0]['meta']['regularMarketPrice']
            if price and price > 0:
                live_prices[t] = float(price)
        except Exception:
            pass
    return live_prices



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
        consent = request.form.get("consent")

        if not consent:
            error = "You must agree to the terms to sign up"
        elif password != confirm:
            error = "Passwords do not match"
        elif not is_strong_password(password):
            error = "Password requires 8+ chars, letter, number, and special character"
        else:
            hashed = generate_password_hash(password)

            try:
                # Store consent_given=True and timestamp
                # Set trial_end for 30 days from now
                # and subscription_tier = 'free' (or 'trialing')
                trial_end_dt = datetime.now() + timedelta(days=30)
                
                supabase.table("users").insert({
                    "username": username, 
                    "current_hash": hashed,
                    "consent_given": True,
                    "consent_timestamp": "now()",
                    "trial_end": trial_end_dt.isoformat(),
                    "subscription_tier": "free"
                }).execute()

                # Don't log in immediately; redirect to 2FA SETUP
                session["setup_user"] = username
                return redirect("/setup-2fa")

            except Exception as e:
                err_msg = str(e).lower()
                if "duplicate key value" in err_msg or "unique violation" in err_msg or "23505" in err_msg or "already exists" in err_msg:
                    error = "Username already exists"
                else:
                    error = "An error occurred: " + str(e)


    return render_template("signup.html", error=error)

# ---------------- 2FA SETUP ----------------
@app.route("/setup-2fa", methods=["GET", "POST"])
def setup_2fa():
    if "setup_user" not in session:
        return redirect("/signup")
    
    username = session["setup_user"]
    
    # Check if they already have a secret in the DB (don't overwrite)
    res = supabase.table("users").select("two_factor_secret").eq("username", username).execute()
    existing_secret = res.data[0].get("two_factor_secret") if res.data else None
    
    if existing_secret:
        # Already set up, move to dashboard
        session["user"] = username
        session.pop("setup_user", None)
        return redirect("/dashboard")

    # Generate a temporary secret if not in session
    if "temp_2fa_secret" not in session:
        session["temp_2fa_secret"] = pyotp.random_base32()
    
    secret = session["temp_2fa_secret"]
    totp = pyotp.TOTP(secret)
    provisioning_uri = totp.provisioning_uri(name=username, issuer_name="InvestTrack")
    
    error = None
    if request.method == "POST":
        token = request.form.get("token")
        if totp.verify(token):
            # SAVE TO DB
            supabase.table("users").update({"two_factor_secret": secret}).eq("username", username).execute()
            
            # LOGIN SUCCESS
            session["user"] = username
            session.pop("setup_user", None)
            session.pop("temp_2fa_secret", None)
            return redirect("/dashboard")
        else:
            error = "Invalid 2FA code. Please try again."

    return render_template("setup_2fa.html", secret=secret, uri=provisioning_uri, error=error)

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
            # Check for 2FA
            secret = user.get("two_factor_secret")
            if secret:
                # Store pending user in session
                session["pending_2fa_user"] = username
                return redirect("/verify-2fa")
            else:
                session["user"] = username
                return redirect("/dashboard")
        else:
            error = "Invalid username or password"

    return render_template("login.html", error=error)

# ---------------- 2FA VERIFY ----------------
@app.route("/verify-2fa", methods=["GET", "POST"])
def verify_2fa():
    if "pending_2fa_user" not in session:
        return redirect("/login")
    
    username = session["pending_2fa_user"]
    
    # Get secret from DB
    res = supabase.table("users").select("two_factor_secret").eq("username", username).execute()
    secret = res.data[0].get("two_factor_secret") if res.data else None
    
    if not secret:
        # No 2FA setup, just log in
        session["user"] = username
        session.pop("pending_2fa_user", None)
        return redirect("/dashboard")
    
    error = None
    if request.method == "POST":
        token = request.form.get("token")
        totp = pyotp.TOTP(secret)
        if totp.verify(token):
            session["user"] = username
            session.pop("pending_2fa_user", None)
            return redirect("/dashboard")
        else:
            error = "Invalid 2FA code"

    return render_template("verify_2fa.html", error=error)

# ---------------- TERMS & PRIVACY ----------------
@app.route("/terms")
def terms():
    return render_template("terms.html", user=session.get("user"))

@app.route("/privacy")
def privacy():
    return render_template("privacy.html", user=session.get("user"))

# ---------------- SUBSCRIPTION ----------------
@app.route("/upgrade")
def upgrade():
    if "user" not in session:
        return redirect("/login")
    
    # Check current tier
    response = supabase.table("users").select("subscription_tier", "trial_end").eq("username", session["user"]).execute()
    user_data = response.data[0] if response.data else {}
    
    return render_template("upgrade.html", user_data=user_data, user=session.get("user"))

@app.route("/create-checkout-session", methods=["POST"])
def create_checkout_session():
    if "user" not in session:
        return jsonify({"error": "Unauthorized"}), 401

    tier = request.form.get("tier")
    price_map = {
        "basic": 599,  # $5.99
        "ultra": 1499  # $14.99
    }
    
    if tier not in price_map:
        return jsonify({"error": "Invalid tier"}), 400

    # Simulation mode: Just mark as premium for now since we don't have real Stripe keys
    # In a real app, you would redirect to Stripe here.
    supabase.table("users").update({"subscription_tier": tier}).eq("username", session["user"]).execute()
    
    return redirect("/dashboard")

# ---------------- DASHBOARD ----------------
@app.route("/dashboard")
def dashboard():
    if "user" not in session:
        return redirect("/login")

    response = supabase.table("investments").select("*").eq("username", session["user"]).execute()
    investments_raw = response.data
    
    live_prices = fetch_live_prices(investments_raw, include_overview=True)
    
    total_invested = 0
    total_current_value = 0
    
    display_investments = []
    for inv in investments_raw:
        initial = float(inv.get("amount") or 0)
        status = inv.get("status", "Active")
        
        if status == "Sold":
            current_price = float(inv.get("sell_price") or initial)
        else:
            ticker = inv.get("ticker")
            quantity = inv.get("quantity")
            if ticker and quantity is not None and ticker.strip().upper() in live_prices:
                current_price = live_prices[ticker.strip().upper()] * float(quantity)
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
            "percent": per,
            "result_type": "Gain" if gain > 0 else ("Loss" if gain < 0 else "Break-even")
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
        apple=round(live_prices.get("AAPL", 150.0), 2),
        tesla=round(live_prices.get("TSLA", 200.0), 2),
        btc=round(live_prices.get("BTC-USD", 40000.0), 2),
        eth=round(live_prices.get("ETH-USD", 2500.0), 2)
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
        ticker = request.form.get("ticker", "").strip()
        quantity_str = request.form.get("quantity", "").strip()
        quantity = float(quantity_str) if quantity_str else None
        
        data = {
            "asset_name": name, 
            "asset_type": type_, 
            "amount": amount, 
            "username": session["user"],
            "status": status,
            "ticker": ticker if ticker else None,
            "quantity": quantity
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

def generate_recommendations(investments_raw, live_prices):
    recs = []
    for inv in investments_raw:
        initial = float(inv.get("amount") or 0)
        status = inv.get("status", "Active")
        ticker = inv.get("ticker")
        quantity = inv.get("quantity")
        asset_type = (inv.get("asset_type") or "Stock").lower()
        
        if status == "Sold":
            current_price = float(inv.get("sell_price") or initial)
            gain = current_price - initial
            per = (gain / initial * 100) if initial > 0 else 0
            recs.append({
                "asset_name": inv["asset_name"],
                "gain_loss": per,
                "risk": "Closed",
                "action": "Review Result",
                "color": "secondary",
                "text": f"This investment is closed with a {per:.1f}% {'gain' if per >= 0 else 'loss'}."
            })
            continue

        if ticker and quantity is not None and ticker.strip().upper() in live_prices:
            current_price = live_prices[ticker.strip().upper()] * float(quantity)
        else:
            current_price = float(inv.get("current_value") or initial)
            
        gain = current_price - initial
        per = (gain / initial * 100) if initial > 0 else 0
        
        # Risk Logic
        if per < -15:
            risk = "High Risk"
            action = "Review Entry"
            color = "danger"
            text = "Strongly monitor. Significant drawdown detected. Decide if the long-term thesis still holds."
        elif per < 0:
            risk = "Moderate Risk"
            action = "Hold & Watch"
            color = "warning"
            text = "Minor loss. Markets are currently volatile; patience might be your best asset here."
        elif per > 25:
            risk = "Low Risk"
            action = "Secure Profits"
            color = "success"
            text = "Exceptional gains! Good time to take initial investment out and let the 'house money' run."
        else:
            risk = "Low Risk"
            action = "Hold"
            color = "info"
            text = "Healthy position. Performance is within normal expected parameters."

        # Asset Type Modifiers
        if "crypto" in asset_type:
            if per < 0:
                risk = "Extreme Risk"
                color = "danger"
            else:
                risk = "High Volatility"
                color = "warning"

        recs.append({
            "asset_name": inv["asset_name"],
            "ticker": ticker,
            "gain_loss": per,
            "risk": risk,
            "action": action,
            "color": color,
            "text": text
        })
    return recs

@app.route("/analytics")
def analytics():
    if "user" not in session:
        return redirect("/login")

    # Fetch User Tier
    user_resp = supabase.table("users").select("subscription_tier").eq("username", session["user"]).execute()
    tier = user_resp.data[0].get("subscription_tier", "free") if user_resp.data else "free"
    is_ultra = (tier == 'ultra')

    response = supabase.table("investments").select("*").eq("username", session["user"]).execute()
    investments_raw = response.data
    
    live_prices = fetch_live_prices(investments_raw, include_overview=False)
    
    total_invested = 0
    total_current_value = 0
    asset_totals = {}
    
    for inv in investments_raw:
        initial = float(inv.get("amount") or 0)
        status = inv.get("status", "Active")
        
        if status == "Sold":
            current_price = float(inv.get("sell_price") or initial)
        else:
            ticker = inv.get("ticker")
            quantity = inv.get("quantity")
            if ticker and quantity is not None and ticker.strip().upper() in live_prices:
                current_price = live_prices[ticker.strip().upper()] * float(quantity)
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

    # Generate Individual Recommendations for All Users
    individual_recs = generate_recommendations(investments_raw, live_prices)

    return render_template(
        "analytics.html",
        user=session.get("user"),
        total=round(total_invested, 2),
        current=round(total_current_value, 2),
        gain=round(gain_total, 2),
        percent=round(percent_total, 2),
        labels=labels,
        values=values,
        is_ultra=is_ultra,
        recommendations=individual_recs
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
    
    live_prices = fetch_live_prices(investments_raw, include_overview=False)
    
    display_investments = []
    total_invested = 0
    
    for inv in investments_raw:
        initial = float(inv.get("amount") or 0)
        status = inv.get("status", "Active")
        
        if status == "Sold":
            current_price = float(inv.get("sell_price") or initial)
        else:
            ticker = inv.get("ticker")
            quantity = inv.get("quantity")
            if ticker and quantity is not None and ticker.strip().upper() in live_prices:
                current_price = live_prices[ticker.strip().upper()] * float(quantity)
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
            "percent": per,
            "result_type": "Gain" if gain > 0 else ("Loss" if gain < 0 else "Break-even")
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
    
    skill_map = ["Novice", "Student", "Apprentice", "Practitioner", "Analyst", "Strategist", "Elite", "Expert", "Master", "Grandmaster", "Legend"]
    skill_index = min((course_progress + quiz_progress), len(skill_map) - 1)
    
    stats = {
        "completed": course_progress + quiz_progress,
        "total_modules": 11,
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
        },
        "crypto": {
            "title": "Crypto & Web3",
            "desc": "The future of decentralized finance and digital ownership.",
            "modules": [
                {"name": "Blockchain Basics", "body": "A distributed, immutable ledger that records transactions across a network of computers."},
                {"name": "Bitcoin vs Ethereum", "body": "Bitcoin as digital gold vs. Ethereum as a programmable platform for smart contracts."},
                {"name": "Wallets & Security", "body": "Understanding hot (online) and cold (offline) storage to protect your digital assets."}
            ]
        },
        "realestate": {
            "title": "Real Estate & REITs",
            "desc": "Building wealth through physical and digital property.",
            "modules": [
                {"name": "REITs Explained", "body": "Real Estate Investment Trusts allow you to invest in large-scale properties without buying them directly."},
                {"name": "Rental Yield", "body": "The annual rental income from a property divided by its total value, expressed as a percentage."},
                {"name": "Mortgage & Leverage", "body": "Using borrowed capital to increase the potential return of an investment (and its risk)."}
            ]
        },
        "esg": {
            "title": "Sustainable Finance (ESG)",
            "desc": "Investing for profit and purpose.",
            "modules": [
                {"name": "What is ESG?", "body": "Environmental, Social, and Governance criteria used to measure the sustainability of a company."},
                {"name": "Green Bonds", "body": "Fixed-income instruments designed specifically to support climate-related or environmental projects."},
                {"name": "Ethical Investing", "body": "Selecting investments based on ethical principles and social values alongside financial performance."}
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
        },
        "diversification": {
            "title": "Diversification Masterclass",
            "questions": [
                {"q": "What is asset correlation?", "opts": {"a": "When assets move in the same direction", "b": "When assets move in opposite directions", "c": "The speed of market trading"}, "ans": "a"},
                {"q": "Which asset 'typically' moves opposite to stocks during a crash?", "opts": {"a": "Cryptocurrency", "b": "Real Estate", "c": "Gold/Bonds"}, "ans": "c"},
                {"q": "What is the primary goal of diversification?", "opts": {"a": "To maximize returns", "b": "To reduce overall portfolio risk", "c": "To pay fewer taxes"}, "ans": "b"}
            ]
        },
        "global": {
            "title": "Global Markets Challenge",
            "questions": [
                {"q": "What is the largest financial market in the world?", "opts": {"a": "The Stock Market", "b": "The Forex Market", "c": "The Bond Market"}, "ans": "b"},
                {"q": "What happens if a currency's value increases?", "opts": {"a": "It becomes 'stronger' relative to others", "b": "It becomes 'weaker' relative to others", "c": "Nothing changes"}, "ans": "a"},
                {"q": "What is a major risk of international investing?", "opts": {"a": "Weather volatility", "b": "Currency exchange rate risk", "c": "Too much profit"}, "ans": "b"}
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