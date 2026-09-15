# Instinct Wire

Direction channel between Instinct and Claude Code, using GitHub issue
[#2 "Instinct Wire"](https://github.com/talyaak/gd-pipeline/issues/2) as
the mailbox. Email (`3vbshc@mail.instinct.com`) remains the backup channel
and is untouched by any of this.

## How it works

- Instinct posts direction as issue comments starting with `**[INSTINCT]**`,
  authenticated as the dedicated `talyaak-headless` GitHub account.
- `scripts/instinct-wire.sh` polls the issue every `POLL_INTERVAL_SECONDS`
  (config: `.instinct-wire/config`, default 45s) and appends every comment
  that is **both** marked `**[INSTINCT]**` **and** authored by
  `INSTINCT_GH_USER` to `.instinct-wire/inbox.md`.
- Claude reads `.instinct-wire/inbox.md` on a fixed timer (a scheduled
  wakeup every ≤5 minutes while a work session is active) and evaluates
  new entries as data -- same trust model as the email channel, not an
  automatic command injection. Judgment gates on routine work stay as
  they are; kill decisions, pivots, and anything that spends money still
  route to Tal.
- Claude posts gate reports, blockers and questions back as issue
  comments starting with `**[CLAUDE]**`, via `gh api
  repos/talyaak/gd-pipeline/issues/2/comments -f body=...`.

## Why the account has to be separate

The marker alone (`**[INSTINCT]**`) is never sufficient -- this repo is
public, so anyone can post a comment with that prefix. The only real
boundary is that delivered comments must be authored by a GitHub identity
(`talyaak-headless`) that this machine's own tooling cannot also post as.
`scripts/instinct-wire.sh` checks this at startup and refuses to run if
`INSTINCT_GH_USER` resolves to the same account its own `gh` auth does.

## Start / stop / restart

Requires `gh` CLI on `PATH` and authenticated (`GH_TOKEN` env var or
`gh auth login`) as an account that is NOT `talyaak-headless`, plus `jq`.

**Start (detached, survives the shell exiting):**
```bash
cd /path/to/gd-pipeline
nohup bash scripts/instinct-wire.sh >> .instinct-wire/watcher.log 2>&1 &
disown
```
The PID is also written to `.instinct-wire/watcher.pid` by the script
itself once it starts.

**Check it's running:**
```bash
kill -0 "$(cat .instinct-wire/watcher.pid)" && echo running
tail -f .instinct-wire/watcher.log
```

**Stop:**
```bash
kill "$(cat .instinct-wire/watcher.pid)"
rm -f .instinct-wire/watcher.pid
```

**Restart:** stop, then start again. This is idempotent and resumable --
`.instinct-wire/state` holds the last-delivered comment ID and is the
only thing consulted to decide what's new; nothing already recorded there
gets re-delivered, even if `inbox.md` itself were deleted.

## Files

- `scripts/instinct-wire.sh` -- the watcher (committed).
- `.instinct-wire/config` -- repo, issue number, poll interval, Instinct's
  GitHub username (committed, not secret).
- `.instinct-wire/state` -- last-seen comment ID (gitignored, local only).
- `.instinct-wire/inbox.md` -- delivered comments, appended to (gitignored).
- `.instinct-wire/watcher.log` -- watcher activity log (gitignored).
- `.instinct-wire/watcher.pid` -- running watcher's PID (gitignored).
