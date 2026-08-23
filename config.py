import os

from dotenv import load_dotenv

load_dotenv()

ANTHROPIC_API_KEY = os.environ.get("ANTHROPIC_API_KEY", "")

# Generation is the harder job (writing a full game); review/judgment tasks
# are cheaper to run on a smaller/faster model. Keep these separately
# configurable so a model swap is a deployment decision, not a code edit.
GENERATION_MODEL = os.environ.get("GENERATION_MODEL", "claude-sonnet-4-5-20250929")
REVIEW_MODEL = os.environ.get("REVIEW_MODEL", "claude-haiku-4-5-20251001")

MAX_DESIGN_ATTEMPTS = int(os.environ.get("MAX_DESIGN_ATTEMPTS", "3"))
MAX_CODE_ATTEMPTS = int(os.environ.get("MAX_CODE_ATTEMPTS", "2"))

OUTPUT_DIR = os.environ.get("OUTPUT_DIR", "output")
