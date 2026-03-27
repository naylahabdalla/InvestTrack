from flask import Flask, render_template, request, redirect, url_for, session
from supabase import create_client, Client
import yfinance as yf
import requests
from werkzeug.security import generate_password_hash, check_password_hash
import re
import os
from dotenv import load_dotenv

load_dotenv()

VERSION: str = "1.1.0"

url: str = os.getenv("SUPABASE_URL")
key: str = os.getenv("SUPABASE_KEY")

if not url or not key:
    raise ValueError("Missing SUPABASE_URL or SUPABASE_KEY environment variables. "
                     "Please check your .env file or deployment settings.")

supabase: Client = create_client(url, key)

app: Flask = Flask(__name__, template_folder='../templates', static_folder='../static')
app.secret_key = os.getenv("FLASK_SECRET_KEY", "investtrack_default_secret_key")

@app.context_processor
def inject_version():
    return dict(version=VERSION)

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
 
# ---------------- DEMO ----------------
@app.route("/demo")
def demo_login():
    session["user"] = "demo"
    return redirect("/dashboard")

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

    # 📊 REAL-TIME DATA FETCHING
    def get_price(ticker):
        try:
            stock = yf.Ticker(ticker)
            return round(stock.history(period="1d")["Close"].iloc[-1], 2)
        except:
            return 0.0

    prices = {
        "apple": get_price("AAPL") or 175.0,
        "tesla": get_price("TSLA") or 240.0,
        "btc": get_price("BTC-USD") or 65000.0,
        "eth": get_price("ETH-USD") or 3500.0
    }

    return render_template(
        "dashboard.html", user=session.get("user"),
        investments=investments,
        total=round(total,2),
        current=round(current,2),
        gain=round(gain,2),
        percent=round(percent,2),
        count=len(investments),
        **prices
    )

# ---------------- ADD ----------------
@app.route("/add", methods=["GET", "POST"])
def add():
    if "user" not in session:
        return redirect("/login")

    if request.method == "POST":
        if session.get("user") == "demo":
            return render_template("add_investment.html", user=session.get("user"), error="Action disabled in Demo Mode")
        
        name = request.form["asset_name"]
        type_ = request.form["asset_type"]
        amount = float(request.form["amount"])

        supabase.table("investments").insert({"asset_name": name, "asset_type": type_, "amount": amount, "username": session["user"]}).execute()

        return redirect("/dashboard")

    return render_template("add_investment.html", user=session.get("user"))

# ---------------- LOGOUT ----------------
@app.route("/logout")
def logout():
    session.pop("user", None)
    return redirect("/")

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
        if session.get("user") == "demo":
            return render_template("feedback.html", user=session.get("user"), error="Action disabled in Demo Mode")
        
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
    if session.get("user") == "demo":
        return redirect("/portfolio")
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
        "basics": """
            <h5>The Foundation of Wealth</h5>
            <p>Investing is the act of allocating resources, usually money, with the expectation of generating an income or profit. You can invest in assets, such as stocks, bonds, real estate, and more.</p>
            <ul>
                <li><strong>Risk vs Reward:</strong> Higher potential returns typically come with higher risk.</li>
                <li><strong>Compound Interest:</strong> The ability of an investment to generate earnings, which are then reinvested to generate their own earnings.</li>
                <li><strong>Inflation:</strong> The rate at which the general level of prices for goods and services is rising.</li>
            </ul>
        """,
        "stocks": """
            <h5>Owning a Piece of the Future</h5>
            <p>A stock (also known as equity) is a security that represents the ownership of a fraction of a corporation. This entitles the owner of the stock to a proportion of the corporation's assets and profits equal to how much stock they own.</p>
            <ul>
                <li><strong>Common vs Preferred:</strong> Common stock usually carries voting rights, while preferred stock has a higher claim on assets.</li>
                <li><strong>Dividends:</strong> A distribution of a portion of a company's earnings, decided by the board of directors, to a class of its shareholders.</li>
                <li><strong>Market Cap:</strong> The total value of a company's shares of stock.</li>
            </ul>
        """,
        "diversification": """
            <h5>Don't Put All Your Eggs in One Basket</h5>
            <p>Diversification is a risk management strategy that mixes a wide variety of investments within a portfolio. A diversified portfolio contains a mix of distinct asset types and investment vehicles in an attempt at limiting exposure to any single asset or risk.</p>
            <ul>
                <li><strong>Asset Allocation:</strong> Spreading your investments across different asset classes like stocks, bonds, and cash.</li>
                <li><strong>Correlation:</strong> The degree to which two different assets move in relation to each other.</li>
                <li><strong>Rebalancing:</strong> Periodically adjusting your portfolio to maintain your desired level of asset allocation.</li>
            </ul>
        """,
        "currency": """
            <h5>Navigating the Global Market</h5>
            <p>The foreign exchange (forex) market is the largest, most liquid market in the world. It involves the buying and selling of currencies to capitalize on exchange rate fluctuations.</p>
            <ul>
                <li><strong>Exchange Rates:</strong> The value of one currency for the purpose of conversion to another.</li>
                <li><strong>Pairs:</strong> Currencies are always traded in pairs (e.g., EUR/USD).</li>
                <li><strong>Liquidity:</strong> The ease with which an asset can be converted into ready cash without affecting its market price.</li>
            </ul>
        """,
        "realestate": """
            <h5>Investing in Bricks and Mortar</h5>
            <p>Real estate investing involves the purchase, ownership, management, rental, and/or sale of real estate for profit. Improvements of realty as part of a real estate investment strategy is generally considered to be a sub-specialty of real estate investing.</p>
            <ul>
                <li><strong>Rental Income:</strong> Cash flow generated by leasing property to tenants.</li>
                <li><strong>Appreciation:</strong> The increase in value of a property over time.</li>
                <li><strong>REITs:</strong> Real Estate Investment Trusts allow you to invest in large-scale properties without owning them directly.</li>
            </ul>
        """,
        "retirement": """
            <h5>Securing Your Golden Years</h5>
            <p>Retirement planning is the process of determining retirement income goals and the actions and decisions necessary to achieve those goals. It includes identifying sources of income, estimating expenses, implementing a savings program, and managing assets and risk.</p>
            <ul>
                <li><strong>401(k) / IRA:</strong> Tax-advantaged accounts designed to help you save for retirement.</li>
                <li><strong>The 4% Rule:</strong> A rule of thumb used to determine how much a retiree should withdraw from their retirement portfolio each year.</li>
                <li><strong>Social Security:</strong> A federal insurance program that provides benefits to retired people and those who are unemployed or disabled.</li>
            </ul>
        """
    }
    content = content_map.get(name.lower().replace(" ", ""), "Detailed content coming soon!")
    return render_template("course.html", user=session.get("user"), title=name.title(), content=content)

@app.route("/quiz/<path:name>", methods=["GET", "POST"])
def quiz(name):
    if "user" not in session: return redirect("/login")
    score = None
    if request.method == "POST":
        ans1 = request.form.get("q1")
        ans2 = request.form.get("q2")
        ans3 = request.form.get("q3")
        ans4 = request.form.get("q4")
        ans5 = request.form.get("q5")
        score = sum([ans1 == "b", ans2 == "b", ans3 == "b", ans4 == "b", ans5 == "b"])
    return render_template("quiz.html", user=session.get("user"), score=score)

# ---------------- RUN ----------------
if __name__ == "__main__":
    app.run(debug=True)