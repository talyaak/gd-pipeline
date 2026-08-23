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

# Human taste-check on the GDD before spending tokens on spec+code. Off by default
# is only advisable once execution validation is trusted; on by default for now.
HUMAN_REVIEW_GDD = os.environ.get("HUMAN_REVIEW_GDD", "true").lower() in ("1", "true", "yes")

RETRY_MAX_ATTEMPTS = int(os.environ.get("RETRY_MAX_ATTEMPTS", "3"))
RETRY_BASE_DELAY_SECONDS = float(os.environ.get("RETRY_BASE_DELAY_SECONDS", "2"))

# 16000 was cutting off complex genres mid-function (mini-boss/wave-spawning code
# missing entirely), which the LLM reviewer kept flagging as "truncated". Sonnet
# supports far higher output; give codegen real headroom.
CODEGEN_MAX_TOKENS = int(os.environ.get("CODEGEN_MAX_TOKENS", "48000"))
