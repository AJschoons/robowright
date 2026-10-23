---
name: robowright-onboard
description: Set up Robowright on this machine from a clone — check the install, interview the builder, write the machine profile, `launch.json` and a first project hook, write the scrub gate's pattern list when it is missing, link the four entry points, and end on a green `tests/run.sh`. Use when a builder installs Robowright on a machine. Manual invocation only.
disable-model-invocation: true
---

# Robowright onboarding

Takes a builder from a clone of Robowright to a working install: a machine profile at
`~/.claude/robowright/profile.md`, a `launch.json` beside it, a first project hook under
`~/.claude/robowright/projects/`, the scrub gate's pattern list at
`${ROBOWRIGHT_DENYLIST:-$HOME/.config/robowright/denylist}` when it is missing, the four entry
points linked into `~/.local/bin`, and `bash tests/run.sh` from the clone printing `EXIT=0`.

The builder owns every file this skill writes. Show each file before writing it, and write
only after the builder says yes. A file already at a target path is the builder's: show it,
and ask whether to keep it or replace it — never overwrite on your own call. This skill writes
nothing into `settings.json`; the status line is text the builder pastes (step 6).

Below, `<clone>` is the clone's absolute path, found in step 1.

## 1 · Check the install

The one manual step comes before this skill can run: the builder runs
`bash <clone>/install.sh`, because a skill is not in `~/.claude/skills` until its directory is
linked there. Run each check and report its result:

- `command -v python3 jq git claude` prints four paths. A missing tool is the builder's to
  install; stop until it is.
- `~/.claude/skills` and `~/.claude/agents` are real directories:
  `test -d ~/.claude/skills -a ! -L ~/.claude/skills`, the same for `agents`.
- `readlink -f ~/.claude/skills/robowright-onboard` prints `<clone>/skills/robowright-onboard`.
  Take `<clone>` from that path.

When a check fails, print the line that fixes it, for the builder to run, then run step 1 again:

```sh
bash <clone>/install.sh
```

When `install.sh` refuses, it exits 1 having made no link, and its stderr names the path and
the fix, one of:

- `install.sh: <path> exists and is not a symlink; move it aside and run again`
- `install.sh: <path> is not a directory; move it aside and run again`
- `install.sh: <path> is a symlink; remove it and run: mkdir -p <path>`

The builder applies the fix, then runs `install.sh` again.

Done when all three checks pass and `<clone>` is known.

## 2 · Interview

Ask one question at a time, each with the default it names, else the example's answer. Record
every answer.

1. **Machine** — a short name for this machine, and whether an employer manages it.
2. **Sessions root** — where Robowright Session directories live. Default
   `~/Projects/robowright-sessions`.
3. **Projects root** — where project folders live. Default `~/Projects`.
4. **Launch mode** — `paste`: the launcher prints the `claude --bg` line and the builder pastes
   it into a terminal, so a person starts every session. `auto`: the launcher starts each
   background session itself, which needs a shell that can run `claude --bg`; the Lead then
   starts Planner, Worker and Explainer sessions on its own, unattended, under the builder's permission
   settings. Default `paste`.
5. **Unit naming** — slug form, like `sample-012-note-autosave` (`examples/laptop/launch.json`),
   or ticket form, a ticket key plus a short slug, like `SMPL-482` and `export-csv`
   (`examples/desktop/launch.json`). Ask for one real example in the chosen form.
6. **Budget** — a Claude subscription, measured in plan usage, or an API key, billed in dollars.
   A subscription takes the laptop example's Budget section: `claude-usage`, `usage-guard` and
   the status line. An API key takes the desktop example's: `spend_threshold_usd` and
   `spend_cap_usd` in each brief, `spend-guard.py --watch 60` enforcing.
7. **Review Overlay** — a file of the builder's own review checks, which the two code Reviewers
   apply after their correctness findings. Three answers:
   - **None now** — no `reviewer.overlay` row is written. The profile is complete without one,
     and every review then says `no Review Overlay named`.
   - **Later** — no row now. When the builder is ready, the overlay skill's `## Add` section
     (`<clone>/skills/review-overlay/SKILL.md`) writes one check from one rule, typed, pasted or
     dictated, and prints the row to add.
   - **A path to an existing file** — the row `Reviewer · reviewer.overlay · <path>` is written
     into the profile's Duties with that path.
8. **First project** — the path to one repository's checkout, a project name for it, and its
   build and test commands.
9. **Owner rules** — the always-on rule files this machine loads for its Owner, if any.
   Default none.
10. **Protected branches** — which branches of each repository `rw-git` must never write in a
    checkout the builder works in by hand. Every repository already gets `main`, `master`,
    `develop`, `release/*`, `hotfix/*` and the branch `origin/HEAD` names; a
    `protected_branches` entry adds names or `fnmatch` globs to that list, never removes one.
    Default none added.

Done when all ten have an answer, and the unit example matches the form chosen.

## 3 · Write the machine profile

Write `~/.claude/robowright/profile.md` with the seven sections of
`<clone>/skills/robowright/PROFILE-CONTRACT.md`, in its order, seeded from
`<clone>/examples/laptop/profile.md`. Replace every value in the seed with the builder's
answer, and drop the seed's opening paragraph about being an example. A section that does not
apply says `None on this machine.`

- **Launch** — the mode from question 4, in the laptop seed's section either way. For `paste`,
  keep the section as it is. For `auto`, say that `launch.json` sets `auto`, keep the sentences on
  what the launcher prints and what `auto` does, and drop the one that calls `auto` the opt-in.
- **Budget** — the laptop seed's section for a subscription; for an API key, the Budget section
  of `<clone>/examples/desktop/profile.md`, whole. That file's `ILLUSTRATIVE` first line sits
  above its title and stays out of the profile.
- **Paths** — the sessions root and projects root from questions 2 and 3, and the owner rules
  from question 9, or `none on this machine`.
- **Duties** — the `reviewer.overlay` row only for the third overlay answer, with the builder's
  path. For **None now** and **Later**, delete the seed's row.

Done when the file holds the seven headings in order and the builder has confirmed every
value in it, the ones the interview did not ask about included.

## 4 · Write `launch.json`

Write `~/.claude/robowright/launch.json` from the matching example —
`<clone>/examples/laptop/launch.json` for slug form, `<clone>/examples/desktop/launch.json`
for ticket form. Keep every key the example carries: `schema`, `sessions_root`,
`review_guide_dir`, `report_scope`, `launch`, the `unit` block, `projects_root`, `repos` and `roles`.
Rewrite `_doc`, a comment no tool reads, to describe this machine. Set
`sessions_root`, `projects_root` and `launch` from the interview, `repos` to the first project's
main clone from question 8 (absolute or `~/`; with no `repos`, `accept.sh` and the launcher trust no
repository), `protected_branches` beside it when question 10 adds any (the repository path spelled
as `repos` spells it, to the list), and the `unit` block's
examples from question 5; the regexes are POSIX ERE as bash reads them, so change one only when
the builder's example does not match it. Create both roots with `mkdir -p`.

Validate it through the launcher, the check the test suite runs on the laptop example:

```sh
P=$(mktemp -d)
printf '# plan\n' > "$P/PROJECT.md"
~/.claude/skills/robowright/scripts/run-launch.sh --planner brief --project "$P" --slug <slug_example> --dry-run
```

For ticket form, add `--ticket <ticket_example>`. The launcher names the key it refuses; fix
that key and run it again.

Done when the dry run exits 0.

## 5 · Write the first project hook

Write `~/.claude/robowright/projects/<project>.md` with the fourteen sections of
`<clone>/skills/worker/PROJECT-HOOK.md`, in its order, seeded from
`<clone>/examples/laptop/projects/sample.md`. Fill each section from the repository itself —
its origin, build and test commands, branch names — or `None in this repository.` The Identity
row matches on the `owner/name` of `git -C <repo> remote get-url origin`.

Check that the resolver finds both files:

```sh
python3 ~/.claude/skills/robowright/scripts/robowright-resolve.py <repo>
```

Done when it exits 0 and prints the profile's path first and the hook's second.

## 6 · Link the entry points and the status line

```sh
mkdir -p ~/.local/bin
ln -s ~/.claude/skills/robowright/scripts/role-start.py ~/.local/bin/role-start
ln -s ~/.claude/skills/robowright/scripts/run-launch.sh ~/.local/bin/run-launch.sh
ln -s ~/.claude/skills/robowright/scripts/claude-usage ~/.local/bin/claude-usage
ln -s ~/.claude/skills/robowright/scripts/usage-guard ~/.local/bin/usage-guard
```

When a write to `~/.local/bin` is refused (`SECURITY.md` → The recommended setup, step 7 has the
builder deny it), print the block above for the builder to run in their own terminal; once they
say it ran, run the "Done when" check below again.

An `ln` that says the file exists has found something of the builder's at that path: show
what it is, and leave it for the builder. When `~/.local/bin` is not on `PATH`
(`case ":$PATH:" in *":$HOME/.local/bin:"*)`), tell the builder; their shell's startup file is
theirs to edit.

For a subscription, point the builder at the status line in
`<clone>/skills/robowright/OWNERS-GUIDE.md` → "The status line": the `statusLine` entry they
paste into their own `settings.json`. Until it is there, `claude-usage` has no reading.

Done when `readlink -f` on each of the four links prints a path inside `<clone>`, and
`find -L ~/.local/bin ~/.claude/skills ~/.claude/agents -type l` prints nothing: no link
dangles.

## 7 · Run the suites

`tests/run.sh` ends with the scrub check, `tools/scrub-gate.sh --tree`, which refuses to run
without its pattern list at `${ROBOWRIGHT_DENYLIST:-$HOME/.config/robowright/denylist}`. When
that file is missing, tell the builder what it is: this install's own list of the names that must
never enter a commit from this machine, one pattern per line, empty until they add one. Show it,
and once they say yes, write it at that same path, holding two comment lines:

```sh
D="${ROBOWRIGHT_DENYLIST:-$HOME/.config/robowright/denylist}"
mkdir -p "$(dirname "$D")"
printf '%s\n' \
  '# scrub gate patterns: one POSIX ERE per line, matched case-insensitively' \
  "# the patterns are this install's own: names that must never enter a commit from this machine" \
  > "$D"
```

On a no, the run below prints `scrub: denylist not found` and ends `EXIT=1`, and this step stays
open until the builder writes the file. Then:

```sh
bash <clone>/tests/run.sh
```

It prints one line per suite and ends `EXIT=<n>`; expect a few minutes, most of it the
session-state suite. On `EXIT=1`,
quote the failing suite's line and read that suite's output with
`python3 <clone>/<the suite's path>`.

Done when the last line is `EXIT=0`.

## 8 · Hand back

Report, in this order:

- the four files written, with their paths, and each one the builder kept rather than replaced
- the four links, and whether `~/.local/bin` is on `PATH`
- the `EXIT=0` line, quoted
- for a subscription, whether the status line is pasted yet
- for the overlay: nothing for **None now**; the `## Add` pointer again for **Later**; the path
  for a file
- next: `role-start planner` starts a Planner session for the builder's first piece of work

Done when the builder has all six items.
