"""Fixed numbers from SPEC.md. Constants, not settings (SPEC §13)."""

from packages.algo_tutor.domain.enums import Difficulty

# Training ladder (SPEC §7.1).
START_LEVEL = 1300
K_FACTOR = 32
FLOOR_LEVEL = 1000

# Target rating (SPEC §7.3, §13).
DEFAULT_TARGET = 1850
TARGET_MIN = 1200
TARGET_MAX = 2600
TARGET_STEP = 50

# "On time" budgets in seconds, by label; no label gets 25 minutes (SPEC §7.2).
TIME_BUDGET_SECONDS: dict[Difficulty | None, int] = {
    Difficulty.EASY: 15 * 60,
    Difficulty.MEDIUM: 25 * 60,
    Difficulty.HARD: 40 * 60,
    None: 25 * 60,
}

# Ratings (SPEC §5.5).
LABEL_MEDIAN_RATING: dict[Difficulty, int] = {
    Difficulty.EASY: 1252,
    Difficulty.MEDIUM: 1648,
    Difficulty.HARD: 2262,
}
RIDGE_LAMBDA = 5.0
RIDGE_MIN_ROWS = 50
RIDGE_FOLDS = 5
ACCEPTANCE_CLAMP = (1.0, 99.0)  # percent, before logit

# Problem bank (SPEC §5.4).
BANK_CAP = 2000
BANK_PAGE_SIZE = 100
BANK_PAGE_DELAY_SECONDS = 0.3
MAX_SOURCE_TAGS = 30

# Review intervals in days (SPEC §8.1).
REPAIR_DAYS = 1
RECONSTRUCTION_DAYS = 3
TRANSFER_DAYS = 7
MIXED_DAYS = 14

# Checks and the shortlist (SPEC §8.3, §10.2).
CHECK_HEADROOM = 150
NEAR_WINDOW = 100
SHORTLIST_PER_TOPIC = 5

# Daily plan (SPEC §10, §13).
QUESTIONS_PER_DAY_DEFAULT = 2
QUESTIONS_PER_DAY_RANGE = (1, 20)
ATCODER_PER_DAY_DEFAULT = 0
ATCODER_PER_DAY_RANGE = (0, 10)

# Stopwatch (SPEC §6.3).
HEARTBEAT_GAP_SECONDS = 120
MAX_ACTIVE_SECONDS = 7 * 24 * 60 * 60

# Limits (SPEC §6.4, §6.5, §6.7, §11, §5.9, §5.10, §18.2).
MAX_CODE_CHARS = 1_000_000
MAX_NOTES_CHARS = 100_000
MAX_TAKEAWAY_CHARS = 2_000
MAX_MISTAKE_LABELS = 3
MAX_NOTEBOOK_CHARS = 1_000_000
MAX_SOLUTION_FILE_BYTES = 1_000_000
MAX_PACK_QUESTIONS = 1000
MAX_TITLE_CHARS = 300
MAX_LIST_ENTRIES = 500
MAX_IDEMPOTENCY_KEY_CHARS = 200

# Backups (SPEC §17).
BACKUPS_KEPT = 7
BACKUP_MAX_AGE_SECONDS = 24 * 60 * 60
