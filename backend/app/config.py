from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[2]
DATA_DIR = PROJECT_ROOT / "backend" / "data"
CRM_FILE = DATA_DIR / "crm_events.json"
CALENDAR_FILE = DATA_DIR / "calendar_events.json"
AUTO_MATCH_THRESHOLD = 0.68
REVIEW_THRESHOLD = 0.50
TIME_TOLERANCE_MINUTES = 90
