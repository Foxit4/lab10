import os
import secrets
import sqlite3
from pathlib import Path

from flask import (Flask, abort, g, redirect, render_template_string, request,
                   session, url_for)
from werkzeug.middleware.proxy_fix import ProxyFix
from werkzeug.security import check_password_hash, generate_password_hash

app = Flask(__name__)
# Довіряємо одному проксі (Nginx) для X-Forwarded-For та X-Forwarded-Proto
app.wsgi_app = ProxyFix(app.wsgi_app, x_for=1, x_proto=1)

storage_dir = Path(os.environ.get("DATA_DIR", "instance")).resolve()
storage_dir.mkdir(parents=True, exist_ok=True)
app.config["DATABASE"] = str(storage_dir / "app.sqlite3")
app.config["SECRET_KEY"] = os.environ["SECRET_KEY"]
app.config["SESSION_COOKIE_HTTPONLY"] = True
app.config["SESSION_COOKIE_SAMESITE"] = "Lax"


# ---------- робота з БД ----------
def get_db():
    if "db" not in g:
        g.db = sqlite3.connect(app.config["DATABASE"])
        g.db.row_factory = sqlite3.Row
    return g.db


@app.teardown_appcontext
def close_db(_exc):
    db = g.pop("db", None)
    if db is not None:
        db.close()


def init_db():
    """Створює схему, якщо її немає. Наявні записи НЕ видаляються."""
    db = sqlite3.connect(app.config["DATABASE"])
    db.executescript(
        """
        CREATE TABLE IF NOT EXISTS users (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            username TEXT UNIQUE NOT NULL,
            password_hash TEXT NOT NULL
        );
        CREATE TABLE IF NOT EXISTS notes (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL REFERENCES users(id),
            body TEXT NOT NULL,
            created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
        );
        """
    )
    db.commit()
    db.close()


init_db()


# ---------- допоміжне ----------
BASE = """
<!doctype html><html lang="uk"><head><meta charset="utf-8">
<title>Lab 10</title></head><body style="font-family:sans-serif;max-width:640px;margin:2em auto">
<nav>
  <a href="{{ url_for('index') }}">Головна</a> |
  {% if session.get('user_id') %}
    <a href="{{ url_for('notes') }}">Нотатки</a> |
    <a href="{{ url_for('logout') }}">Вийти ({{ session['username'] }})</a>
  {% else %}
    <a href="{{ url_for('login') }}">Вхід</a> |
    <a href="{{ url_for('register') }}">Реєстрація</a>
  {% endif %}
</nav><hr>
{% if error %}<p style="color:#b00">{{ error }}</p>{% endif %}
%BODY%
</body></html>
"""


def page(body, **ctx):
    return render_template_string(BASE.replace("%BODY%", body), **ctx)


def csrf_token():
    if "csrf" not in session:
        session["csrf"] = secrets.token_hex(16)
    return session["csrf"]


app.jinja_env.globals["csrf_token"] = csrf_token


@app.before_request
def check_csrf():
    if request.method == "POST":
        sent = request.form.get("csrf", "")
        if not sent or not secrets.compare_digest(sent, session.get("csrf", "")):
            abort(400, "CSRF token missing or invalid")


def login_required():
    return "user_id" in session


# ---------- маршрути ----------
@app.get("/health")
def health():
    return {"status": "ok"}, 200


@app.get("/")
def index():
    return page(
        "<h1>Лабораторна робота №10</h1>"
        "<p>Flask + Gunicorn за Nginx (Docker Compose).</p>"
        "<p>Ваша IP-адреса (за X-Forwarded-For): {{ request.remote_addr }}</p>"
    )


@app.route("/register", methods=["GET", "POST"])
def register():
    error = None
    if request.method == "POST":
        username = request.form.get("username", "").strip()
        password = request.form.get("password", "")
        if not username or len(password) < 6:
            error = "Логін обов'язковий, пароль — щонайменше 6 символів."
        else:
            try:
                db = get_db()
                db.execute(
                    "INSERT INTO users (username, password_hash) VALUES (?, ?)",
                    (username, generate_password_hash(password)),
                )
                db.commit()
                return redirect(url_for("login"))
            except sqlite3.IntegrityError:
                error = "Такий користувач уже існує."
    return page(
        """<h2>Реєстрація</h2>
        <form method="post">
          <input type="hidden" name="csrf" value="{{ csrf_token() }}">
          <p><input name="username" placeholder="логін" required></p>
          <p><input name="password" type="password" placeholder="пароль" required></p>
          <button>Зареєструватися</button>
        </form>""",
        error=error,
    )


@app.route("/login", methods=["GET", "POST"])
def login():
    error = None
    if request.method == "POST":
        row = get_db().execute(
            "SELECT * FROM users WHERE username = ?",
            (request.form.get("username", "").strip(),),
        ).fetchone()
        if row and check_password_hash(row["password_hash"], request.form.get("password", "")):
            session.clear()
            session["user_id"] = row["id"]
            session["username"] = row["username"]
            return redirect(url_for("notes"))
        error = "Невірний логін або пароль."
    return page(
        """<h2>Вхід</h2>
        <form method="post">
          <input type="hidden" name="csrf" value="{{ csrf_token() }}">
          <p><input name="username" placeholder="логін" required></p>
          <p><input name="password" type="password" placeholder="пароль" required></p>
          <button>Увійти</button>
        </form>""",
        error=error,
    )


@app.get("/logout")
def logout():
    session.clear()
    return redirect(url_for("index"))


@app.route("/notes", methods=["GET", "POST"])
def notes():
    if not login_required():
        return redirect(url_for("login"))
    db = get_db()
    if request.method == "POST":
        body = request.form.get("body", "").strip()
        if body:
            db.execute(
                "INSERT INTO notes (user_id, body) VALUES (?, ?)",
                (session["user_id"], body),
            )
            db.commit()
        return redirect(url_for("notes"))  # Post/Redirect/Get
    rows = db.execute(
        "SELECT id, body, created_at FROM notes WHERE user_id = ? ORDER BY id DESC",
        (session["user_id"],),
    ).fetchall()
    return page(
        """<h2>Мої нотатки</h2>
        <form method="post">
          <input type="hidden" name="csrf" value="{{ csrf_token() }}">
          <p><textarea name="body" rows="3" cols="50" required></textarea></p>
          <button>Додати</button>
        </form>
        <ul>{% for n in rows %}<li>#{{ n['id'] }} [{{ n['created_at'] }}] {{ n['body'] }}</li>{% endfor %}</ul>""",
        rows=rows,
    )


if __name__ == "__main__":
    app.run(host="127.0.0.1", port=5000, debug=False)
