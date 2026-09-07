#!/usr/bin/env python3
"""Deterministic priority-queue runner for the gd-pipeline-fix subagent swarm.

Mirrors scripts/quota_guard.sh's philosophy: pure state/git inspection on a
schedule, no LLM self-judgment about progress or success. Run on a timer
(see the gd-pipeline-agent-queue Task Scheduler job) -- each invocation does
one tick: reap finished agents (by git commit presence, not by asking an LLM
"did you succeed"), then launch up to MAX_CONCURRENT new ones from the
priority queue, respecting quota health and file-ownership lock groups.

State lives in /tmp/agent_queue_state.json (container-local, not committed --
it's process bookkeeping, not project data).
"""
import json
import os
import re
import subprocess
import time
from pathlib import Path

WORKSPACE = Path("/workspace")
PROMPTS_DIR = Path("/tmp/prompts")
LOGS_DIR = Path("/tmp/agent-logs2")
STATE_FILE = Path("/tmp/agent_queue_state.json")
QUEUE_LOG = Path("/tmp/agent_queue.log")

MAX_CONCURRENT = 3
MAX_ATTEMPTS = 3
RATE_LIMIT_LOG = Path.home() / ".hermes" / "logs" / "agent.log"
RATE_LIMIT_THRESHOLD = 15  # same threshold quota_guard.sh uses to pause the cron

# Deterministic priority order. Lower number = higher priority. Ties broken
# by list order. Task 10 (integration-adversarial) is gated separately below,
# its priority number is irrelevant to that gate.
QUEUE = [
    {"name": "reskin-noop-fix", "priority": 1, "lock": None},
    {"name": "research-design-fallbacks", "priority": 1, "lock": None},
    {"name": "spec-visualspec-fallbacks", "priority": 1, "lock": None},
    {"name": "execute-cta-check", "priority": 2, "lock": None},
    {"name": "validate-execute-gzip-gate", "priority": 2, "lock": None},
    {"name": "playability-skip-status", "priority": 3, "lock": "playability_agent.py"},
    {"name": "playability-parser-fixtures", "priority": 3, "lock": "playability_agent.py"},
    {"name": "cli-docs-cleanup", "priority": 4, "lock": None},
    {"name": "cost-repair-metrics", "priority": 4, "lock": None},
    {"name": "integration-adversarial", "priority": 5, "lock": None, "gate_on_rest": True},
]

TASK_NAMES = [t["name"] for t in QUEUE]


def sh(cmd, cwd=None):
    return subprocess.run(cmd, shell=True, cwd=cwd, capture_output=True, text=True)


def load_state():
    if STATE_FILE.exists():
        return json.loads(STATE_FILE.read_text())
    state = {}
    for t in QUEUE:
        state[t["name"]] = {"status": "pending", "attempts": 0, "pid": None}
    return state


def save_state(state):
    STATE_FILE.write_text(json.dumps(state, indent=2))


def log(msg):
    ts = subprocess.run(["date", "-u", "+%Y-%m-%d %H:%M:%S"], capture_output=True, text=True).stdout.strip()
    line = f"{ts} | {msg}"
    print(line)
    with QUEUE_LOG.open("a") as f:
        f.write(line + "\n")


def worktree_path(name):
    return Path(f"/tmp/wt-agent-{name}")


def has_commit(name):
    wt = worktree_path(name)
    if not wt.exists():
        return False
    r = sh("git log --oneline main..HEAD", cwd=wt)
    return bool(r.stdout.strip())


def has_uncommitted_changes(name):
    wt = worktree_path(name)
    if not wt.exists():
        return False
    r = sh("git status --porcelain", cwd=wt)
    return bool(r.stdout.strip())


def pid_alive(pid):
    if pid is None:
        return False
    return Path(f"/proc/{pid}").exists()


def find_running_pid_for(name):
    """Match a live hermes process to a task by its /proc/<pid>/cwd target."""
    wt = str(worktree_path(name).resolve())
    proc_dir = Path("/proc")
    for p in proc_dir.iterdir():
        if not p.name.isdigit():
            continue
        try:
            cwd_link = os.readlink(p / "cwd")
        except (OSError, PermissionError):
            continue
        if cwd_link != wt:
            continue
        try:
            cmdline = (p / "cmdline").read_bytes().replace(b"\x00", b" ").decode(errors="replace")
        except OSError:
            continue
        if "hermes" in cmdline and "-z" in cmdline:
            return int(p.name)
    return None


def rate_limit_hits_today():
    if not RATE_LIMIT_LOG.exists():
        return 0
    today = subprocess.run(["date", "-u", "+%Y-%m-%d"], capture_output=True, text=True).stdout.strip()
    count = 0
    with RATE_LIMIT_LOG.open(errors="replace") as f:
        for line in f:
            if line.startswith(today) and "Rate limit exceeded" in line:
                count += 1
    return count


def reap(state):
    """Deterministic completion check: alive process? real commit? terminal state."""
    for name, s in state.items():
        if s["status"] != "running":
            continue
        pid = s.get("pid")
        if pid_alive(pid):
            continue  # still running, nothing to do
        # process is gone -- classify by git state only, never by re-reading its log for "success"
        if has_commit(name):
            s["status"] = "done"
            log(f"{name}: process ended, real commit found -> done")
        else:
            s["attempts"] += 1
            if s["attempts"] >= MAX_ATTEMPTS:
                s["status"] = "stuck"
                log(f"{name}: process ended, no commit, attempts={s['attempts']} >= {MAX_ATTEMPTS} -> stuck (needs human)")
            else:
                s["status"] = "pending"
                log(f"{name}: process ended, no commit, attempts={s['attempts']} -> requeued")
        s["pid"] = None


def currently_running(state):
    return [n for n, s in state.items() if s["status"] == "running"]


def active_lock_groups(state):
    groups = set()
    for t in QUEUE:
        if state[t["name"]]["status"] == "running" and t["lock"]:
            groups.add(t["lock"])
    return groups


def rest_are_terminal(state, exclude):
    terminal = {"done", "stuck"}
    for t in QUEUE:
        if t["name"] == exclude:
            continue
        if state[t["name"]]["status"] not in terminal:
            return False
    return True


def pick_next(state):
    running = set(currently_running(state))
    locked = active_lock_groups(state)
    candidates = sorted(
        (t for t in QUEUE if state[t["name"]]["status"] == "pending"),
        key=lambda t: t["priority"],
    )
    for t in candidates:
        name = t["name"]
        if t.get("gate_on_rest") and not rest_are_terminal(state, exclude=name):
            continue  # integration-adversarial waits for 1-9
        if t["lock"] and t["lock"] in locked:
            continue  # same-file mutex held by a running sibling
        return t
    return None


def launch(name, state):
    wt = worktree_path(name)
    prompt_file = PROMPTS_DIR / f"{name}.md"
    log_file = LOGS_DIR / f"{name}.log"
    prompt_text = prompt_file.read_text()
    if has_uncommitted_changes(name):
        prompt_text = (
            "NOTE: a previous attempt at this exact task left uncommitted changes "
            "in this worktree. Run `git status` and `git diff` FIRST. If the existing "
            "work is on the right track, continue and finish it. If it's flawed, fix "
            "it. If it's unsalvageable, `git checkout -- .` (and remove any stray new "
            "files it added) to start clean -- do not blindly duplicate correct work "
            "already done.\n\n"
        ) + prompt_text
        tmp_prompt = Path(f"/tmp/prompts/{name}.resume.md")
        tmp_prompt.write_text(prompt_text)
        prompt_file = tmp_prompt

    cmd = (
        f'nohup hermes -z "$(cat {prompt_file})" --accept-hooks --yolo '
        f'> {log_file} 2>&1 & echo $!'
    )
    r = subprocess.run(["bash", "-lc", cmd], cwd=wt, capture_output=True, text=True)
    pid_line = r.stdout.strip().splitlines()[-1] if r.stdout.strip() else ""
    pid = int(pid_line) if pid_line.isdigit() else None
    state[name]["status"] = "running"
    state[name]["pid"] = pid
    log(f"{name}: launched (pid={pid}, attempt {state[name]['attempts'] + 1})")


def main():
    LOGS_DIR.mkdir(parents=True, exist_ok=True)
    state = load_state()
    # make sure state has entries for every task (in case QUEUE changed)
    for t in QUEUE:
        state.setdefault(t["name"], {"status": "pending", "attempts": 0, "pid": None})

    reap(state)

    hits = rate_limit_hits_today()
    if hits >= RATE_LIMIT_THRESHOLD:
        log(f"quota check: {hits} rate-limit hits today >= threshold {RATE_LIMIT_THRESHOLD} -- not launching new agents this tick")
        save_state(state)
        return

    running = currently_running(state)
    slots = MAX_CONCURRENT - len(running)
    launched_this_tick = 0
    while slots > 0:
        nxt = pick_next(state)
        if nxt is None:
            break
        launch(nxt["name"], state)
        slots -= 1
        launched_this_tick += 1

    if launched_this_tick == 0 and not running:
        pending = [n for n, s in state.items() if s["status"] == "pending"]
        stuck = [n for n, s in state.items() if s["status"] == "stuck"]
        done = [n for n, s in state.items() if s["status"] == "done"]
        if not pending and not stuck:
            log(f"queue complete: {len(done)}/{len(QUEUE)} done, nothing left to run")
        elif stuck:
            log(f"queue stalled: {len(stuck)} task(s) stuck after {MAX_ATTEMPTS} attempts: {stuck} -- needs human review")

    save_state(state)


if __name__ == "__main__":
    main()
