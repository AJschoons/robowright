# Changelog

Landed 2026-09-18: the renames; the fresh Lead and per-brief Planner in both handbooks, with
`/planner brief <slug>` as the argument path; the `model` field through brief → `run.json` →
launch; a subagent default model set per session; the four Reviewer and one Reader agent files;
hunks-by-range in the review prompts; `rotate_sessions: true` as the template default;
`run-roster.py --tail` / `--since`; the transcript pin in the cost scripts; `run-cost.py`'s
`per request:` and `by role:` lines, quoted into every unit-close ledger entry; a 1-hour prompt
cache TTL, which a machine's `settings.json` may set. Later the same day: the post-publish watch as
a Lead duty; the delegation tiers (`robowright.json`, the Owner-only floor, `Decided (Lead)`, the
decision review at intake); the Planner's `rebrief` and `review` modes; models per role within
floors; the Explainer (explainer) with its two modes.

Landed 2026-09-19: every machine fact behind `~/.claude/robowright/profile.md` and every
platform fact behind the project hook; the extension points `skills/robowright/SKILL.md` lists, all but `reviewer.overlay`.

Landed 2026-10-22: `rw-git --dir <path> <form>`, the worktree resolved from `<path>` instead of the working
directory, through the same checks, since a `cd` outside a desktop-app session's folders does not stick;
`rw-git where`, printing the worktree, repository, git directory, kind and HEAD it resolved; and
`rw-git switch --detach <full id>`, with `switch <branch>` as the way back.

Landed 2026-10-23: every `rw-git switch` form passes `--no-overwrite-ignore`, so a switch that would replace an
ignored file the target tracks exits 1 instead; and on an install whose `launch.json` sets `unit.ticket_regex`, work
with no tracker key is briefed and launched, its unit id the session directory's name, and built directly from a
plain `--slug`.

Landed 2026-10-24: `accept.sh`'s teardown line deletes every unit branch of a stacked session, `robowright/<slug>`
and each `robowright/<slug>-u<N>` the integrated tip holds, where it named only the top unit's; a unit branch holding a
commit the tip lacks is printed as `kept` instead.

Landed 2026-10-25: `robowright-resolve.py` reads a project folder through its `robowright.json` `repos` when the
folder sits inside another repository's checkout, such as a projects root kept in git, instead of resolving the
enclosing checkout and refusing for want of a hook for its origin; a checkout's own root still resolves as that
checkout.
