import os
import sqlite3

from flask import Flask, flash, redirect, render_template, request, session
from flask_session import Session
from werkzeug.security import check_password_hash, generate_password_hash

from helpers import apology, login_required, lookup, ars
from helpers import get_db_connection

# Configuramos la aplicacion
app = Flask(__name__)

# Custom filter
app.jinja_env.filters["ars"] = ars

# Configuramos sesion para usar filesystem (en vez de cookies)
app.config["SESSION_PERMANENT"] = False
app.config["SESSION_TYPE"] = "filesystem"
Session(app)

# Set up conexion a la base de datos
conn = get_db_connection()
db = conn.cursor()


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
    """4 Show portfolio of stocks"""
    # obtenemos las acciones del usuario
    stocks = db.execute("SELECT symbol, SUM(shares) as total_shares FROM transactions WHERE user_id = :user_id GROUP BY symbol HAVING total_shares > 0",
                        user_id=session["user_id"])
    # obtenemos el balance de efectivo del usuario
    cash = db.execute("SELECT cash FROM users WHERE id = :user_id", user_id=session["user_id"])[0]["cash"]

    # inicializamos variables para valores totales
    total_value = cash
    grand_total = cash

    # iteramos sobre y añadimos el precio y valor total
    for stock in stocks:
        quote = lookup(stock["symbol"])
        stock["price"] = quote["price"]
        stock["value"] = stock["price"] * stock["total_shares"]
        total_value += stock["value"]
        grand_total += stock["value"]

    return render_template("index.html", stocks=stocks, cash=cash, total_value=total_value, grand_total=grand_total)


@app.route("/buy", methods=["GET", "POST"])
@login_required
def buy():
    """3 Buy shares of stock"""
    if request.method == "POST":
        symbol = request.form.get("symbol").upper()
        shares = request.form.get("shares")
        if not symbol:
            return apology("must return symbol")
        elif not shares or not shares.isdigit() or int(shares) <= 0:
            return apology("must provide a positive integer number of shares")

        quote = lookup(symbol)
        if quote is None:
            return apology("symbol not found")

        price = quote["price"]
        total_cost = int(shares) * price
        cash = db.execute("SELECT cash FROM users WHERE id = :user_id", user_id=session["user_id"])[0]["cash"]

        if cash < total_cost:
            return apology("not enough cash")

        #actualiza la tabla usuarios
        db.execute("UPDATE users SET cash = cash - :total_cost WHERE id = :user_id",
                   total_cost=total_cost, user_id=session["user_id"])

        #añade compras a la tabla historial
        db.execute("INSERT INTO transactions (user_id, symbol, shares, price) VALUES (:user_id, :symbol, :shares, :price)",
                   user_id=session["user_id"], symbol=symbol, shares=shares, price=price)

        flash(f"Bought {shares} shares of {symbol} for {ars(total_cost)}!")
        return redirect("/")

    else:
        return render_template("buy.html")


@app.route("/history")
@login_required
def history():
    """6 Show history of transactions"""
    #Query base de datos para buscar transacciones de usuarios, ordenado por mas reciente primero
    transactions = db.execute(
        "SELECT * FROM transactions WHERE user_id = :user_id ORDER BY timestamp DESC", user_id=session["user_id"])

    #renderiza la plantilla de historial con las transacciones
    return render_template("history.html", transactions=transactions)


@app.route("/login", methods=["GET", "POST"])
def login():
    """Log user in"""

    # "Olvidamos" cualquier sesion de usuario
    session.clear()

    # Usuario alcanzo la route via POST (como haciendo submit a una form via POST)
    if request.method == "POST":
        # Aseguramos que se proporciono un nombre de usuario
        if not request.form.get("username"):
            return apology("must provide username", 403)

        # Aseguramos que se proporciono una password
        elif not request.form.get("password"):
            return apology("must provide password", 403)

        # Query bd para el username
        rows = db.execute(
            "SELECT * FROM users WHERE username = ?", request.form.get("username")
        )

        # Aseguramos que username existe y password es correcta
        if len(rows) != 1 or not check_password_hash(
            rows[0]["hash"], request.form.get("password")
        ):
            return apology("invalid username and/or password", 403)

        # recuerda que usuario se ha loggeado
        session["user_id"] = rows[0]["id"]

        # Redirecciona usuario a home page
        return redirect("/")

    # Usuario alcanzo la rutae via GET (como haciendo click a link o via redireccionado)
    else:
        return render_template("login.html")


@app.route("/logout")
def logout():
    """Log user out"""

    # Se olvido una user_id
    session.clear()

    # Redirecciona usuario a formulario login
    return redirect("/")


@app.route("/quote", methods=["GET", "POST"])
@login_required
def quote():
    """2 Get stock quote."""
    if request.method == "POST":
        symbol = request.form.get("symbol")
        quote = lookup(symbol)
        if not quote:
            return apology("Invalid symbol", 400)
        return render_template("quote.html", quote=quote)
    else:
        return render_template("quote.html")


@app.route("/register", methods=["GET", "POST"])
def register():
    """1 Register user"""
    # se olvida cualquier sesion de usuario
    session.clear()

    #Usuario alcanzo ruta via POST (como haciendo submit en un FORMULARIO via POST)
    if request.method == "POST":
        #Asegurarnos que un USER NAME fue proporcionado
        if not request.form.get("username"):
            return apology("must provide username", 400)

        #asegurarnos password fue proporcionado
        elif not request.form.get("password"):
            return apology("must provide password", 400)

        #asegurarnos que la confirmacion de password fue proporcionada
        elif not request.form.get("confirmation"):
            return apology("must confirm password", 400)

        #asegurarnos que password y confirmacion de password coinciden
        elif request.form.get("password") != request.form.get("confirmation"):
            return apology("passwords do not match", 400)

        #Query base de datos por username
        rows = db.execute("SELECT * FROM users WHERE username = ?", request.form.get("username"))

        #Asegurarnos que username no existe
        if len(rows) != 0:
            return apology("username already exists", 400)

        #INSERTAR nuevo usuario en la base de datos
        db.execute("INSERT INTO users (username, hash) VALUES (?, ?)",
                    request.form.get("username"), generate_password_hash(request.form.get("password")))

        #Query bd por nuevo usuario insertado
        rows = db.execute("SELECT * FROM users WHERE username = ?", request.form.get("username"))

        #Recordar que usuario se ha loggeado
        session["user_id"] = rows[0]["id"]

        #redireccionar a homepage
        return redirect("/")

    #Usuario alcanzo la ruta via get (como con un click en un link o redireccionado)
    else:
        return render_template("register.html")


@app.route("/sell", methods=["GET", "POST"])
@login_required
def sell():
    """5 Sell shares of stock"""
    #obtener las acciones del usuario
    stocks = db.execute("SELECT symbol, SUM(shares) as total_shares FROM transactions WHERE user_id = :user_id GROUP BY symbol HAVING total_shares > 0",
                        user_id=session["user_id"])

    #si el usuario envia el formulario
    if request.method == "POST":
        symbol = request.form.get("symbol").upper()
        shares = request.form.get("shares")
        if not symbol:
            return apology("must provide symbol")
        elif not shares or not shares.isdigit() or int(shares) <= 0:
            return apology("must provide a positive integer number of shares")
        else:
            shares = int(shares)

        for stock in stocks:
            if stock["symbol"] == symbol:
                if stock["total_shares"] < shares:
                    return apology("not enough shares")
                else:
                    #obtener cotizacion
                    quote = lookup(symbol)
                    if quote is None:
                        return apology("symbol not found")
                    price = quote["price"]
                    total_sale = shares * price

                    #actualizar la tabla de usuarios
                    db.execute("UPDATE users SET cash = cash + :total_sale WHERE id = :user_id",
                               total_sale=total_sale, user_id=session["user_id"])

                    #Añadir nuevas ventas a la tabla de historial
                    db.execute("INSERT INTO transactions (user_id, symbol, shares, price) VALUES (:user_id, :symbol, :shares, :price)",
                               user_id=session["user_id"], symbol=symbol, shares=shares, price=price)

                    flash(f"Sold {shares} shares of {symbol} for {ars(total_sale)}!")
                    return redirect("/")

        return apology("symbol not found")

    #si el usuario visita la pagina
    else:
        return render_template("sell.html", stocks=stocks)


@app.route("/wallet", methods=["GET", "POST"])
@login_required
def wallet():
    """7 OWN THING allow users to add cash to the user's account."""
    if request.method == "POST":
        amount = request.form.get("amount")

        if not amount or not amount.isdigit() or int(amount) <= 0:
            return apology("must provide a positive integer amount")

        amount = int(amount)
        # Actualizar el balance del usuario
        db.execute("UPDATE users SET cash = cash + :amount WHERE id = :user_id",
                   amount=amount, user_id=session["user_id"])

        flash(f"Added {ars(amount)} to your account!")
        return redirect("/")

    return render_template("wallet.html")