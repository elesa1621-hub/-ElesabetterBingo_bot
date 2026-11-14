
import os
import shutil
import logging
from datetime import datetime

from sqlalchemy import (
    create_engine,
    Column,
    Integer,
    String,
    Boolean,
    Text,
    DateTime,
    ForeignKey,
    Index,
    inspect,
    text,
)
from sqlalchemy.orm import (
    declarative_base,
    sessionmaker,
    relationship,
)

from config import DATABASE_URL


# ==========================================
# LOGGING
# ==========================================

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("TrustBINGO.database")


# ==========================================
# DATABASE CONNECTION
# ==========================================

Base = declarative_base()

connect_args = {}

if DATABASE_URL.startswith("sqlite"):
    connect_args = {"check_same_thread": False}

engine = create_engine(
    DATABASE_URL,
    connect_args=connect_args,
    pool_pre_ping=True,
)

SessionLocal = sessionmaker(
    autocommit=False,
    autoflush=False,
    bind=engine,
)


# ==========================================
# PLAYER MODEL
# ==========================================

class Player(Base):

    __tablename__ = "players"

    id = Column(Integer, primary_key=True, index=True)

    telegram_id = Column(
        String(40),
        unique=True,
        nullable=False,
        index=True,
    )

    username = Column(String(100), nullable=True)
    full_name = Column(String(200), nullable=True)
    phone_number = Column(String(30), nullable=True)

    balance = Column(Integer, default=0, nullable=False)

    created_at = Column(
        DateTime,
        default=datetime.utcnow,
    )

    cards = relationship(
        "BingoCard",
        back_populates="player",
    )

    payment_requests = relationship(
        "PaymentRequest",
        back_populates="player",
    )


# ==========================================
# GAME MODEL
# ==========================================

class Game(Base):

    __tablename__ = "games"

    id = Column(Integer, primary_key=True, index=True)

    status = Column(
        String(30),
        default="waiting",
        nullable=False,
    )

    # 10 ETB = GoodBingo
    # 50 ETB = SuperBingo
    entry_fee = Column(
        Integer,
        default=10,
        nullable=False,
    )

    prize_pool = Column(
        Integer,
        default=0,
        nullable=False,
    )

    prize_percent = Column(
        Integer,
        default=80,
        nullable=False,
    )

    drawn_numbers = Column(
        Text,
        default="[]",
    )

    created_at = Column(
        DateTime,
        default=datetime.utcnow,
    )

    cards = relationship(
        "BingoCard",
        back_populates="game",
    )


# Index allows efficient lookup of active games by room fee.
Index(
    "ix_games_status_entry_fee",
    Game.status,
    Game.entry_fee,
)


# ==========================================
# BINGO CARD MODEL
# ==========================================

class BingoCard(Base):

    __tablename__ = "cards"

    id = Column(Integer, primary_key=True, index=True)

    game_id = Column(
        Integer,
        ForeignKey("games.id"),
        nullable=False,
        index=True,
    )

    player_id = Column(
        Integer,
        ForeignKey("players.id"),
        nullable=False,
        index=True,
    )

    grid_json = Column(
        Text,
        nullable=False,
    )

    claimed = Column(
        Boolean,
        default=False,
        nullable=False,
    )

    created_at = Column(
        DateTime,
        default=datetime.utcnow,
    )

    game = relationship(
        "Game",
        back_populates="cards",
    )

    player = relationship(
        "Player",
        back_populates="cards",
    )


# ==========================================
# PAYMENT REQUEST MODEL
# ==========================================

class PaymentRequest(Base):

    __tablename__ = "payment_requests"

    id = Column(Integer, primary_key=True, index=True)

    player_id = Column(
        Integer,
        ForeignKey("players.id"),
        nullable=False,
        index=True,
    )

    amount = Column(
        Integer,
        nullable=False,
    )

    reference = Column(
        String(120),
        nullable=True,
    )

    # deposit or withdrawal
    request_type = Column(
        String(30),
        default="deposit",
        nullable=False,
    )

    # pending, approved, rejected
    status = Column(
        String(30),
        default="pending",
        nullable=False,
    )

    created_at = Column(
        DateTime,
        default=datetime.utcnow,
    )

    player = relationship(
        "Player",
        back_populates="payment_requests",
    )


# ==========================================
# DATABASE BACKUP
# ==========================================

def backup_database():

    if not DATABASE_URL.startswith("sqlite:///"):
        logger.info("SQLite backup skipped.")
        return

    db_path = DATABASE_URL.replace(
        "sqlite:///",
        "",
        1,
    )

    if not os.path.isabs(db_path):

        db_path = os.path.join(
            os.path.dirname(os.path.abspath(__file__)),
            db_path,
        )

    if not os.path.exists(db_path):
        logger.info("No existing database to back up.")
        return

    backup_path = (
        db_path
        + ".backup_"
        + datetime.now().strftime("%Y%m%d_%H%M%S")
    )

    shutil.copy2(db_path, backup_path)

    logger.info(
        "Database backup created: %s",
        backup_path,
    )


# ==========================================
# DATABASE MIGRATION
# ==========================================

def add_missing_column(connection, table, column, definition):

    inspector = inspect(connection)

    if not inspector.has_table(table):
        return

    existing_columns = {
        col["name"]
        for col in inspector.get_columns(table)
    }

    if column not in existing_columns:

        connection.execute(
            text(
                f"ALTER TABLE {table} "
                f"ADD COLUMN {column} {definition}"
            )
        )

        logger.info(
            "Added column %s to table %s",
            column,
            table,
        )


def update_database():

    """
    Add missing columns to existing databases.
    Existing players, games, cards, and payments are preserved.
    """

    with engine.begin() as connection:

        # Players
        add_missing_column(
            connection,
            "players",
            "phone_number",
            "VARCHAR(30)",
        )

        add_missing_column(
            connection,
            "players",
            "balance",
            "INTEGER NOT NULL DEFAULT 0",
        )

        # Games
        add_missing_column(
            connection,
            "games",
            "entry_fee",
            "INTEGER NOT NULL DEFAULT 10",
        )

        add_missing_column(
            connection,
            "games",
            "prize_pool",
            "INTEGER NOT NULL DEFAULT 0",
        )

        add_missing_column(
            connection,
            "games",
            "prize_percent",
            "INTEGER NOT NULL DEFAULT 80",
        )

        add_missing_column(
            connection,
            "games",
            "drawn_numbers",
            "TEXT DEFAULT '[]'",
        )

        # Cards
        add_missing_column(
            connection,
            "cards",
            "claimed",
            "BOOLEAN NOT NULL DEFAULT 0",
        )

        # Payment requests
        add_missing_column(
            connection,
            "payment_requests",
            "request_type",
            "VARCHAR(30) NOT NULL DEFAULT 'deposit'",
        )

        add_missing_column(
            connection,
            "payment_requests",
            "status",
            "VARCHAR(30) NOT NULL DEFAULT 'pending'",
        )

    # Create the room lookup index if it does not exist.
    Index(
        "ix_games_status_entry_fee",
        Game.status,
        Game.entry_fee,
    ).create(bind=engine, checkfirst=True)


# ==========================================
# DATABASE VALIDATION
# ==========================================

def validate_database():

    inspector = inspect(engine)

    required_tables = [
        "players",
        "games",
        "cards",
        "payment_requests",
    ]

    for table in required_tables:

        if not inspector.has_table(table):

            raise RuntimeError(
                f"Missing database table: {table}"
            )

    game_columns = {
        col["name"]
        for col in inspector.get_columns("games")
    }

    if "entry_fee" not in game_columns:

        raise RuntimeError(
            "Game entry_fee column is missing."
        )

    payment_columns = {
        col["name"]
        for col in inspector.get_columns("payment_requests")
    }

    if "request_type" not in payment_columns:

        raise RuntimeError(
            "Payment request_type column is missing."
        )

    logger.info("Database validation successful.")


# ==========================================
# INITIALIZE DATABASE
# ==========================================

def initialize_database():

    backup_database()

    Base.metadata.create_all(bind=engine)

    update_database()

    validate_database()

    logger.info(
        "TrustBINGO database initialized successfully."
    )


initialize_database()


# ==========================================
# DATABASE SESSION HELPER
# ==========================================

def get_db():

    db = SessionLocal()

    try:
        yield db

    finally:
        db.close()
