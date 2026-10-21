# Machine profile contract

Robowright's handbooks are machine-agnostic. Everything that differs between one machine (or
one organisation) and another lives in a **machine profile**: one file at
`~/.claude/robowright/profile.md`, read in full by every role at preflight. A handbook that
says "per the profile → Launch" points at a heading below.

No profile installed → refuse to start and say so. Do not guess a default.

The profile provides these sections, in this order, each copy-pasteable by an agent with no
other context. A section that does not apply says `None on this machine.` — it is never omitted.

1. **Identity** — whose machine, which organisation if any, and who the Owner is. The repos
   Robowright works in are the hooks on this Mac, whatever `robowright-resolve` finds —
   `~/.claude/robowright/projects/*.md` plus any checkout's own `.claude/robowright/project.md`.
2. **Launch** — how a role's session is started and resumed on this machine, by whom, and from
   which runtime; how a pasted line reaches a shell that can start a session here, and what a
   shell needs for the `auto` launch mode (the mode itself is `launch.json`'s, `paste` or `auto`,
   not the profile's); the exact command shapes,
   including rotation at a unit boundary, stopping a live session, and the first prompt a
   resumed session receives; how the Lead observes and messages a live Robowright Session;
   concurrency limits.
3. **Budget** — what a Robowright Session's budget is measured in (plan-usage percent, dollars,
   wall hours), which fields the brief carries, which script or tool enforces it, what the
   cost line in a ledger entry quotes, and the ceiling on the Lead's own session before it
   hands off to a fresh one; and whether the estimated USD a report prints means anything here.
   The prices behind it are one file, `skills/robowright/pricing.json`, which the Owner
   maintains. A record in the accounting ledger holds one Claude session's
   requests, tokens by class, estimated USD and the pricing date behind it, wall and active
   seconds, and the latest plan-usage reading, per role and model; a `unit`-scope record holds
   the same for one unit's window.
4. **Tools** — the commit tool, the git wrapper if any, the log-verdict reader, the ledger
   appender, the push tool; each with its fallback when absent. Plain `git` is a valid answer for
   reads; a write to the git directory (commit, branch, rebase, push) is `rw-git` on every machine,
   since a session's sandbox denies that directory to everything else.
5. **Owner-only floor** — the actions no role takes on this machine without the Owner's
   explicit word, beyond the floor every profile shares (money, shipping a behaviour change,
   schema or public API, reversing a settled decision, anything another person reads).
6. **Paths** — sessions root, the accounting root (`launch.json`'s `accounting_root`, else
   `accounting` beside the sessions root: the ledger `records.jsonl` and the launch index
   `launches.jsonl`), projects root, decision logs, inbox, and where owner briefs
   are written, and the owner rules: the always-on rule files this machine loads for its Owner,
   if any. `launch.json`'s optional `desktop_roots` lists the folders whose repositories `rw-git`
   serves outside a managed worktree, for a session the Owner starts by hand there: each entry
   absolute or `~/`, with no glob and no link at any prefix, and a bad entry refuses, by name,
   every `rw-git` call outside a `repos` repository (`rw-git --help`, `SECURITY.md` → rw-git → "Outside a managed worktree").
   Its optional `protected_branches` maps a repository path, spelled as in `repos`, to the branch
   names or `fnmatch` globs `rw-git` writes to in no unmanaged checkout of it. Every repository
   gets `main`, `master`, `develop`, `release/*`, `hotfix/*` and the branch `origin/HEAD` names;
   a list adds to that default, never replaces it, and a bad value refuses, by name, every
   `rw-git` call in an unmanaged checkout. Its optional `push_remotes`, shaped the same, maps a
   repository path to the remote names, each one plain segment, `rw-git push --remote` may push
   to besides `origin`; with none, a push goes to `origin` only, and `fetch --remote` is
   unchanged. A bad value refuses, by name, every `rw-git push` to a remote other than `origin`.
7. **Duties** — a table of `role · extension point · skill or script to run`. The extension
   points a handbook exposes: `planner.brief`, `worker.preflight`, `worker.unit-gate`,
   `worker.publish`, `lead.tick`, `lead.intake`, `lead.post-publish`, `explainer.publish`,
   `reviewer.overlay`.
   The profile and the project hook (→ Duties) may each list duties at any extension point.
   A handbook reaching an extension point runs every duty the profile, then the project hook,
   lists for it, in order, and nothing when both list none.

   **Review Overlay.** A `Reviewer · reviewer.overlay · <path>` row names a file instead of a
   step: an overlay file of review enumerations (absolute path, `~` allowed; the Worker expands
   `~` at preflight), which the two code Reviewers apply after their correctness findings. The Worker resolves the rows at
   preflight, the profile's then the hook's, and pastes the paths into both review prompts; a
   Reviewer reads those paths and never the profile or the hook. Each named file that exists
   applies, in that order, its output headed by the file's path. A named file that does not exist is said so in the review, once,
   and the review continues; a missing file is never a `HOLD`. No row anywhere → the review
   has no Review Overlay section and says `no Review Overlay named` once.

   An overlay file is Markdown: numbered checks under `### Findings-eligible` and `### Notes`,
   each check three lines — what to look for, why it has bitten before, how to cite — with an
   optional `## Posture` before them, and an `## Output` section giving the shape the Reviewer
   emits under that file's path line inside the review's one `## Review Overlay` section:
   `### Findings-eligible`, then `### Notes`, each item with `file:line` or `none`.
   A findings-eligible item may `HOLD` only when it is one of the
   classes its review prompt names (`worker/prompts/REVIEW-GATE.md` and
   `ADVERSARIAL-REVIEW.md`, each under Output); every other item is a note.

The project hook (`worker/PROJECT-HOOK.md`) is the per-repository counterpart: build, test,
device, commit, publishing and naming facts for one codebase. The profile never names a scheme,
a test target, a branch format or what "published" means; the project hook never says how
sessions are launched or billed.
