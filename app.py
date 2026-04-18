from flask import Flask, render_template, request, redirect, url_for, session
from supabase import create_client, Client
import yfinance as yf
import requests
from werkzeug.security import generate_password_hash, check_password_hash
import re
from functools import wraps
import os

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
    for t in active_tickers:
        try:
            price = yf.Ticker(t).fast_info['lastPrice']
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
    
    # Calculate progress for 7 courses and 7 quizzes
    course_progress = len(completed_courses)
    quiz_progress = len(completed_quizzes)
    
    skill_map = ["Novice", "Student", "Apprentice", "Practitioner", "Analyst", "Strategist", "Elite", "Expert", "Master", "Grandmaster", "Legend", "Visionary", "Sage", "Oracle", "Grandmaster Elite"]
    skill_index = min((course_progress + quiz_progress), len(skill_map) - 1)
    
    stats = {
        "completed": course_progress + quiz_progress,
        "total_modules": 14,
        "skill": skill_map[skill_index],
        "courses_done": completed_courses,
        "quizzes_done": completed_quizzes
    }

    return render_template("learn.html", user=session.get("user"), stats=stats)

@app.route("/course/<path:name>", methods=["GET", "POST"])
def course(name):
    if "user" not in session: return redirect("/login")
    
    if request.method == "POST":
        completed_courses = session.get('completed_courses', [])
        if name.lower() not in completed_courses:
            completed_courses.append(name.lower())
            session['completed_courses'] = completed_courses
            session.modified = True
        return redirect("/learn")

    content_map = {
        "basics": {
            "title": "Investment Basics",
            "desc": "Before buying any asset, you must understand the rules of the game.",
            "modules": [
                {"name": "What is an Investment?", "body": "An asset acquired with the goal of generating income or appreciation over time. It requires committing capital today for a future benefit."},
                {"name": "Risk vs Reward", "body": "The fundamental tradeoff: higher potential returns typically require taking on higher risk. Understanding your risk tolerance is the first step to success."},
                {"name": "Compound Interest", "body": "Known as the 8th wonder of the world. It is the process where the value of an investment increases because the earnings on an investment, both principal and interest, earn interest as time passes."},
                {"name": "Time Value of Money", "body": "A dollar today is worth more than a dollar tomorrow because of its potential earning capacity. This core principle underpins all of finance."},
                {"name": "Inflation & Purchasing Power", "body": "The rate at which the general level of prices for goods and services is rising. If your investments don't beat inflation, you are technically losing money."},
                {"name": "Asset Classes", "body": "Broad categories of investments, such as stocks, bonds, real estate, and cash. Each has different risk and return profiles."},
                {"name": "The Power of Patience", "body": "Long-term investing allows you to weather short-term market volatility. Time in the market is often more important than timing the market."},
                {"name": "Financial Goals", "body": "Setting SMART (Specific, Measurable, Achievable, Relevant, Time-bound) goals is essential for choosing the right investment strategy."},
                {"name": "Emergency Funds", "body": "Before investing, ensure you have 3-6 months of expenses saved. This prevents you from being forced to sell investments during a downturn."},
                {"name": "Net Worth Calculation", "body": "Total Assets minus Total Liabilities. Tracking this over time is the ultimate scorecard for your financial health."}
            ]
        },
        "stocks": {
            "title": "Stock Market",
            "desc": "Own a piece of your favorite companies.",
            "modules": [
                {"name": "What is a Stock?", "body": "A security that represents ownership of a fraction of a corporation. This entitles the owner to a proportion of the corporation's assets and profits."},
                {"name": "Common vs Preferred Stock", "body": "Common stock offers voting rights and potential for higher growth; preferred stock acts more like a bond with fixed dividends and no voting rights."},
                {"name": "Stock Exchanges", "body": "Places where stocks are bought and sold, like the NYSE or NASDAQ. They ensure fair and orderly trading."},
                {"name": "Market Capitalization", "body": "The total value of a company's shares. Calculated as (Share Price) x (Total Shares Outstanding). Categorized as Small, Mid, or Large cap."},
                {"name": "Dividends", "body": "A portion of a company's earnings paid to shareholders. A sign of a mature, profitable company."},
                {"name": "P/E Ratio", "body": "The Price-to-Earnings ratio. A valuation metric comparing a company's current share price to its per-share earnings."},
                {"name": "Bull vs Bear Markets", "body": "A 'Bull' market is characterized by rising prices and optimism. A 'Bear' market is characterized by falling prices and pessimism."},
                {"name": "IPO (Initial Public Offering)", "body": "The process where a private company first sells shares to the public to raise capital."},
                {"name": "Fundamental Analysis", "body": "Evaluating a company's health by looking at financial statements, management, and competitive position."},
                {"name": "Growth vs Value Investing", "body": "Growth investors seek companies with rapid earnings potential; Value investors look for 'bargains' currently trading below their intrinsic value."}
            ]
        },
        "diversification": {
            "title": "Diversification",
            "desc": "Don't put all your eggs in one basket.",
            "modules": [
                {"name": "Asset Allocation", "body": "The strategy of balancing risk and reward by apportioning a portfolio's assets according to an individual's goals and risk tolerance."},
                {"name": "Asset Correlation", "body": "A measurement of how two assets move in relation to each other. Diversification works best with negatively correlated assets."},
                {"name": "Portfolio Rebalancing", "body": "The process of realigning the weightings of a portfolio of assets. Periodically buying or selling assets to maintain your original desired level of risk."},
                {"name": "Mutual Funds", "body": "A professionaly managed investment fund that pools money from many investors to purchase securities."},
                {"name": "ETFs (Exchange Traded Funds)", "body": "Similar to mutual funds but traded on stock exchanges like individual stocks. Known for low costs and tax efficiency."},
                {"name": "Modern Portfolio Theory", "body": "A mathematical framework for assembling a portfolio of assets such that the expected return is maximized for a given level of risk."},
                {"name": "Index Funds", "body": "A type of mutual fund or ETF with a portfolio constructed to match or track the components of a financial market index, like the S&P 500."},
                {"name": "Sector Diversification", "body": "Investing across different industries (Tech, Healthcare, Energy) to ensure one industry's downturn doesn't tank your entire portfolio."},
                {"name": "Geographic Diversification", "body": "Investing in international markets to reduce dependence on a single country's economy."},
                {"name": "The Efficiency Frontier", "body": "The set of optimal portfolios that offer the highest expected return for a defined level of risk."}
            ]
        },
        "currency": {
            "title": "Currency & Exchange",
            "desc": "The global market that never sleeps.",
            "modules": [
                {"name": "Forex Market", "body": "The Foreign Exchange market, where global currencies are traded. It is the largest and most liquid financial market in the world."},
                {"name": "Exchange Rates", "body": "The price of one country's currency in terms of another currency (e.g., EUR/USD). Influenced by interest rates and economic stability."},
                {"name": "Currency Pairs", "body": "In Forex, you always trade pairs (Base/Quote). Major pairs include USD, EUR, JPY, GBP, and CHF."},
                {"name": "Central Banks", "body": "Institutions like the Fed or ECB that manage a country's currency, money supply, and interest rates to control inflation."},
                {"name": "Interest Rate Parity", "body": "A theory suggesting the difference in interest rates between two countries is equal to the difference between the forward and spot exchange rates."},
                {"name": "Hedging Currency Risk", "body": "Using financial instruments like forwards or options to protect against unfavorable moves in exchange rates."},
                {"name": "Quantitative Easing", "body": "A monetary policy where a central bank buys government securities to increase money supply and encourage lending and investment."},
                {"name": "Fiat vs Commodity Money", "body": "Fiat money has no intrinsic value but is backed by a government. Commodity money (like gold coins) has value from the material it's made of."},
                {"name": "Balance of Trade", "body": "The difference between the value of a country's exports and imports. A surplus can strengthen a currency."},
                {"name": "Geopolitical Impact", "body": "Political instability, elections, and international conflicts can cause rapid volatility in currency values."}
            ]
        },
        "crypto": {
            "title": "Crypto & Web3",
            "desc": "The future of decentralized finance and digital ownership.",
            "modules": [
                {"name": "Blockchain Basics", "body": "A decentralized, distributed ledger technology that records transactions across many computers so that the record cannot be altered retroactively."},
                {"name": "Bitcoin & Digital Gold", "body": "The first cryptocurrency, designed as a peer-to-peer electronic cash system with a capped supply of 21 million."},
                {"name": "Ethereum & Smart Contracts", "body": "A programmable blockchain that allows developers to build decentralized applications (dApps) using self-executing contracts."},
                {"name": "Wallets & Private Keys", "body": "Tools to manage your crypto. Your private key is like a master password; if you lose it, you lose access to your funds."},
                {"name": "Proof of Work vs Stake", "body": "The two main consensus mechanisms. PoW uses high computing power (mining); PoS uses validators who 'stake' their own coins."},
                {"name": "DeFi (Decentralized Finance)", "body": "Financial services (lending, borrowing, trading) built on blockchains, removing traditional intermediaries like banks."},
                {"name": "NFTs & Digital Assets", "body": "Non-Fungible Tokens represent unique ownership of digital or physical items on the blockchain."},
                {"name": "Gas Fees", "body": "The transaction fees paid to miners or validators to process transactions on networks like Ethereum."},
                {"name": "Stablecoins", "body": "Cryptocurrencies designed to have a stable value, usually pegged 1:1 to a fiat currency like the US Dollar."},
                {"name": "Layer 2 Solutions", "body": "Secondary frameworks built on top of an existing blockchain to improve scalability and reduce transaction costs."}
            ]
        },
        "realestate": {
            "title": "Real Estate & REITs",
            "desc": "Building wealth through physical and digital property.",
            "modules": [
                {"name": "REITs Explained", "body": "Real Estate Investment Trusts are companies that own, operate, or finance income-generating real estate. They provide a way for individuals to invest in large-scale properties."},
                {"name": "Rental Yield", "body": "A measure of the annual return an investor can expect from a property. Calculated as (Annual Rent / Property Value) x 100."},
                {"name": "Mortgage & Leverage", "body": "Using borrowed capital (a mortgage) to purchase property. This can amplify your returns but also increases your risk."},
                {"name": "Appreciation", "body": "The increase in the value of a property over time, influenced by location, demand, and inflation."},
                {"name": "Cap Rate (Capitalization Rate)", "body": "The ratio of Net Operating Income to property asset value. Used to estimate the potential return on an investment property."},
                {"name": "Residential vs Commercial", "body": "Residential includes houses and apartments; Commercial involves offices, retail, and industrial spaces with different lease structures."},
                {"name": "Property Management", "body": "The daily oversight of real estate by a third-party, including rent collection, maintenance, and tenant relations."},
                {"name": "The 1% Rule", "body": "A rule of thumb suggesting a property should rent for at least 1% of its purchase price to be potentially profitable."},
                {"name": "Equity Build-up", "body": "The process of increasing your ownership stake in a property as you pay down the mortgage principal."},
                {"name": "Real Estate Cycles", "body": "The four phases: Recovery, Expansion, Hypersupply, and Recession. Timing your buy/sell within these cycles is key."}
            ]
        },
        "esg": {
            "title": "Sustainable Finance (ESG)",
            "desc": "Investing for profit and purpose.",
            "modules": [
                {"name": "What is ESG?", "body": "Environmental, Social, and Governance criteria used by investors to evaluate a company's sustainability and ethical impact."},
                {"name": "Environmental (E)", "body": "Focuses on climate change, carbon emissions, waste management, and natural resource conservation."},
                {"name": "Social (S)", "body": "Evaluates a company's relationship with employees, suppliers, customers, and communities (e.g., labor standards, diversity)."},
                {"name": "Governance (G)", "body": "Assesses a company's leadership, audits, internal controls, shareholder rights, and executive pay."},
                {"name": "Green Bonds", "body": "Fixed-income instruments specifically earmarked to raise money for climate and environmental projects."},
                {"name": "Impact Investing", "body": "Investments made with the intention to generate positive, measurable social and environmental impact alongside a financial return."},
                {"name": "ESG Integration", "body": "The explicit and systematic inclusion of ESG factors into financial analysis and investment decisions."},
                {"name": "The UN SDGs", "body": "The United Nations Sustainable Development Goals are 17 global goals designed to be a 'blueprint to achieve a better and more sustainable future for all.'"},
                {"name": "Greenwashing", "body": "The practice of making misleading or unsubstantiated claims about the environmental benefits of a product, service, or company."},
                {"name": "Shareholder Activism", "body": "Investors using their ownership stake in a corporation to influence its behavior and ESG policies."}
            ]
        }
    }
    
    course_data = content_map.get(name.lower(), {
        "title": name.title(), "desc": "Detailed content coming soon!", "modules": []
    })
    return render_template("course.html", user=session.get("user"), course=course_data, completed_courses=session.get('completed_courses', []))

@app.route("/quiz/<path:name>", methods=["GET", "POST"])
def quiz(name):
    if "user" not in session: return redirect("/login")
    
    score = None
    passed = False
    total = None
    
    quizzes = {
        "basics": {
            "title": "Investment Fundamentals Test",
            "questions": [
                {"q": "What is compound interest?", "opts": {"a": "Interest on standard loans", "b": "Earning interest on interest", "c": "A fixed yearly rate"}, "ans": "b"},
                {"q": "What is the primary relationship between risk and reward?", "opts": {"a": "Higher risk usually implies higher potential reward", "b": "Higher risk means lower potential reward", "c": "There is no relationship"}, "ans": "a"},
                {"q": "Which of these is generally considered the safest investment?", "opts": {"a": "Cryptocurrency", "b": "Government Bonds", "c": "Startup Stocks"}, "ans": "b"},
                {"q": "What does the 'Time Value of Money' imply?", "opts": {"a": "Money today is worth more than money tomorrow", "b": "Money tomorrow is worth more than today", "c": "Time has no value in finance"}, "ans": "a"},
                {"q": "What is inflation?", "opts": {"a": "Decrease in price levels", "b": "Increase in price levels", "c": "Stable prices"}, "ans": "b"},
                {"q": "What is a major component of an emergency fund?", "opts": {"a": "Stock options", "b": "3-6 months of expenses in cash", "c": "Cryptocurrency"}, "ans": "b"},
                {"q": "Which is an example of an asset class?", "opts": {"a": "A car you drive", "b": "Real Estate", "c": "A dinner out"}, "ans": "b"},
                {"q": "How do you calculate Net Worth?", "opts": {"a": "Income minus Expenses", "b": "Assets minus Liabilities", "c": "Total Savings"}, "ans": "b"},
                {"q": "What does 'S' stand for in SMART goals?", "opts": {"a": "Simple", "b": "Specific", "c": "Strategic"}, "ans": "b"},
                {"q": "What is the '8th wonder of the world' according to Einstein?", "opts": {"a": "The Stock Market", "b": "Compound Interest", "c": "Real Estate"}, "ans": "b"}
            ]
        },
        "stocks": {
            "title": "Stock Market Test",
            "questions": [
                {"q": "What does buying a stock signify?", "opts": {"a": "Loaning money to a company", "b": "Partial ownership of a company", "c": "A guaranteed yearly payout"}, "ans": "b"},
                {"q": "What is a dividend?", "opts": {"a": "A company profit shared with stockholders", "b": "A penalty fee for selling early", "c": "A type of corporate bond"}, "ans": "a"},
                {"q": "What does ETF stand for?", "opts": {"a": "Estimated Trading Fund", "b": "Exchange-Traded Fund", "c": "Equity Trust Federation"}, "ans": "b"},
                {"q": "What is the P/E ratio?", "opts": {"a": "Price-to-Equity", "b": "Price-to-Earnings", "c": "Profit-to-Earnings"}, "ans": "b"},
                {"q": "A 'Bear' market means prices are:", "opts": {"a": "Rising", "b": "Falling", "c": "Flat"}, "ans": "b"},
                {"q": "What occurs during an IPO?", "opts": {"a": "A company goes private", "b": "A company goes public", "c": "A company goes bankrupt"}, "ans": "b"},
                {"q": "Fundamental analysis looks at:", "opts": {"a": "Chart patterns", "b": "Financial health & management", "c": "Social media trends"}, "ans": "b"},
                {"q": "A Large-Cap company has a market value of:", "opts": {"a": "Under $2B", "b": "Over $10B", "c": "Exactly $1B"}, "ans": "b"},
                {"q": "Preferred stockholders usually don't have:", "opts": {"a": "Dividends", "b": "Voting rights", "c": "Asset claims"}, "ans": "b"},
                {"q": "Value investors look for stocks that are:", "opts": {"a": "Overpriced", "b": "Underpriced/Undervalued", "c": "Most popular"}, "ans": "b"}
            ]
        },
        "diversification": {
            "title": "Diversification Masterclass",
            "questions": [
                {"q": "What is asset correlation?", "opts": {"a": "When assets move in the same direction", "b": "When assets move in opposite directions", "c": "The speed of market trading"}, "ans": "a"},
                {"q": "Which asset 'typically' moves opposite to stocks during a crash?", "opts": {"a": "Cryptocurrency", "b": "Real Estate", "c": "Gold/Bonds"}, "ans": "c"},
                {"q": "What is the primary goal of diversification?", "opts": {"a": "To maximize returns", "b": "To reduce overall portfolio risk", "c": "To pay fewer taxes"}, "ans": "b"},
                {"q": "What is Portfolio Rebalancing?", "opts": {"a": "Adding more of the same asset", "b": "Realignment of asset weightings", "c": "Selling everything"}, "ans": "b"},
                {"q": "Modern Portfolio Theory focuses on:", "opts": {"a": "Picking single lucky stocks", "b": "Optimal return for a given risk", "c": "Avoiding all risk"}, "ans": "b"},
                {"q": "An Index Fund tracks:", "opts": {"a": "A specific manager's picks", "b": "A market index (like S&P 500)", "c": "Commodity prices only"}, "ans": "b"},
                {"q": "Sector diversification protects against:", "opts": {"a": "Global collapse", "b": "Single industry downturns", "c": "Currency drops"}, "ans": "b"},
                {"q": "Geographic diversification means investing:", "opts": {"a": "Only in your home town", "b": "In international markets", "c": "In different zip codes"}, "ans": "b"},
                {"q": "Which is lower cost generally?", "opts": {"a": "Active Mutual Funds", "b": "Passive ETFs/Index Funds", "c": "Hedge Funds"}, "ans": "b"},
                {"q": "The 'Efficiency Frontier' represents:", "opts": {"a": "Lowest possible return", "b": "Optimal portfolios", "c": "The stock market floor"}, "ans": "b"}
            ]
        },
        "global": {
            "title": "Global Markets Challenge",
            "questions": [
                {"q": "What is the largest financial market in the world?", "opts": {"a": "The Stock Market", "b": "The Forex Market", "c": "The Bond Market"}, "ans": "b"},
                {"q": "What happens if a currency's value increases?", "opts": {"a": "It becomes 'stronger' relative to others", "b": "It becomes 'weaker' relative to others", "c": "Nothing changes"}, "ans": "a"},
                {"q": "What is a major risk of international investing?", "opts": {"a": "Weather volatility", "b": "Currency exchange rate risk", "c": "Too much profit"}, "ans": "b"},
                {"q": "A 'Major' currency pair usually includes the:", "opts": {"a": "Bitcoin", "b": "US Dollar (USD)", "c": "Gold"}, "ans": "b"},
                {"q": "Central Banks use interest rates to:", "opts": {"a": "Increase unemployment", "b": "Control inflation & stability", "c": "Fix stock prices"}, "ans": "b"},
                {"q": "Quantitative Easing involves:", "opts": {"a": "Selling all gold", "b": "Central bank buying securities", "c": "Lowering all taxes"}, "ans": "b"},
                {"q": "Fiat money is primarily backed by:", "opts": {"a": "Gold", "b": "The Government", "c": "Oil"}, "ans": "b"},
                {"q": "A trade surplus occurs when:", "opts": {"a": "Imports > Exports", "b": "Exports > Imports", "c": "Exports = Imports"}, "ans": "b"},
                {"q": "Hedging is used to:", "opts": {"a": "Gambling on high returns", "b": "Protect against risk", "c": "Day trade for fun"}, "ans": "b"},
                {"q": "Political instability usually makes a currency:", "opts": {"a": "Stronger", "b": "More volatile/Weaker", "c": "Static"}, "ans": "b"}
            ]
        },
        "crypto": {
            "title": "Web3 & Blockchain Exam",
            "questions": [
                {"q": "What is a blockchain?", "opts": {"a": "A centralized database", "b": "A decentralized ledger", "c": "A cloud server"}, "ans": "b"},
                {"q": "Who created Bitcoin?", "opts": {"a": "Vitalik Buterin", "b": "Satoshi Nakamoto", "c": "Elon Musk"}, "ans": "b"},
                {"q": "What enables self-executing contracts?", "opts": {"a": "Digital Wallets", "b": "Smart Contracts", "c": "Mining Rigs"}, "ans": "b"},
                {"q": "What happens if you lose your private key?", "opts": {"a": "You call support", "b": "Funds are lost forever", "c": "You reset it via email"}, "ans": "b"},
                {"q": "Which mechanism uses validation by 'staking'?", "opts": {"a": "Proof of Work", "b": "Proof of Stake", "c": "Proof of Authority"}, "ans": "b"},
                {"q": "DeFi stands for:", "opts": {"a": "Definite Finance", "b": "Decentralized Finance", "c": "Deferred Finance"}, "ans": "b"},
                {"q": "What are 'Gas Fees'?", "opts": {"a": "Cost of electricity", "b": "Transaction fees on network", "c": "A cloud storage fee"}, "ans": "b"},
                {"q": "Stablecoins are usually pegged to:", "opts": {"a": "Bitcoin Price", "b": "Fiat currency (like USD)", "c": "Total active users"}, "ans": "b"},
                {"q": "What is an NFT?", "opts": {"a": "New Financial Tool", "b": "Non-Fungible Token", "c": "Network File Transfer"}, "ans": "b"},
                {"q": "Layer 2 solutions aim to:", "opts": {"a": "Create new coins", "b": "Improve scalability/speed", "c": "Replace Layer 1 entirely"}, "ans": "b"}
            ]
        },
        "realestate": {
            "title": "Property Investment Trivia",
            "questions": [
                {"q": "What is a REIT?", "opts": {"a": "Real Estate Income Tool", "b": "Real Estate Investment Trust", "c": "Rental Equity Interest"}, "ans": "b"},
                {"q": "Formula for Rental Yield:", "opts": {"a": "Rent / Mortgage", "b": "Annual Rent / Property Value", "c": "Price / SqFt"}, "ans": "b"},
                {"name": "Leverage in real estate is:", "opts": {"a": "Using a hammer", "b": "Using borrowed capital", "c": "Buying with cash only"}, "ans": "b"},
                {"q": "What is 'Cap Rate'?", "opts": {"a": "Maximum rent allowed", "b": "Ratio of Income to Value", "c": "Real estate tax rate"}, "ans": "b"},
                {"q": "Commercial real estate includes:", "opts": {"a": "Single family homes", "b": "Offices & Warehouses", "c": "Personal gardens"}, "ans": "b"},
                {"q": "The 1% Rule suggests:", "opts": {"a": "1% downpayment", "b": "Rent should be 1% of price", "c": "Paying 1% tax"}, "ans": "b"},
                {"q": "Equity build-up comes from:", "opts": {"a": "Paying down principal", "b": "Paying interest only", "c": "Taking more loans"}, "ans": "a"},
                {"q": "Which phase is NOT in a RE cycle?", "opts": {"a": "Expansion", "b": "Hypersupply", "c": "Inflationary Boom"}, "ans": "c"},
                {"q": "Property appreciation means:", "opts": {"a": "Rent stays the same", "b": "Value increases over time", "c": "Maintenance is paid"}, "ans": "b"},
                {"q": "Net Operating Income (NOI) is:", "opts": {"a": "Total Rent collected", "b": "Income after operating expenses", "c": "Your personal salary"}, "ans": "b"}
            ]
        },
        "esg": {
            "title": "Sustainable Investing Quiz",
            "questions": [
                {"q": "ESG stands for:", "opts": {"a": "Equity, Savings, Growth", "b": "Environmental, Social, Governance", "c": "Energy, Sustainability, Global"}, "ans": "b"},
                {"q": "Carbon emissions fall under:", "opts": {"a": "Governance", "b": "Environmental", "c": "Social"}, "ans": "b"},
                {"q": "Board diversity is part of:", "opts": {"a": "Social", "b": "Governance", "c": "Environmental"}, "ans": "b"},
                {"q": "Labor standards fall under:", "opts": {"a": "Environmental", "b": "Social", "c": "Governance"}, "ans": "b"},
                {"q": "What are Green Bonds?", "opts": {"a": "Money for gambling", "b": "Debt for eco-projects", "c": "Agricultural stocks"}, "ans": "b"},
                {"q": "Impact Investing aims for:", "opts": {"a": "Only profit", "b": "Profit + Social impact", "c": "Only charity"}, "ans": "b"},
                {"q": "What is the UN's blueprint for the future?", "opts": {"a": "The Magna Carta", "b": "The SDGs", "c": "The Paris Accord"}, "ans": "b"},
                {"q": "Greenwashing is:", "opts": {"a": "Cleaning solar panels", "b": "Misleading eco-claims", "c": "Planting trees"}, "ans": "b"},
                {"q": "Shareholder activism uses:", "opts": {"a": "Social media only", "b": "Ownership stakes to influence", "c": "Physical protests"}, "ans": "b"},
                {"q": "ESG Integration is:", "opts": {"a": "Ignoring financial data", "b": "Systematic inclusion of ESG", "c": "Combining all accounts"}, "ans": "b"}
            ]
        }
    }
    
    quiz_data = quizzes.get(name.lower(), quizzes["basics"])
    
    if request.method == "POST":
        correct_count = 0
        for i, q in enumerate(quiz_data["questions"]):
            user_ans = request.form.get(f"q{i}")
            if user_ans == q["ans"]:
                correct_count += 1
        
        score = correct_count * 2
        total = len(quiz_data["questions"]) * 2
        passed = score >= 16  # 80% to pass
        
        if passed:
            completed_quizzes = session.get('completed_quizzes', [])
            if name.lower() not in completed_quizzes:
                completed_quizzes.append(name.lower())
                session['completed_quizzes'] = completed_quizzes
                session.modified = True
                
        return render_template("quiz.html", user=session.get("user"), quiz=quiz_data, score=score, total=total, passed=passed)

    return render_template("quiz.html", user=session.get("user"), quiz=quiz_data, score=score, total=total, passed=passed)

# ---------------- RUN ----------------
if __name__ == "__main__":
    app.run(debug=True)