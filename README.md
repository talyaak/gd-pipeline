# gd-gpt

Multi-agent pipeline that turns a game genre/concept into a playable, single-file
HTML5 browser game (Phaser 3, no external assets), and proves the result actually
runs before calling it done.

## Why this exists

The predecessor project (`gd-pipeline`) generated games through a similar staged
LLM pipeline but never once executed the output — "done" meant "an LLM reviewer
liked the code." This project's core addition is a headless-browser execution
harness (`pipeline/execute.py`) that loads every generated game in real Chromium,
captures console/runtime errors, confirms the canvas actually renders, and checks
that input produces an observable effect. That evidence, not an LLM's opinion, is
the primary pass/fail gate.

## Pipeline

```
research -> design (GDD) -> [human review, configurable] -> spec -> codegen
  -> validate (static regex + browser execution)
  -> review (LLM, informed by execution evidence)
  -> pass, or bounded rework loop back to codegen
```

A run that exhausts its rework attempts ends with an explicit `failed_max_attempts`
status and the last execution report attached — it never silently ships a broken
or low-quality game.

## Setup

```
py -3.12 -m venv .venv
.venv/Scripts/pip install -e ".[dev]"
.venv/Scripts/python -m playwright install chromium
cp .env.example .env   # fill in ANTHROPIC_API_KEY
```

## Usage

```
python -m pipeline "endless runner"
```

By default this pauses once for a human approval gate on the Game Design Document
(set `HUMAN_REVIEW_GDD=false` in `.env` to run fully headless). The run's full
history — every attempt's code, execution report, and screenshots — lands under
`output/<run>/`, and the final playable file is `output/<run>/game.html`.

## Tests

```
python -m pytest
```

No live API calls required — LLM calls are mocked in tests; the deterministic
validator and the real Playwright execution harness are exercised directly.
