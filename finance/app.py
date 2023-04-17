import os

from cs50 import SQL
from flask import Flask, flash, redirect, render_template, request, session
from flask_session import Session
from tempfile import mkdtemp
from werkzeug.security import check_password_hash, generate_password_hash
import datetime

from helpers import apology, login_required, lookup, usd

# Configure application
app = Flask(__name__)

# Custom filter
app.jinja_env.filters["usd"] = usd

# Configure session to use filesystem (instead of signed cookies)
app.config["SESSION_PERMANENT"] = False
app.config["SESSION_TYPE"] = "filesystem"
Session(app)

# Configure CS50 Library to use SQLite database
db = SQL("sqlite:///finance.db")

# Make sure API key is set
if not os.environ.get("API_KEY"):
    raise RuntimeError("API_KEY not set")


@app.after_request
def after_request(response):
    """Ensure responses aren't cached"""
    response.headers["Cache-Control"] = "no-cache, no-store, must-revalidate"
    response.headers["Expires"] = 0
    response.headers["Pragma"] = "no-cache"
    return response


@app.route("/")
@login_required
def index():
    """Show portfolio of stocks"""
    #get data from database
    user_id = session["user_id"]

    transactions_db = db.execute("SELECT symbol, SUM(shares) AS totalShares, price FROM transactions WHERE user_id = ? AND symbol IS NOT '£' GROUP BY symbol", user_id)
    cash_db = db.execute("SELECT cash FROM users WHERE id = ?", user_id)
    cash = round(cash_db[0]["cash"],2)

    total = cash

    for stock in transactions_db:
        total += stock["price"] * stock["totalShares"]

    return render_template("index.html", database = transactions_db, cash = cash, total = round(total, 2))


@app.route("/buy", methods=["GET", "POST"])
@login_required
def buy():
    """Buy shares of stock"""
    #check if link clicked (GET) or form submitted (post)
    if request.method == "GET":
        return render_template("buy.html")
#get the symbol and shares from form and check against lookup function and shares >=0
    else:
        symbol = request.form.get("symbol")
        try:
            shares = float(request.form.get("shares"))
        except:
            return apology("Please enter a number.")

        if not symbol:
            return apology("Please give a Symbol.")

        stock = lookup(symbol.upper())

        if stock == None:
            return apology("Symbol does not exist.")

        if shares <= 0:
            return apology("Please enter a positive number.")

        if not shares.is_integer():
            return apology("Must be whole number.")
#calculate transaction value and deduct from users cash balance
        transaction_value = shares * stock["price"]

        user_id = session["user_id"]
        user_cash_db = db.execute("SELECT cash FROM users WHERE id = ?", user_id)
        user_cash = user_cash_db[0]["cash"]


        if user_cash < transaction_value:
            return apology("Insufficient funds.")

        updated_cash = round(user_cash - transaction_value, 2)

        db.execute("UPDATE users SET cash = ? WHERE id = ?", updated_cash, user_id)
#get datetime and insert into transactions table
        date = datetime.datetime.now()

        db.execute("INSERT INTO transactions (user_id, symbol, shares, price, date) VALUES (?, ?, ?, ?, ?)", user_id, stock["symbol"], shares, ("%0.2f" % (stock["price"])), date)

        flash("Purchase complete.")
        return redirect("/")



@app.route("/history")
@login_required
def history():
    """Show history of transactions"""
    user_id = session["user_id"]
    transactions_db = db.execute("SELECT * FROM transactions WHERE user_id = ?", user_id)
    return render_template("history.html", database_his = transactions_db)

@app.route("/login", methods=["GET", "POST"])
def login():
    """Log user in"""

    # Forget any user_id
    session.clear()

    # User reached route via POST (as by submitting a form via POST)
    if request.method == "POST":

        # Ensure username was submitted
        if not request.form.get("username"):
            return apology("must provide username", 403)

        # Ensure password was submitted
        elif not request.form.get("password"):
            return apology("must provide password", 403)

        # Query database for username
        rows = db.execute("SELECT * FROM users WHERE username = ?", request.form.get("username"))

        # Ensure username exists and password is correct
        if len(rows) != 1 or not check_password_hash(rows[0]["hash"], request.form.get("password")):
            return apology("invalid username and/or password", 403)

        # Remember which user has logged in
        session["user_id"] = rows[0]["id"]

        # Redirect user to home page
        return redirect("/")

    # User reached route via GET (as by clicking a link or via redirect)
    else:
        return render_template("login.html")


@app.route("/logout")
def logout():
    """Log user out"""

    # Forget any user_id
    session.clear()

    # Redirect user to login form
    return redirect("/")


@app.route("/quote", methods=["GET", "POST"])
@login_required
def quote():
    """Get stock quote."""
    if request.method == "GET":
        return render_template("quote.html")

    else:
        symbol = request.form.get("symbol")

        if not symbol:
            return apology("Please give a Symbol.")

        stock = lookup(symbol.upper())

        if stock == None:
            return apology("Symbol does not exist.")

        return render_template("quoted.html", name = stock["name"], price = ("%0.2f" % (stock["price"])), symbol = stock["symbol"])


@app.route("/register", methods=["GET", "POST"])
def register():
    if request.method == "GET":
        return render_template("register.html")

    else:
        """Register user"""
        username = request.form.get("username")
        password = request.form.get("password")
        confirmation = request.form.get("confirmation")

        if not username or not password:
            return apology("Please give a username and password.")

        if password != confirmation:
            return apology("Passwords don't match.")

        hash = generate_password_hash(password)

        try:
            new_user = db.execute("INSERT INTO users (username, hash) VALUES (?, ?)", username, hash)
        except:
            return apology("Username already exists.")

        session["user_id"] = new_user

        return redirect("/")


@app.route("/sell", methods=["GET", "POST"])
@login_required
def sell():
    """Sell shares of stock"""
    if request.method == "GET":
        user_id = session["user_id"]
        user_symbols = db.execute("SELECT symbol FROM transactions WHERE user_id = ? GROUP BY symbol HAVING SUM(shares) > 0", user_id)
        return render_template("sell.html", symbols = [row["symbol"] for row in user_symbols])

        #get the symbol and shares from form and check against lookup function and shares >=0
    else:
        symbol = request.form.get("symbol")
        shares = int(request.form.get("shares"))

        if not symbol:
            return apology("Please give a Symbol.")

        stock = lookup(symbol.upper())

        if stock == None:
            return apology("Symbol does not exist.")

        if shares <= 0:
            return apology("Please enter a positive number.")


#calculate transaction value
        transaction_value = shares * stock["price"]

        user_id = session["user_id"]
        user_cash_db = db.execute("SELECT cash FROM users WHERE id = ?", user_id)
        user_cash = user_cash_db[0]["cash"]

        #check user has suffiecent shares to sell
        user_shares = db.execute("SELECT shares FROM transactions WHERE user_id = ? AND symbol = ? GROUP BY symbol", user_id, symbol)
        user_shares_int = user_shares[0]["shares"]

        if user_shares_int < shares:
            return apology("You do not own this many shares.")
        #add to users cash balance
        updated_cash = user_cash + transaction_value

        db.execute("UPDATE users SET cash = ? WHERE id = ?", updated_cash, user_id)
#get datetime and insert into transactions table
        date = datetime.datetime.now()

        db.execute("INSERT INTO transactions (user_id, symbol, shares, price, date) VALUES (?, ?, ?, ?, ?)", user_id, stock["symbol"], (-1)*shares, stock["price"], date)

        flash("Sale complete.")
        return redirect("/")

@app.route("/wallet", methods=["GET", "POST"])
@login_required
def wallet():
    user_id = session["user_id"]
    if request.method == "GET":
    #get data from database


        cash_db = db.execute("SELECT cash FROM users WHERE id = ?", user_id)
        cash = round(cash_db[0]["cash"],2)

        return render_template("wallet.html", cash = cash)

    else:
        #add cash to balance from form
        added_cash = int(request.form.get("add_cash"))
        user_cash_db = db.execute("SELECT cash FROM users WHERE id = ?", user_id)
        user_cash = user_cash_db[0]["cash"]

        incr_cash = added_cash + user_cash

        db.execute("UPDATE users SET cash = ? WHERE id = ?", round(incr_cash,2), user_id)

        #add transaction to transactions.db
        date = datetime.datetime.now()

        db.execute("INSERT INTO transactions (user_id, symbol, shares, price, added_cash, date) VALUES (?, ?, ?, ?, ?, ?)", user_id, "£", "£", added_cash, added_cash, date)

        flash("Cash added!")
        return redirect("/")