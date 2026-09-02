# Genre library

Validated game design docs (GDDs), one directory per genre, reusable across runs.

**Rule: check here before generating a new GDD for a genre.** research→design→spec
is reliable on free-tier models (confirmed 2026-09-02: every free-tier model tested
passed these three stages; only codegen failed). Design quality doesn't degrade by
regenerating, so there's no reason to burn request budget re-deriving a GDD for a
genre that already has one here — read the existing file(s) instead.

## Layout

```
genre_library/<genre_slug>/gdd_v1.json   # ImplementationSpec-ready GameDesignDocument
genre_library/<genre_slug>/gdd_v2.json   # optional additional variants
```

A genre with 2-3 stored variants is enough; stop generating new ones for it and
move to a genre with zero.

## What's seeded here (2026-09-02)

`bullet_hell_shmup`, `endless_runner`, `match_3_puzzle`, `tower_defense` each have
one GDD pulled from a real pipeline run and manually read/confirmed as genuinely
well-specified (concrete mechanics, real juice list, clear win/lose condition) —
see the design taxonomy discussion the same day. `idle_clicker` is an empty
placeholder — genre confirmed as a target, no validated GDD yet.

## What this does NOT cover

Code. Every genre here failed at codegen on free-tier models and produced
structurally-fine-but-content-thin output even on the paid model (see
`/workspace/STRATEGY.md`). A stored GDD is a *design* asset, not a shippable game —
building the actual playable game for a genre is a hand-authored-harness task
(see `/workspace/harness/`), not something to regenerate from these GDDs via the
old codegen pipeline.
