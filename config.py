
import os
from pathlib import Path
from dotenv import load_dotenv
# =====================================
# PROJECT DIRECTORY
# =====================================
BASE_DIR = Path(__file__).resolve().parent

# Load environment variables from the project folder
load_dotenv(BASE_DIR / ".env")
# =====================================
# TELEGRAM BOT SETTINGS
# =====================================

BOT_TOKEN = os.getenv("BOT_TOKEN", "").strip()

if not BOT_TOKEN:
    raise RuntimeError(
        "BOT_TOKEN is missing. Add it to your .env file."
    )

# =====================================
# DATABASE SETTINGS
# =====================================

# Default database is inside the TrustBINGO project folder
DEFAULT_DATABASE_PATH = BASE_DIR / "trustbingo.db"

DATABASE_URL = os.getenv("DATABASE_URL", "").strip()

if not DATABASE_URL:
    DATABASE_URL = "sqlite:///" + DEFAULT_DATABASE_PATH.as_posix()

# Resolve relative SQLite database paths against BASE_DIR.
if DATABASE_URL.startswith("sqlite:///"):
    sqlite_path = DATABASE_URL[len("sqlite:///"):]

    if sqlite_path != ":memory:":
        path = Path(sqlite_path)

        if not path.is_absolute():
            path = (BASE_DIR / path).resolve()

        path.parent.mkdir(parents=True, exist_ok=True)

        DATABASE_URL = "sqlite:///" + path.as_posix()

# =====================================
# ADMIN SETTINGS
# =====================================

ADMIN_PASSWORD = os.getenv(
    "ADMIN_PASSWORD",
    "E1216@2129"
)

if ADMIN_PASSWORD == "ChangeThisStrongPassword":
    print("WARNING: Change the default admin password!")

# =====================================
# GAME SETTINGS
# =====================================

CURRENCY = os.getenv("CURRENCY", "ETB")

ENTRY_FEE = int(os.getenv("ENTRY_FEE", "10"))

PRIZE_PERCENT = int(os.getenv("PRIZE_PERCENT", "80"))

if ENTRY_FEE < 1:
    raise ValueError("ENTRY_FEE must be at least 1.")

if not 0 <= PRIZE_PERCENT <= 100:
    raise ValueError("PRIZE_PERCENT must be between 0 and 100.")

# =====================================
# FLASK SETTINGS
# =====================================

WEB_HOST = os.getenv("WEB_HOST", "127.0.0.1")

WEB_PORT = int(os.getenv("WEB_PORT", "5000"))

SECRET_KEY = os.getenv(
    "SECRET_KEY",
    "replace-this-secret-key"
)

if SECRET_KEY == "replace-this-secret-key":
    print("WARNING: Set a secure SECRET_KEY in your .env file.")

# =====================================
# DISPLAY DATABASE LOCATION
# =====================================
print("TrustBINGO configuration loaded.")
print("Database URL:", DATABASE_URL)
print("Project directory:", BASE_DIR)
