# Agent rules

## Notify via ntfy (mandatory)

When you complete a task (or reach a point where you need the user's input/decision), send a push notification via ntfy:

```bash
curl -s -H "Title: <short title>" -H "Priority: default" -d "<one-line summary of what happened>" "https://ntfy.sh/$NTFY_TOPIC"
```

- Use `$NTFY_TOPIC` from `.env` (never hardcode the topic; topics are effectively secrets — anyone who knows the URL can send/receive).
- Fire-and-forget: use `curl -s` with a short timeout (`--max-time 10`) and do not fail the task if the notification fails.
- Send when: a long-running task finishes, a pipeline run completes/fails, or you are blocked waiting for a human decision.
- Do not send more than one notification per user-visible milestone.
