# LEDGER — <slug>

Append-only, newest at the bottom. One entry per event. Every claim carries an evidence path
under `evidence/` or a SHA. The hooks also write here.

Entries land through the ledger appender the machine profile names (→ Tools), which writes the
`## YYYY-MM-DD HH:MM — <title>` heading and refuses a body over 25 lines; where the profile
names none, one `Write` append of at most 25 lines in the same shape. A longer story is one
`evidence/<name>.md`, written once, cited here by path. The gate fields
in `run.json` point at these entries and the evidence; they do not repeat them.

## Entry shapes

```
## 2026-09-12 03:14 — U2 gate
- build: <verdict line> · <exit line> · evidence/U2-build.log
- tests: <counts line> · <verdict line> · <exit line> · evidence/U2-test.log
- kind check: equivalence check clean on both moved files · evidence/U2-symbols.txt
- review: HOLD → ADVANCE (attempt 2) · reviews/U2-gate.md
  - F1 fixed, folded into a1b2c3d (old tip 9f8e7d6)
  - F2 rejected: the guard at <file>:214 makes the nil path unreachable
- head: d4e5f6a

## 2026-09-12 03:20 — Assumed
- U3's contract says "the editor" without naming which; took <symbol> (the only one in scope)

## 2026-09-12 03:41 — Parked
- <file>:388 force-unwrap pre-exists; not touched

## 2026-09-12 04:02 — Brief corrections
- brief said 12 call sites for `reload()`; worktree has 14 (two in tests)

## 2026-09-12 06:10 — end-of-stack attempt 2 of 3 at c4d5e6f
- review: HOLD · reviews/end-of-stack-2.md
- F1 fixed 0a1b2c3
- F2 rejected: <file>:88 clamps the index before the read
- F3 deferred: the caller is outside Scope paths; to HANDBACK

## 2026-09-12 06:50 — Comment pass
- classified: 31 lines (24 source, 7 md) · reviews/comment-pass.md
- deleted 6 (change-history 4, roadmap 2) · rewrote 3 · kept 22 · doc claims re-verified 5/5
- folded into b7c8d9e, e0f1a2b (old tip 3c4d5e6) · tree check clean
- tests after fold: <counts line> · <verdict line> · <exit line> · evidence/comment-pass-test.log
- head: f3a4b5c

## 2026-09-12 07:30 — Sweep
| screen | base | tip | verdict |
|---|---|---|---|
| <screen> | 6/6 predicates | 6/6 | pass · evidence/sweep/<screen>.diff.png 0.3% px |
```

---
