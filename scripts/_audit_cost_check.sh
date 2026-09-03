cd /workspace
VENV=/tmp/venv_seed
if [ ! -x "$VENV/bin/python" ]; then
  uv venv "$VENV" --python 3.13 --clear && uv pip install --python "$VENV/bin/python" langgraph langgraph-checkpoint-sqlite langchain-anthropic langchain-openai langchain-core pydantic python-dotenv
fi
PYTHONPATH=/workspace "$VENV/bin/python" pipeline/cost_tracker.py 24
