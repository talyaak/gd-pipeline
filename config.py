import os

from dotenv import load_dotenv

load_dotenv()

ANTHROPIC_API_KEY = os.environ.get("ANTHROPIC_API_KEY", "")

# Which backend pipeline/llm.py talks to: "anthropic" (direct Anthropic API) or
# "openrouter". Swap by setting LLM_PROVIDER in .env — no code changes needed.
LLM_PROVIDER = os.environ.get("LLM_PROVIDER", "anthropic").strip().lower()

# Model names are provider-specific (OpenRouter uses "anthropic/claude-sonnet-4"
# style slugs; direct Anthropic uses its own dated model IDs), so each provider
# gets its own pair rather than one GENERATION_MODEL that only works for one of them.
GENERATION_MODEL_ANTHROPIC = os.environ.get("GENERATION_MODEL_ANTHROPIC", "claude-sonnet-4-5-20250929")
REVIEW_MODEL_ANTHROPIC = os.environ.get("REVIEW_MODEL_ANTHROPIC", "claude-haiku-4-5-20251001")
GENERATION_MODEL_OPENROUTER = os.environ.get("GENERATION_MODEL_OPENROUTER", "anthropic/claude-sonnet-4")
REVIEW_MODEL_OPENROUTER = os.environ.get("REVIEW_MODEL_OPENROUTER", "anthropic/claude-3-haiku")

MAX_DESIGN_ATTEMPTS = int(os.environ.get("MAX_DESIGN_ATTEMPTS", "3"))
MAX_CODE_ATTEMPTS = int(os.environ.get("MAX_CODE_ATTEMPTS", "3"))

OUTPUT_DIR = os.environ.get("OUTPUT_DIR", "output")

# Human taste-check on the GDD before spending tokens on spec+code. Off by default
# is only advisable once execution validation is trusted; on by default for now.
HUMAN_REVIEW_GDD = os.environ.get("HUMAN_REVIEW_GDD", "true").lower() in ("1", "true", "yes")

RETRY_MAX_ATTEMPTS = int(os.environ.get("RETRY_MAX_ATTEMPTS", "3"))
RETRY_BASE_DELAY_SECONDS = float(os.environ.get("RETRY_BASE_DELAY_SECONDS", "2"))

# 16000 was cutting off complex genres mid-function (mini-boss/wave-spawning code
# missing entirely), which the LLM reviewer kept flagging as "truncated". Sonnet
# supports 8192 output tokens max; 48000 triggered OpenRouter fallback to free models.
# Use 8192 to stay on the intended model (claude-sonnet-4).
CODEGEN_MAX_TOKENS = int(os.environ.get("CODEGEN_MAX_TOKENS", "8192"))
