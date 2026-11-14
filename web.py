
import json
import random
import logging
import hmac
import os
import secrets

from functools import wraps

from flask import (
    Flask,
    render_template,
    request,
    redirect,
    url_for,
    session,
    flash,
    jsonify,
)

from sqlalchemy import desc, func, update

from db import (
    SessionLocal,
    Game,
    Player,
    BingoCard,
    PaymentRequest,
)

from game import json_list

from config import (
    ADMIN_PASSWORD,
    ENTRY_FEE,
    PRIZE_PERCENT,
    CURRENCY,
    SECRET_KEY,
)


# =====================================
# LOGGING
# =====================================

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(name)s - %(message)s",
)

log = logging.getLogger("trustbingo.web")


# =====================================
# FLASK CONFIGURATION
# =====================================

app = Flask(__name__)

if not SECRET_KEY or SECRET_KEY == "replace-this-secret-key":
    raise RuntimeError("Set a strong SECRET_KEY in your .env file.")

if not ADMIN_PASSWORD or ADMIN_PASSWORD == "ChangeThisStrongPassword":
    raise RuntimeError("Set a strong ADMIN_PASSWORD in your .env file.")

app.secret_key = SECRET_KEY

app.config.update(
    SESSION_COOKIE_HTTPONLY=True,
    SESSION_COOKIE_SAMESITE="Lax",
    SESSION_COOKIE_SECURE=False,  # Set True when deployed with HTTPS.
    PERMANENT_SESSION_LIFETIME=3600,
)


# =====================================
# CSRF PROTECTION
# =====================================

def get_csrf_token():

    if "_csrf_token" not in session:
        session["_csrf_token"] = secrets.token_urlsafe(32)

    return session["_csrf_token"]


app.jinja_env.globals["csrf_token"] = get_csrf_token


@app.before_request
def protect_admin_posts():

    if request.method == "POST" and request.path.startswith("/admin/"):

        if not session.get("admin"):
            return redirect(url_for("admin_login"))

        submitted_token = request.form.get("csrf_token", "")
        session_token = session.get("_csrf_token", "")

        if not submitted_token or not session_token:
            return "Invalid security token. Reload the page.", 400

        if not hmac.compare_digest(submitted_token, session_token):
            return "Invalid security token. Please reload the page.", 400


# =====================================
# ADMIN LOGIN PROTECTION
# =====================================

def admin_required(fn):

    @wraps(fn)
    def wrapper(*args, **kwargs):

        if not session.get("admin"):
            flash("እባክዎ በአድሚን ይግቡ።")
            return redirect(url_for("admin_login"))

        return fn(*args, **kwargs)

    return wrapper


# =====================================
# DATABASE HELPERS
# =====================================

VALID_ROOM_FEES = (10, 50)


def get_active_game(db, entry_fee=None):

    query = db.query(Game).filter(Game.status == "active")

    if entry_fee is not None:
        query = query.filter(Game.entry_fee == entry_fee)

    return query.order_by(desc(Game.id)).first()


def get_room_name(entry_fee):

    return "GoodBingo" if entry_fee == 10 else "SuperBingo"


def get_payment_type(payment):

    return getattr(payment, "request_type", "deposit") or "deposit"


def get_game_player_count(db, game_id):

    return (
        db.query(func.count(func.distinct(BingoCard.player_id)))
        .filter(BingoCard.game_id == game_id)
        .scalar()
        or 0
    )


def clean_drawn_numbers(value):

    numbers = json_list(value)

    return list(dict.fromkeys(
        n for n in numbers
        if isinstance(n, int)
        and not isinstance(n, bool)
        and 1 <= n <= 75
    ))


# =====================================
# PUBLIC WEBSITE
# =====================================

@app.get("/")
def index():

    try:

        stake = request.args.get("stake", default=10, type=int)

        if stake not in VALID_ROOM_FEES:
            stake = 10

        with SessionLocal() as db:

            game = get_active_game(db, stake)

            drawn = clean_drawn_numbers(
                game.drawn_numbers
            ) if game else []

            players_count = (
                get_game_player_count(db, game.id)
                if game else 0
            )

            return render_template(
                "index.html",
                game=game,
                drawn=drawn,
                players=players_count,
                currency=CURRENCY,
                stake=stake,
                room_name=get_room_name(stake),
                board=list(range(1, 76)),
            )

    except Exception:

        log.exception("Public website error.")

        return "Website temporarily unavailable.", 500


# =====================================
# BONUS PAGE
# =====================================

@app.get("/bonus")
def bonus():

    return render_template("bonus.html")


# =====================================
# ROOM-SPECIFIC GAME API
# =====================================

@app.get("/api/game")
def api_game():

    try:

        stake = request.args.get("stake", default=10, type=int)

        if stake not in VALID_ROOM_FEES:

            return jsonify({
                "active": False,
                "error": "Invalid room. Choose 10 or 50 ETB.",
            }), 400

        with SessionLocal() as db:

            game = get_active_game(db, stake)

            if not game:

                return jsonify({
                    "active": False,
                    "stake": stake,
                    "room_name": get_room_name(stake),
                    "drawn": [],
                    "board": list(range(1, 76)),
                    "players": 0,
                    "entry_fee": stake,
                })

            drawn = clean_drawn_numbers(game.drawn_numbers)

            players_count = get_game_player_count(db, game.id)

            return jsonify({
                "active": True,
                "id": game.id,
                "stake": stake,
                "room_name": get_room_name(stake),
                "drawn": drawn,
                "board": list(range(1, 76)),
                "players": players_count,
                "prize_pool": game.prize_pool,
                "entry_fee": game.entry_fee,
            })

    except Exception:

        log.exception("Game API error.")

        return jsonify({
            "active": False,
            "error": "Unable to retrieve game information.",
        }), 500


# =====================================
# PLAYER BALANCE API
# =====================================

@app.get("/api/balance")
def api_balance():

    # Compatibility endpoint.
    # A URL-supplied Telegram ID is NOT authentication.
    # Validate Telegram Web App initData before using
    # this endpoint for real-money operations.

    telegram_id = request.args.get("user_id", "").strip()

    if not telegram_id.isdigit():

        return jsonify({
            "success": False,
            "error": "Invalid player ID.",
        }), 400

    try:

        with SessionLocal() as db:

            player = (
                db.query(Player)
                .filter_by(telegram_id=telegram_id)
                .first()
            )

            if not player:

                return jsonify({
                    "success": False,
                    "balance": 0,
                })

            return jsonify({
                "success": True,
                "balance": player.balance,
                "currency": CURRENCY,
            })

    except Exception:

        log.exception("Balance API error.")

        return jsonify({
            "success": False,
            "error": "Unable to retrieve balance.",
        }), 500


# =====================================
# ADMIN LOGIN
# =====================================

@app.route("/admin", methods=["GET", "POST"])
def admin_login():

    if session.get("admin"):
        return redirect(url_for("dashboard"))

    if request.method == "POST":

        password = request.form.get("password", "")

        if hmac.compare_digest(
            str(password),
            str(ADMIN_PASSWORD),
        ):

            session.clear()

            session["admin"] = True
            session.permanent = True
            session["_csrf_token"] = secrets.token_urlsafe(32)

            flash("በትክክል ገብተዋል።")

            return redirect(url_for("dashboard"))

        flash("የይለፍ ቃሉ ትክክል አይደለም።")

    return render_template("admin_login.html")


# =====================================
# ADMIN LOGOUT
# =====================================

@app.route("/admin/logout", methods=["GET", "POST"])
@admin_required
def admin_logout():

    session.clear()

    flash("ከአድሚን አካውንት ወጥተዋል።")

    return redirect(url_for("index"))


# =====================================
# ADMIN DASHBOARD
# =====================================

@app.get("/admin/dashboard")
@admin_required
def dashboard():

    try:

        with SessionLocal() as db:

            # Independently retrieve both active rooms.
            good_game = get_active_game(db, 10)
            super_game = get_active_game(db, 50)

            # Backward compatibility with existing template.
            game = good_game or super_game

            pending = (
                db.query(PaymentRequest)
                .filter_by(status="pending")
                .order_by(PaymentRequest.id)
                .all()
            )

            players = (
                db.query(Player)
                .order_by(desc(Player.id))
                .limit(100)
                .all()
            )

            total_players = db.query(Player).count()

            pending_count = (
                db.query(PaymentRequest)
                .filter_by(status="pending")
                .count()
            )

            total_credit = (
                db.query(
                    func.coalesce(func.sum(Player.balance), 0)
                ).scalar()
            )

            good_cards_count = (
                get_game_player_count(db, good_game.id)
                if good_game else 0
            )

            super_cards_count = (
                get_game_player_count(db, super_game.id)
                if super_game else 0
            )

            good_drawn = (
                clean_drawn_numbers(good_game.drawn_numbers)
                if good_game else []
            )

            super_drawn = (
                clean_drawn_numbers(super_game.drawn_numbers)
                if super_game else []
            )

            drawn = (
                clean_drawn_numbers(game.drawn_numbers)
                if game else []
            )

            game_cards_count = (
                good_cards_count
                if game and game.entry_fee == 10
                else super_cards_count
            )

            return render_template(
                "dashboard.html",

                game=game,
                drawn=drawn,

                pending=pending,
                players=players,

                currency=CURRENCY,
                entry_fee=ENTRY_FEE,
                prize_percent=PRIZE_PERCENT,

                total_players=total_players,
                pending_count=pending_count,
                total_credit=total_credit,
                game_cards_count=game_cards_count,

                # GoodBingo information.
                good_game=good_game,
                good_cards_count=good_cards_count,
                good_drawn=good_drawn,

                # SuperBingo information.
                super_game=super_game,
                super_cards_count=super_cards_count,
                super_drawn=super_drawn,
            )

    except Exception:

        log.exception("Admin dashboard error.")

        return "Dashboard temporarily unavailable.", 500


# =====================================
# START NEW ROOM GAME
# =====================================

@app.post("/admin/start")
@admin_required
def start_game():

    try:

        fee = int(
            request.form.get("entry_fee", ENTRY_FEE)
        )

        pct = int(
            request.form.get("prize_percent", PRIZE_PERCENT)
        )

        if fee not in VALID_ROOM_FEES:
            raise ValueError("Only 10 ETB and 50 ETB rooms are allowed.")

        if not 0 <= pct <= 100:
            raise ValueError("Invalid prize percentage.")

    except (ValueError, TypeError):

        flash("እባክዎ ትክክለኛ የጨዋታ መረጃ ያስገቡ።")

        return redirect(url_for("dashboard"))

    try:

        with SessionLocal() as db:

            # Check only the selected room.
            active = get_active_game(db, fee)

            room = get_room_name(fee)

            if active:

                flash(f"{room} አስቀድሞ ንቁ ነው።")

            else:

                new_game = Game(
                    status="active",
                    entry_fee=fee,
                    prize_percent=pct,
                    prize_pool=0,
                    drawn_numbers="[]",
                )

                db.add(new_game)
                db.commit()

                log.info(
                    "%s started. Game ID: %s",
                    room,
                    new_game.id,
                )

                flash(f"{room} ጨዋታ ተጀምሯል።")

    except Exception:

        log.exception("Could not start new room game.")

        flash("ጨዋታውን መጀመር አልተቻለም።")

    return redirect(url_for("dashboard"))


# =====================================
# DRAW NUMBER FOR SELECTED ROOM
# =====================================

@app.post("/admin/draw")
@admin_required
def draw_number():

    try:

        fee = int(request.form.get("entry_fee", ""))

        if fee not in VALID_ROOM_FEES:
            raise ValueError("Invalid room.")

    except (ValueError, TypeError):

        flash("እባክዎ ትክክለኛ ክፍል ይምረጡ።")

        return redirect(url_for("dashboard"))

    try:

        with SessionLocal() as db:

            # Retrieve the active game in the selected room.
            game = get_active_game(db, fee)

            room = get_room_name(fee)

            if not game:

                flash(f"{room} ንቁ ጨዋታ የለውም።")

                return redirect(url_for("dashboard"))

            drawn = clean_drawn_numbers(game.drawn_numbers)

            remaining = [
                number
                for number in range(1, 76)
                if number not in drawn
            ]

            if not remaining:

                flash(f"{room}: ሁሉም 75 ቁጥሮች ወጥተዋል።")

            else:

                number = random.SystemRandom().choice(remaining)

                drawn.append(number)

                game.drawn_numbers = json.dumps(drawn)

                db.commit()

                log.info(
                    "%s game %s drew number %s",
                    room,
                    game.id,
                    number,
                )

                flash(f"{room}: አዲስ ቁጥር {number}")

    except Exception:

        log.exception("Number drawing failed.")

        flash("ቁጥር ማውጣት አልተቻለም።")

    return redirect(url_for("dashboard"))


# =====================================
# END SELECTED ROOM GAME
# =====================================

@app.post("/admin/end")
@admin_required
def end_game():

    try:

        fee = int(request.form.get("entry_fee", ""))

        if fee not in VALID_ROOM_FEES:
            raise ValueError("Invalid room.")

    except (ValueError, TypeError):

        flash("እባክዎ ትክክለኛ ክፍል ይምረጡ።")

        return redirect(url_for("dashboard"))

    try:

        with SessionLocal() as db:

            # End only the selected room.
            game = get_active_game(db, fee)

            room = get_room_name(fee)

            if game:

                game.status = "finished"

                db.commit()

                log.info(
                    "%s game %s ended.",
                    room,
                    game.id,
                )

                flash(f"{room} ጨዋታ ተዘግቷል።")

            else:

                flash(f"{room} ንቁ ጨዋታ የለውም።")

    except Exception:

        log.exception("Could not end selected room game.")

        flash("ጨዋታውን መዝጋት አልተቻለም።")

    return redirect(url_for("dashboard"))


# =====================================
# APPROVE DEPOSIT OR WITHDRAWAL
# =====================================

@app.post("/admin/approve/<int:req_id>")
@admin_required
def approve_payment(req_id):

    try:

        with SessionLocal() as db:

            payment = (
                db.query(PaymentRequest)
                .filter_by(
                    id=req_id,
                    status="pending",
                )
                .first()
            )

            if not payment:

                flash("ጥያቄው አልተገኘም ወይም ቀድሞ ተሠርቷል።")

                return redirect(url_for("dashboard"))

            amount = payment.amount
            player_id = payment.player_id
            request_type = get_payment_type(payment)

            if amount <= 0:

                flash("የክፍያው መጠን ትክክል አይደለም።")

                return redirect(url_for("dashboard"))

            if request_type not in ("deposit", "withdrawal"):

                flash("የክፍያ ጥያቄው አይነት አይታወቅም።")

                return redirect(url_for("dashboard"))

            # Atomically change pending to approved.
            result = db.execute(
                update(PaymentRequest)
                .where(
                    PaymentRequest.id == req_id,
                    PaymentRequest.status == "pending",
                )
                .values(status="approved")
            )

            if result.rowcount != 1:

                db.rollback()

                flash("ይህ ጥያቄ ቀድሞ ተሠርቷል።")

                return redirect(url_for("dashboard"))

            if request_type == "deposit":

                result = db.execute(
                    update(Player)
                    .where(Player.id == player_id)
                    .values(balance=Player.balance + amount)
                )

                if result.rowcount != 1:

                    db.rollback()

                    flash("ተጫዋቹ አልተገኘም።")

                    return redirect(url_for("dashboard"))

                db.commit()

                flash(
                    f"የተጫዋች ዴፖዚት #{req_id} ተፈቅዷል። "
                    f"{amount} {CURRENCY} ተጨምሯል።"
                )

            else:

                result = db.execute(
                    update(Player)
                    .where(
                        Player.id == player_id,
                        Player.balance >= amount,
                    )
                    .values(balance=Player.balance - amount)
                )

                if result.rowcount != 1:

                    db.rollback()

                    flash(
                        "የተጫዋቹ ቀሪ ሂሳብ በቂ አይደለም። "
                        "የማውጣት ጥያቄው አልተፈቀደም።"
                    )

                    return redirect(url_for("dashboard"))

                db.commit()

                flash(
                    f"የማውጣት ጥያቄ #{req_id} ተፈቅዷል። "
                    f"{amount} {CURRENCY} ተቀንሷል። "
                    "ክፍያውን በእጅ ወደ ተጫዋቹ መላክ አይርሱ።"
                )

    except Exception:

        log.exception("Payment approval failed.")

        flash("ክፍያውን ማጽደቅ አልተቻለም።")

    return redirect(url_for("dashboard"))


# =====================================
# REJECT DEPOSIT OR WITHDRAWAL
# =====================================

@app.post("/admin/reject/<int:req_id>")
@admin_required
def reject_payment(req_id):

    try:

        with SessionLocal() as db:

            result = db.execute(
                update(PaymentRequest)
                .where(
                    PaymentRequest.id == req_id,
                    PaymentRequest.status == "pending",
                )
                .values(status="rejected")
            )

            if result.rowcount == 1:

                db.commit()

                flash(
                    f"የክፍያ ጥያቄ #{req_id} ውድቅ ተደርጓል።"
                )

            else:

                db.rollback()

                flash(
                    "ጥያቄው አልተገኘም ወይም ቀድሞ ተሠርቷል።"
                )

    except Exception:

        log.exception("Payment rejection failed.")

        flash("ክፍያውን ውድቅ ማድረግ አልተቻለም።")

    return redirect(url_for("dashboard"))


# =====================================
# ADMIN CREDIT MANAGEMENT
# =====================================

@app.post("/admin/credit")
@admin_required
def manage_credit():

    try:

        player_id = int(request.form.get("player_id", ""))
        amount = int(request.form.get("amount", ""))
        action = request.form.get("action", "")

        if player_id <= 0 or amount <= 0:
            raise ValueError

        if action not in ("add", "deduct"):
            raise ValueError

    except (ValueError, TypeError):

        flash("እባክዎ ትክክለኛ የተጫዋች መረጃ ያስገቡ።")

        return redirect(url_for("dashboard"))

    try:

        with SessionLocal() as db:

            if action == "add":

                result = db.execute(
                    update(Player)
                    .where(Player.id == player_id)
                    .values(balance=Player.balance + amount)
                )

                if result.rowcount == 1:

                    db.commit()

                    flash(
                        f"{amount} {CURRENCY} ለተጫዋቹ ተጨምሯል።"
                    )

                else:

                    db.rollback()

                    flash("ተጫዋቹ አልተገኘም።")

            else:

                result = db.execute(
                    update(Player)
                    .where(
                        Player.id == player_id,
                        Player.balance >= amount,
                    )
                    .values(balance=Player.balance - amount)
                )

                if result.rowcount == 1:

                    db.commit()

                    flash(
                        f"{amount} {CURRENCY} ከተጫዋቹ ተቀንሷል።"
                    )

                else:

                    db.rollback()

                    flash(
                        "ተጫዋቹ የለም ወይም በቂ ቀሪ ሂሳብ የለውም።"
                    )

    except Exception:

        log.exception("Player credit management failed.")

        flash("የተጫዋች ክሬዲት ማስተካከል አልተቻለም።")

    return redirect(url_for("dashboard"))


# =====================================
# RUN FLASK WEBSITE
# =====================================

if __name__ == "__main__":

    host = os.getenv("WEB_HOST", "127.0.0.1")
    port = int(os.getenv("WEB_PORT", "5000"))

    app.run(
        host=host,
        port=port,
        debug=False,
        use_reloader=False,
    )
