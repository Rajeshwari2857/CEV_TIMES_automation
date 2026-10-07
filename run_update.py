from POSTS.views import update_market_data
from datetime import datetime
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent
LAST_UPDATE_FILE = BASE_DIR / "last_update.txt"

# Check when the last update happened
if LAST_UPDATE_FILE.exists():
    last_update = datetime.fromisoformat(
        LAST_UPDATE_FILE.read_text()
    )

    hours_passed = (datetime.now() - last_update).total_seconds() / 3600

    # 24 hours havent passed, same data stays
    if hours_passed < 24:
        exit()

# 24 hours have passed, or this is the first run
update_market_data()

# Save the current time
LAST_UPDATE_FILE.write_text(
    datetime.now().isoformat()
)
