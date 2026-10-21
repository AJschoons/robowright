# Security

## What a Robowright Session can do on your machine

A Worker is a background Claude Code session (`claude --bg`) in a git worktree that runs a brief
for hours unwatched, doing whatever **your** permission settings allow without asking: shell,
edits, builds, tests, commits to its own branches. On top of your settings, this tree:

- **Fixes the tools**: the launcher's `LEAN_TOOLS` (`skills/robowright/scripts/run-launch.sh`;
  with `Bash`, `WebFetch` and `WebSearch`) unless a brief's `tools` replaces it, and no MCP server
  unless a brief picks one from the approved list in `skills/robowright/mcp/`, whose allow rules
  (`--allowedTools`) reach only that server; `xcodebuildmcp.json` approves all its tools, even
  ones that run code.
- **Fixes the prompts**: a Worker's first is `/worker <session_dir>`, plus fixed sentences on a
  resume; the Planner's and Explainer's interpolate a few session-file values, each listed below.
- **Writes git only through `rw-git`**: a session's sandbox denies every repository's git directory, and the one
  program it runs outside the sandbox to stage, unstage, commit, amend, switch, reset, rebase, cherry-pick, stash,
  fetch or push is `rw-git` (→ rw-git). Reads stay plain `git`.
- **Runs git that can discard work**: the `load-bearing-tests` loop reverts with `rw-git restore <file>`, losing
  uncommitted work there, and stashes the fix for a regression baseline. Worktrees share `refs/stash`; `rw-git stash
  pop` applies only an entry tagged with its own worktree's slug, and plain `git stash` cannot write from a session.
- **Never pushes from the launcher.** Publishing follows the project hook's strategy: `local-branch`
  (the example's) pushes nothing, `draft-pr` the session's own branches, `pr-plus-deploy` those
  plus a preview deploy the hook names, `push-to-branch` a hook-named branch that may be shared.
- **Puts an Owner-only floor** in every machine profile, which every role reads and stops at; both
  examples put any push, new dependencies and deleting branches on it. The floor and the strategy
  are instructions a model follows, not a sandbox: nothing here stops what your settings allow.

## What each role can write

The launcher (`run-launch.sh`) and `role-start.py` pass each session its write scope in `--settings`, built by
`skills/robowright/scripts/role_grants.py` from `launch.json` alone. The grants go in
`permissions.additionalDirectories`, which Claude Code reads for the [Bash sandbox](https://code.claude.com/docs/en/sandboxing)
and for its Write and Edit tools alike; the working directory is the one other grant.

| Role | Can write | Cannot write |
|---|---|---|
| Worker | Its worktree (the working directory); its session folder; the accounting root; `<sessions root>/.<name>-lock` for each lock its `run.json` names. Its repository's git directory only through `rw-git`, which its settings run outside the sandbox (`sandbox.excludedCommands: ["rw-git *"]`) and allow
(`permissions.allow: ["Bash(rw-git *)"]`). Tracked `.claude/` prose in its worktree (rules, the project hook) stays writable. A `depends_on` checkout is made by the launcher, in a repository `repos` lists, at a commit id: git names its admin dir, so no grant can | Another session's folder, the rest of the projects root, the main clone's working tree, every configured repository's whole git directory, any `.git` file or folder under its worktree, session folder, accounting root or lock directories (a leaf `<root>/**/.git` deny), and the `.claude` settings, skills, agents, commands and hooks Claude Code protects in its working directory |
| Planner, Explainer (launcher) | The projects root and the sessions root, from a project folder | Any worktree or clone, the accounting root, the `.claude` folder and `.mcp.json` of the projects root and of each folder in it, which Claude Code loads as project settings for a session started there, every configured repository's whole git directory, and any `.git` under the projects root or the sessions root |
| Lead, a Planner started by hand (`role-start.py`) | The projects root, the sessions root and the accounting root, starting in the project folder, or the projects root with no project | The same. A Worker's worktree is made by the launcher (below), so the Lead never needs a repository's git directory |
| A direct build (a session with no `run.json`, started in its worktree; the planner handbook → Size `S` or below) | Its worktree (the working directory) and a Planner's grants: the projects root and the sessions root. `run-launch.sh --direct` makes the worktree (below) and starts the build in it with those grants. The fallback, where the launcher cannot run: you make the worktree with the hook's `git worktree add` line and start the build from it with `s="$(python3 <clone>/skills/robowright/scripts/role_grants.py document)" && claude --bg --settings "$s"`. Started without that `--settings`, it writes only its worktree and what your own settings grant | What a Planner cannot, but its own worktree, and any `.git` under that worktree. It commits through `rw-git`, which its settings run outside the sandbox. Without that `--settings`, no `.git` file is denied beyond the sandbox's own `hooks/` and `config` and what your own settings deny, and `rw-git` runs sandboxed, where it cannot write the git directory |
| Hooks (the worker hooks, the SessionEnd cost hook) | Anything you can: hooks run outside the sandbox. They write the session folder and the accounting root, through `session_write.py`. Invoking `worker` registers its frontmatter hooks for the rest of the session that invoked it ([skills](https://code.claude.com/docs/en/skills), read 2026-10-16). Nothing in the skill stops a model from invoking it: its description asks for a prompt naming a session directory, an instruction only. Optional hardening, on a machine that starts Workers only through the launcher: `"skillOverrides": {"worker": "user-invocable-only"}` in your user settings hides `worker` from Claude's skill listing, and `/worker <session_dir>` stays typeable. The docs do not say it refuses a call by name | |

- **No grant, and no working directory, may sit at or above** the home directory, **nor at, above or inside** a
  repository `repos` lists, the clone the launcher runs from, or `launch.json`'s directory, the link's or the real
  file's, **nor inside any git checkout** below the home directory that no root holds (a worktree, a clone `repos` does
  not list). A projects root that is the folder that holds your clones is refused by name, and nothing starts; so is a
  `--project` folder inside a clone. So is any grant without a well-formed `repos`. A projects root you version with
  git is yours and passes.
- **No root, grant or working directory has a link at any prefix, or a `.` or `..` component, and none is
  relative.** A role granted a root could otherwise put a link in it (the sessions root, the accounting root, a session
  folder, a project folder) and every later session would be granted its target. No link is followed, yours included:
  the refusal names the path and the link, and the fix is to spell the real path in `launch.json` or on the command
  line. **Each component, and each `repos` entry's, is spelled as the disk names it**, in letter case and Unicode
  form: the sandbox matches a grant or a deny as a string, and on a case-insensitive volume another spelling names the
  same directory for the kernel but not for that match. With no links and the disk's spelling, a path's spelling is its
  place on disk. Protected paths you do not write in `launch.json` (the home directory from `$HOME`, the launcher's
  clone) are compared by device and inode, so their spelling never matters.
- **The environment never moves a grant.** `$ROBOWRIGHT_ACCOUNTING_ROOT`, `$ROBOWRIGHT_SESSIONS_ROOT` and
  `$ROBOWRIGHT_PROJECTS_ROOT` steer the tools, never what a session may write, and the git that names the denied files
  runs with every `GIT_*` variable removed. `$HOME` still chooses which `launch.json` is read, and with it the repositories the launcher makes a Worker's worktree in. Whoever sets the launcher's environment also sets its `PATH`, and with it every `git`, `jq` and `python3` it runs, so this adds no reach; the launcher is safe only from an environment no session wrote. Where
  `$ROBOWRIGHT_ACCOUNTING_ROOT` is set in the environment a session starts in, its cost records go outside the grant
  and are refused.
- **These add to your own settings, never replace them.** Claude Code merges `additionalDirectories` across settings
  files, so a directory your user settings grant every session (the folder that holds your clones, say) is still granted.
  **A folder granted in your user settings reaches every session the launcher starts**: measured 2026-10-17 on Claude
  Code 2.1.302 with `claude -p` and its own `--settings`, as the launcher passes them, a folder in user-settings
  `permissions.additionalDirectories`, and one in `sandbox.filesystem.allowWrite`, was writable, and not writable once
  the user scope was left out; the launcher passes no `--setting-sources`, so its sessions load the user scope. So the per-role grants above bound a session's writes
  only when your user settings grant nothing beyond Claude Code's defaults. Remove any other grant there; the
  recommended setup grants your repositories' folder by starting a session in it instead.
- **A session cannot add the marker to `.git/info/exclude`.** The launcher adds it before the session starts, and
  adds `/.worktrees/` to the main checkout's `info/exclude` once when it makes a worktree there, through
  `session_write.py`, so `accept.sh` finds the main checkout's status clean.
- **Leaf denies.** Each granted root, and a committing role's worktree, gets `<root>/**/.git` in `denyWrite` and as an
  `Edit(...)` deny. A wildcard deny holds only up to its first `**`: under `<root>/**/.git/config` a session renames
  `.git`, edits the config, and renames it back. A deny whose last component is the name itself still matches after
  the parent is renamed, and it refuses `git init` and `git init --separate-git-dir` there, whose `.git` file it also
  matches. The leaf is a wildcard, which Claude Code honours on macOS only; each repository's own git directory is
  denied by its literal path, which holds everywhere.
- **The launcher makes a Worker's missing worktree**, as you, since no session can write a repository's git directory.
  It makes one only at `<repo>/.worktrees/<session folder name>` in a repository `repos` lists and a project's
  `robowright.json` names, on branch `robowright/<session folder name>`; at preflight with `-b` from `run.json`'s
  `base_sha`, a full commit id of that repository, and later by attaching the existing branch. A finished session gets
  none. A session briefed before this layout, whose `run.json` names `<repo>/.claude/worktrees/<session folder name>`,
  is made and started there as before, until it is torn down. A `**/.claude` deny (the recommended setup) covers
  every file in such a worktree, so finish that session before you add the deny. A Worker's shell wrote the shared git directory before
  `rw-git`, so the launcher refuses a link anywhere on the way to the new
  branch's ref or reflog, and its `worktree add` creates no reflog. Anything else is refused before git runs, with the `git worktree add` line for you to judge and run yourself.
  It makes a direct build's worktree (`--direct`) with the same code and checks, from argv rather than `run.json`:
  `<repo>/.worktrees/<slug>` on `robowright/<slug>`, `-b` from `--base`. An existing path there is reused only
  when it is that repository's worktree of that branch; anything else at the path, or the branch with no worktree, is
  refused. A build started at `<repo>/.claude/worktrees/<slug>` before this layout is reused there while nothing is at
  the new path.
  `git worktree add` checks out the base, so a filter driver your git configuration names runs on it (→ How the
  Owner-side tools run git).
- **A Worker run as a background task inside another session**, the Lead's in the desktop app, writes with that
  session's grants, not the ones `role_grants.py worker` gives a launched Worker: nothing passes it a Worker's
  `--settings`. Its worktree and session folder are writable only as far as that session's grants reach, and the
  Worker row's denies hold only where that session's settings carry them. So do the tool, MCP and first-prompt limits
  above, which come from the launcher's session flags: such a Worker has the host session's tools and MCP servers, and
  starts from a prompt the Lead wrote. This is a known limit of that launch mode; nothing here narrows it.
- **What stays open:** `rw-git` writes the git directory as you, within its subcommands: it commits, rebases and
  stashes on the session's own branches, and pushes one only where the project hook publishes. A worktree whose admin
  files were rewritten (by a session started before `rw-git`, say) is refused as `worktree-foreign-gitdir`. The launcher checks `deps` for a
  link just before git makes a checkout there; a role that can write the session folder and wins that race steers
  where the checkout lands. A Worker cannot write a `depends_on` checkout's admin directory in another repository, so
  removing that checkout at its finish leaves a `prunable` entry; `git worktree prune` there clears it, and until then
  git refuses a relaunch of that session. A directory is checked at launch. A session's working directory is safe from a later swap: the launcher and
  `role-start.py` check it before reading anything in it, start only once the shell's own `pwd -P` (or `getcwd`) is the
  path checked (the line a `paste` hand-off prints makes the same compare before it starts), and write the launch's ledger line from inside it. A directory granted by `additionalDirectories` (a
  root, a session folder, a lock directory) is not: a role that can write a root and swaps a directory in it for a link
  between the check and the session's start wins that race. The protected paths
  (`repos`, `launch.json`, the home directory) may be spelled through your own links; a grant above any link their
  spelling passes through is refused, but a link inside that link's target is not looked for, so spell them by real
  path. The launcher's `worktree add` reads the other worktrees' admin files with no timeout: a FIFO planted there before a session lost its write to the git directory may stall the launch until you stop it. A project folder made after a document role started, one nested deeper than a folder of the projects root, or one whose name starts with `.` has its `.claude` and `.mcp.json` denied only by a wildcard, which Claude Code drops on Linux and WSL2. The leaf `<root>/**/.git` denies are wildcards, which Claude Code drops on Linux and WSL2: there a session can `git init` a folder under a granted root, and a git you later run in that folder reads the config it wrote. A direct build started by hand with `claude`, not through `--direct`, gets only what its own command line grants, its
  worktree is yours to make, and nothing checks where it started. `--direct` confirms the started session's `cwd` from
  the session registry after an `auto` start; a pasted hand-off is checked only by the line's own `pwd -P` compare.

## Values a session can write

A session writes its own `run.json`, `events.jsonl`, `.stop-gate-count` and worktree marker; a Planner or the Lead
can create directories under the sessions root, a Planner writes `robowright.json`, and the Lead writes the launcher's
argv.
The launcher, worker hooks, `role-start.py`, `run-cost.py` and roster read these **outside the
sandbox and the session's permission settings**, so each value is held to a shape before it
reaches JSON, a flag, arithmetic, git, a path or a prompt, and refused by name before anything
starts unless the table says otherwise. Rules and lint: `.claude/rules/`, `tests/conventions/`. The lint is a tripwire,
not a proof: its raw-git check reads only `accept.sh`, `run-launch.sh`, the dashboard, `run-cost.py` and
`session-state.py`, so the git calls of `rw_git.py`, `role_grants.py`, `owner_git.py` and `session_write.py` are held
by their own suites and by review.

| Value | Read by | Check |
|---|---|---|
| `run.json` `model`, `units[].model`, `robowright.worker`; `robowright.json` `models.<role>`; `--model`, `--subagent-model` | Launcher, `role-start.py` | The form in `skills/robowright/models.json`: `opus`, `sonnet`, `haiku`, `fable`, or `claude-` then lowercase letters, digits, `.` and `-`. The `--settings` JSON is built by a JSON encoder, never by string formatting. `model` and `units[].model` also fall under the integrity check below |
| `run.json` `session_id`, `--resume <id>` | Launcher | A UUID, passed as `--resume=<id>`. A non-UUID previous id never builds a transcript path |
| `run.json` `tools` | Launcher | `null` (the lean list) or comma-joined names from the launcher's `KNOWN_TOOLS`; `default` is refused |
| `run.json` `mcp` | Launcher | Each pick names a server on the approved list, a workflow its entry offers, and allow rules that reach only that server; the binary's version is checked against the entry's pin. `mcp_config` must be null |
| `run.json` `ticket` | Launcher | One path segment of letters, digits, `.`, `_` and `-`, starting with a letter or digit, and `launch.json`'s ticket pattern where one is set |
| The session dir's name, when there is no `ticket`; an intake directory's name | Launcher | A unit name in this install's form (`launch.json` `unit`); an intake directory outside it is skipped |
| `run.json` `stop_reason.code` | Launcher | One of the stop codes in `skills/robowright/state-machine.json` |
| `run.json` `phase`, `stop_reason`, `rotate`, `rebriefs`, `units[]` id, status, gate attempts and head | Launcher, hooks, roster, the dashboard | Written only through `session-state.py`; a hand edit fails its integrity check, the roster flags it, and the launcher refuses the session. A tripwire for an edit made around the tool, not a lock: a session can run the same tool, `adopt` included, and can write `events.jsonl` itself. Models are not checked across a rebrief, nor unit models before the first unit starts |
| `run.json` `profile`, `effort`, `compact_pct`, `--stop-cap` | Launcher | `profile` and `effort` a closed set, `compact_pct` digits from 10 to 100, `--stop-cap` digits |
| `run.json` `locks` | Launcher, `session-state.py`, `role_grants.py` | Lowercase letters, digits and `-`; `park` removes only a lock whose owner file names this session |
| `run-launch.sh --direct`'s `--slug`, `--repo`, `--base`, `--project` and `--briefing` | Launcher (`role_grants.py direct`) | `--slug` a unit name on this install and one path segment, and `robowright/<slug>` a branch name git accepts; `--repo` a repository `repos` lists and a project's `robowright.json` names, spelled as its real path; `--base` 40 lowercase hex that `rev-parse --verify <base>^{commit}` returns unchanged; `--project` a folder directly in `launch.json`'s `projects_root`, not the sessions root; `--briefing` a regular file with one link, its name one path segment ending `.md`, directly in `<project>/briefings/`. None may hold a link or a `.`/`..` at any prefix. Only the briefing's path reaches the prompt, inside a fixed sentence; `--name` is refused |
| `run.json` `depends_on` | Launcher (`role_grants.py`) | `session` one path segment of letters, digits, `.`, `_` and `-`; `ref` 7–40 lowercase hex; `path` the same directory as a `repos` entry, else refused before anything starts. The checkout is made with `owner_git.py`'s options and `--end-of-options`, never through a link at `deps` or at the target |
| `run.json` `units[0].branch` | Launcher (`role_grants.py`) | To make a missing worktree, exactly `robowright/<session folder name>`, then `git check-ref-format --branch`; a later phase also needs the branch to exist. Otherwise printed in a suggested `git worktree add` line only if `git check-ref-format --branch` accepts it, and shell-quoted there |
| `run.json` `base_sha`, `publish.tip` | `run-cost.py`; the launcher (`role_grants.py`) for `base_sha` | 7–40 hex characters, or `HEAD` for the tip; the git call ends its options with `--end-of-options`. To make a worktree at preflight, `base_sha` must be 40 lowercase hex characters that `rev-parse --verify` names as a commit of that repository |
| A session's directory name, or a direct build's `prs/<slug>.md` name, as the branch `robowright/<slug>` | The dashboard (`has_reached_main`) | Used only when it matches `BRANCH_SLUG` in `tools/robowright-dash.py`: alphanumeric runs joined by single `.`, `_` or `-`, not ending `.lock`, so git reads it as one branch name and never a range, a reflog or an option. Then only in a hardened `rev-parse --verify --quiet --end-of-options refs/heads/robowright/<slug>`, run in a repository its project's `robowright.json` names and `launch.json`'s `repos` lists, never in a worktree. Out of shape, it is never read as in main |
| `accept.sh --direct`'s `<slug>` and `--base`, and `--tip` in both modes, in the line a Lead composes for you | `accept.sh` | `--tip` 40 or 64 lowercase hex, checked before anything is read, else `tip-missing` or `tip-invalid`, and the branch's tip when it is resolved, else `tip-moved` naming both ids, so a commit added after the line was composed is never integrated; `--direct` has no phase guard, and `--tip` is what pins the reviewed commit there. `<slug>` alphanumeric runs joined by single `.`, `_` or `-`, not ending `.lock`, else `slug-invalid`; `--base` 40 or 64 lowercase hex, else `base-invalid`, then an ancestor of the branch tip, else `base-not-ancestor`, and of the main clone's branch, else `base-not-on-main`. `robowright/<slug>` must be held as a branch, never a tag of that name (`show-ref --verify`), by exactly one repository `launch.json`'s `repos` lists and a project's `robowright.json` names (`owner_git.py branch`), else `branch-missing` or `branch-ambiguous`, and `branch-missing` too when git cannot list that repository's worktrees, so a failed listing never skips the worktree's `status` check; git runs in its worktree only after `owner_git.py worktree` accepts it, and reads no attributes there or in the merge. The fast-forward that follows checks the squash out in the main clone with attributes read, not switched off, so a driver your configuration names can run on the build's content, as Filter drivers says. accept.sh's inline Python runs with `-I`, so a module the build put in the current directory is never imported. In both modes accept.sh refuses `accept-in-target` before writing anything when its own path, links resolved, is inside the main clone or a worktree it lists, because after the fast-forward the scripts beside it would be the build's; run `~/.claude/skills/lead/scripts/accept.sh` from a clone no session can write. accept.sh passes the squash message through shell variables and pipes, never a file in `$TMPDIR`; with `-S` and `gpg.format=ssh`, git itself writes the commit it signs to a file in `$TMPDIR` for `ssh-keygen` to read, so a live session could have your key sign other bytes. A line a Worker or a direct build wrote is session text: compose it yourself from the build's base, `git rev-parse` of the reviewed tip in the main clone and the hook's message path, or check every word and `--tip` against what you reviewed. A `--message` outside the folders the next row names is refused `message-outside`. Read the line before you run it |
| `accept.sh --message <file>`, the squash message a session wrote | `accept.sh` | The path as given must be absolute with no `.`, `..` or empty part. First its place, before anything is read: a file directly in `<project_dir>/prs/<slug>/` for `--direct`, or in any `<session_dir>/prs/<unit>/` folder for a session, the positional folder compared with its links resolved; the folder is the bound, not the file name. Else `message-outside`, naming the folder, and nothing is read. Then read through `session_write.py read` before anything is written: every folder opened under the last without following a link, the name a regular file with one link of at most 64 KiB, opened so a FIFO never waits. Anything else is `message-unreadable`, naming the reason, and nothing is committed |
| A direct build's `prs/<slug>/ACCEPTED.json` | The dashboard (`is_accept_recorded`) | Read without following a link at its name, never waiting on a FIFO, at most 4096 bytes (`owner_git.read_entry`). Used only when the slug matches `BRANCH_SLUG`. Its `sha` must be 40 or 64 lowercase hex and an ancestor of the default branch (`default_branch`) in a trusted repository its project names, checked by a hardened `merge-base --is-ancestor --end-of-options`. While `robowright/<slug>` is still in any trusted repository, the commit must be on that repository's default branch and its own diff must have the `patch-id --stable` of the branch's diff from where it left `main`, both read over the changed lines only (`-U0`) and with no attributes. Once the branch is gone, a session can name any commit on `main` and the build reads as accepted. `accept.sh --direct` refuses any existing record as `already-accepted`, printing the commit it names, so a forged record also blocks the accept until you delete it. A session's own `run.json.accepted` reads as accepted without these checks: the dashboard only displays it, and only `accept.sh` acts on it, refusing that session as `already-accepted`, so a forged value blocks its accept until you clear it |
| A project's `robowright.json` naming a repository `launch.json`'s `repos` does not list | The dashboard (`project_repos`) | That repository is never read; the project is judged on the trusted ones it names, and on none when it names none. So a finished direct build whose branch lives only in the untrusted repository reads as torn down after an accept once its Worker has exited |
| A project's `robowright.json` itself, which a Planner writes and a Worker can wherever your settings grant it the projects root | `owner_git.named_repos`, the dashboard (`project_settings`), `role-start.py`, the launcher | Read through `owner_git.read_unlinked` (the launcher through `session_write.py read`), as `accept.sh` reads its message: never through a link at the file or a folder below the projects root, never waiting on a FIFO, at most 64 KiB. A refused read is an unreadable file: `named_repos` skips the folder, the dashboard reads `{}`, `role-start.py` exits 4 `cannot read`, and the launcher refuses to start. `robowright-resolve.py` reads it plainly, not through `owner_git.read_unlinked`: it serves sessions and you alike, runs sandboxed for a session, and a machine-local hook may be a link by design. It writes nothing, and what it prints is a list of files to read; the git it runs is `rev-parse --show-toplevel` and `remote get-url origin`, without `owner_git.py`'s overrides, in the path it is given and the repositories a `robowright.json` names. rw-git's `push` calls the resolver's `resolve_hook` as you (`rw_git.py:625-634`) and reads the hook it finds with the same plain open |
| A project's `PROJECT.md` Task Breakdown cells (`#`, Unit, Summary) | The roster (`plan_label`) | Read only from `<projects root>/<project>/PROJECT.md`, `<project>` an entry of the projects root's own listing. Printed only as the units cell's label, with every C0 control and DEL dropped and cut to 40 characters, inside the table the roster fences as data |
| `run.json` `worktree` | Launcher, `accept.sh`, `run-cost.py`, `session-state.py`, the dashboard | Listed by `git worktree list` in a repository the Owner configured, compared by canonical path (`skills/robowright/scripts/owner_git.py`), else refused as `worktree-unlisted` before any git runs inside it. It must also have its own git dir, the repository's `worktrees/<id>` entry naming it back, checked by one hardened `rev-parse` inside it, else refused as `worktree-foreign-gitdir`. The configured repositories are those `launch.json`'s `repos` lists and a `repos[].path` in a `robowright.json` one level under the projects root (`$ROBOWRIGHT_PROJECTS_ROOT`, else `launch.json` `projects_root`) names, compared as the same directory on disk: a `robowright.json` narrows `repos` and never widens it. Each `repos` entry is an absolute or `~/` path with no control byte; with `repos` missing, not a list, or holding one entry out of shape, no repository is trusted and the refusal is `repos-unconfigured`, naming the file and the line to add. Nothing in or under a sessions root counts (the one `$ROBOWRIGHT_SESSIONS_ROOT` or `launch.json` names, and the dashboard's `--runs-root`), compared as the same directory on disk, whether a `robowright.json` there or a path one names. `accept.sh` integrates into that configured repository, never one found from the worktree's own metadata. The launcher also requires a linked worktree under a `.worktrees/` or `worktrees/` directory that is its own toplevel. A missing one is made only when the value is exactly `<repo>/.worktrees/<session folder name>` for such a repository, or the older `<repo>/.claude/worktrees/<session folder name>`, `<repo>` its real path, with no link at any component |
| `run.json` `session_id`, `transcripts`, `started_at`; whether `events.jsonl` has a line | The roster and the dashboard, through `never_launched` in `session-state.py` | The three `run.json` fields are tested for truthiness only; `events.jsonl` is read line by line (`read_events`) and only whether it has a line is used. Nothing is printed or passed on. A session at `phase = preflight` that blanks the three fields and empties `events.jsonl` reads `briefed`, which the Lead lists and never resumes, and the dashboard shows under Needs attention |
| `run.json` `transcripts` | `run-cost.py`, the SessionEnd hook | None: any `.jsonl` file it names is read, and only aggregate counts come out |
| `run.json` `units[].kind`, `rotate.requested_at`, `project` | Launcher, Stop hook | `kind` only picks the profile row, anything outside `tests`, `docs`, `refactor` reading as the judgment group. `rotate.requested_at` must be an ISO-8601 time: the launcher refuses anything else, and the Stop hook's ledger line quotes a fixed phrase instead. `project` is recorded through a JSON encoder |
| `HANDOFF.md` FIRST ACTION, `phase`, the unit id, branch, worktree and `device.udid` | Worker hooks | Quoted into the same session's own context, any JSON through an encoder: a session is trusted about itself |
| `run.json` `updated_at`, `spend_threshold_usd`, `spend_cap_usd`; `events.jsonl` `event` | Stop hook, SessionEnd hook, launcher | `updated_at` is only hashed into the Stop hook's fingerprint; the spend fields are only compared with null; the newest event name is only compared with `resume`, to pick one of two fixed resume prompts |
| `.stop-gate-count` | Stop hook | Anything but one to six plain digits reads as 0, and digits are read as a decimal number, never evaluated as an expression |
| `<worktree>/.claude/autonomous-run` | Every worker hook | Used only when the directory it names sits under the sessions root, though it may be another session's directory. This repository's `.gitignore` ignores it |
| The entries of the session folder and the worktree's `.claude`: `LEDGER.md`, `run.json`, `events.jsonl`, `.session-state.lock`, `.stop-gate-count`, `STOP`, the marker; and the accounting root's `records.jsonl`, `.records.lock` and `launches.jsonl`, beside the sessions root and inside a session's sandbox grant | Worker hooks, launcher, `session-state.py`, `run-cost.py`, `spend-guard.py` | Written only through `skills/robowright/scripts/session_write.py`: the name is opened in a directory that is not a link, never through a link, never truncated on open, and written only when it is a regular file with one link, so a symlink, FIFO or hard link the session planted is refused and nothing is created or changed. `run.json` is replaced by a rename. The launcher refuses a worktree whose `.claude` is a link, and checks each file it will write before anything starts. A link higher up the path than the session folder or the accounting root itself is not checked, and `run-cost.py --ledger` still reads `records.jsonl` and `launches.jsonl` by path before it writes, so a FIFO there can stall the SessionEnd hook, though nothing is written through it |
| `rw-git`'s working directory | `rw-git` | Checked with `owner_git.py`'s code: a worktree or the main checkout of a repository `launch.json`'s `repos` lists, or of one whose main checkout lies under a granted folder (→ rw-git, "Outside a managed worktree"), by canonical path, with its own git directory, else `worktree-unlisted` or `worktree-foreign-gitdir`; a link in a `repos` entry's spelling is `launch-config`. Its slug is its folder's name, one path segment, only when its parent is `<repo>/.worktrees` or `<repo>/.claude/worktrees`; the main checkout has none, and owns what an unmanaged checkout owns (→ rw-git, "Outside a managed worktree") |
| `rw-git` paths (`add`, `restore`, `stash push`) | `rw-git` | Relative to the worktree or absolute inside it, normalized, with no `.git` component in any letter case and no link at any folder on the way; passed after `--` under `--literal-pathspecs`, so none reads as an option or a pattern. Else `path-outside`. Before `add`, a file git would stage under a converting attribute is opened folder by folder from `/` with `O_NOFOLLOW`, non-blocking, and read only if it is a regular file, so no link at any folder is followed and no FIFO is waited on |
| `rw-git` branch (`switch`, `push`) | `rw-git` | In a managed worktree, exactly `robowright/<slug>` or `robowright/<slug>-u<N>` for this worktree's slug, else `branch-not-own`; `commit`, `commit --amend`, `reset`, `rebase` and `cherry-pick` need HEAD, or the rebase in progress, on such a branch, else `head-not-own`. In an unmanaged checkout, `switch -c` and `push` name, and every subcommand that writes a branch needs HEAD or the rebase in progress on, a branch `protected_branches` does not protect, matched case folded and never one holding a byte outside printable ASCII (APFS folds `ſ` onto `s`, so `maſter` is `master`'s ref file), a character `git check-ref-format` refuses, `@{` or `..`, else `branch-protected`; `reset` and `push --force-with-lease` there also need a branch no remote-tracking ref or upstream tracks, else `branch-tracked`; `switch` goes to any existing branch. A push also needs the main checkout's project hook to publish pushed branches, else `push-unpublished`. Every call holds an exclusive `flock` on `rw-git.lock` in the repository's shared git directory from its first check to git's last write, so a second `rw-git` cannot move HEAD or the index between them; a git you run yourself takes no part in that lock. The lock is shared by every worktree of the repository, so a call that stalls (git opening a FIFO a session made in its worktree, a slow network) would hold up the others: a call waits for it at most 30 seconds (`LOCK_WAIT`), then is refused `repo-busy` naming the lock file, and git's output is written only after the lock is released, so a caller that never reads its pipe holds up no one |
| `rw-git` commit id (`rebase`, `rebase --onto`, `reset`, `cherry-pick`) | `rw-git` | 40 lowercase hex that `rev-parse --verify <id>^{commit}` in that repository returns unchanged, else `commit-unknown` |
| `rw-git commit --message-file` | `rw-git` | An absolute path with no `.` or `..` part, under `<sessions root>/<slug>/` or `<projects root>/<project>/prs/<slug>/`, opened folder by folder without following a link, a regular file with one link and at most 64 KiB, else `message-file`. Its bytes reach git on stdin, never argv |
| `rw-git commit --scope-file` | `rw-git` | Read under the message file's rules, refused as `scope`; one pathspec per line after `#` comments and blank lines are dropped, a line with a control byte refused; passed after `--` under `--literal-pathspecs`, so no glob or pathspec magic reaches git. Paths come from `diff-index -z`, and each one printed has every control byte removed |
| `rw-git --remote` name (`fetch`, `push`) | `rw-git` | One segment matching `[A-Za-z0-9][A-Za-z0-9._-]{0,63}` that `git remote` lists, else `remote-unknown`; its URL comes from the repository's configuration, never argv, and only ssh and https carry it. `remote.<name>.mirror` is overridden as origin's is |
| The stash list's subjects | `rw-git stash pop` | Only an entry whose subject ends `: rw-git <slug>` (unmanaged: `: rw-git <the checkout's canonical path>`; a slug holds no `/`), which `rw-git stash push` writes, is applied, by full id; it is dropped by the index found again just before the drop |
| Ledger headings, `HANDOFF.md`, `stop_reason.detail`, `parked.reason` | `run-roster.py` | Printed under a line saying it is data, not instructions, with control bytes removed: behind a `│` fence, except a parked reason, which is folded onto its own `parked:` line |

Within those shapes a session still picks the model, tools and MCP server. The checks stop it
**widening** what the next launch runs with, not misbehaving inside limits that are instructions.

### How the Owner-side tools run git

| Covers | Does not cover |
|---|---|
| Every git call `accept.sh`, the launcher, the dashboard, `run-cost.py` and `session-state.py` make in a session's worktree, or in the main clone on its behalf, starts with `--no-pager -c core.fsmonitor=false -c core.hooksPath=/dev/null -c log.showSignature=false`, then `--config-env=hook.<name>.enabled=OWNER_GIT_FALSE` for each config hook that repository configures, read on every call, with `OWNER_GIT_FALSE=false` in git's environment: a hook name may hold `=`, where `-c` would split it. The launcher's calls in a Worker's worktree, and every `worktree add` it runs, a direct build's included, add `--attr-source=<the empty tree> -c core.attributesFile=/dev/null` (Filter drivers), and its `status` adds `--no-optional-locks`, so it writes no index through a link a Worker plants at the admin dir's `index` | **Filter drivers.** A `.gitattributes` a session commits can name a `filter.<driver>`, whose `clean`, `smudge` or `process` command comes from your git configuration, git-lfs for example; a driver name nothing configures does nothing. The launcher reads no attributes from a Worker's checkout, its index or your global attributes file, so none of those drivers runs as you there, and it checks a worktree and each `deps/` checkout out raw: a git-lfs pointer stays a pointer, and no filter, `text`/`eol` attribute or `ident` is applied (`core.autocrlf` in your config still converts line endings: it needs no attribute). `info/attributes` still applies: it is yours, and sessions are denied `info`. `rw-git` reads no attributes from the checkout either. A Worker that needs the real content stops and names the file: `git lfs pull` writes the git directory, so it is yours to run. This needs git 2.41.0 or later (`--attr-source`); on an older git the launcher refuses. Still run as you: `accept.sh`'s `status` and fast-forward, on content you accept after reading the diff; the dashboard's `status` on a direct build; and a worktree you make by hand with the hook's `git worktree add` line. To check a machine, run `git -C <repo> config --show-origin --get-regexp '^filter\.'` in each repository `repos` lists: it reads every include and `includeIf` that applies there, and git-lfs's global filter once `git lfs install` has run. No output means no driver is defined |
| `run-cost.py`'s diff adds `--no-ext-diff --no-textconv` | **Signing.** `accept.sh -S` runs the program your git configuration names for signing (`gpg.program`, `gpg.ssh.program`, `gpg.ssh.defaultKeyCommand`), by design |
| Every `status` adds `--ignore-submodules=all` | **Your git configuration itself.** These checks decide which repository's configuration git reads, not that it is safe. A session that can write a repository's `.git/config` or `.git/hooks`, or an attributes line in `.git/info`, can name a program there, and every other git command you run in that repository runs it. Every session the launcher or `role-start.py` starts is denied the whole git directory of each repository `repos` lists, by the sandbox and by an `Edit(...)` deny, and a leaf `**/.git` under each granted root (→ What each role can write); one that already holds a `commondir` is refused. Without the sandbox, these checks are a second line only |
| `accept.sh` takes the squash message from `--message <file>` only, never runs an editor, and prints session-written text with every C0, DEL and C1 control but tab and newline removed; so do the launcher's refusals and plan | **Hooks.** These tools and `rw-git` run no hook. `core.hooksPath=/dev/null` turns off the hooks in a hooks folder; config hooks (`hook.<name>.*`, git 2.54) run whatever it says, though git's own `core.hooksPath` documentation still claims `/dev/null` disables all hooks, so each tool reads them on every call, in the checkout the call runs in, and turns each off by name (`hook.<name>.enabled=false`, through `--config-env`), the empty name `[hook ""]` and one that is not UTF-8 included. A hook a session adds between that read and the command it guards still runs: where a session can write a repository's configuration, nothing here closes that. So the scrub gate and the conventions lint never run as a hook on a session's commit or on `accept.sh`'s. A session runs the checks its project hook names itself, sandboxed, before `rw-git commit` (in this repository, `tools/hooks/pre-commit`); this repository's `tests/run.sh` ends with the whole-tree scrub |
| `rw-git` runs every call as described under rw-git, below | |
| Signing is opt-in with `accept.sh -S`; nothing here sets `commit.gpgsign` | **Timing.** The worktree is checked once, at the start. A running session can change its `.git` file or git dir between that check and the git calls that follow |
| | **Stalls.** A FIFO in the worktree's admin dir (`gitdir`, `HEAD`, `commondir`) makes git wait on it. During the check, a 30-second timeout bounds the wait and the repository's worktrees are refused until the FIFO is gone. Git calls after the check have no timeout. Nothing runs either way, but an accept or a dashboard render can hang |
| | **`launch.json` itself.** The configured set is only as safe as `launch.json` is unwritable by a session; a `robowright.json` a session writes can name a repository, but only one `repos` already lists is trusted. The launcher grants nothing at or above the directory it is in, but your own settings can: where `~/.claude/robowright` is a link into a tree your settings grant every session, deny that tree in the sandbox (`sandbox.filesystem.denyWrite`) and in permissions (an `Edit(...)` deny), or stop granting it. Claude Code's file tools follow permission rules, not the sandbox ([sandboxing](https://code.claude.com/docs/en/sandboxing), "What runs outside the sandbox") |

### rw-git

`rw-git` (`skills/robowright/scripts/rw_git.py`) is the one program a session runs outside its sandbox to write a git
directory. `install.sh` writes `~/.local/bin/rw-git`, a `#!/bin/sh -p` wrapper file that runs
`/usr/bin/env -i PATH=/usr/bin:/bin HOME=<your home> <python3> -I <clone>/skills/robowright/scripts/rw_git.py "$@"`,
`<python3>` the path `python3` reports as `sys.executable` at install time. That interpreter's folder and its
`site-packages` must be unwritable to every session. `install.sh` refuses a virtual environment's interpreter, because
a venv's `.pth` files run even under `-I`; a conda or other prefix environment that is not a venv passes that probe,
and there the unwritable-folder rule is what protects you.
`sh -p` reads no `SHELLOPTS`, `PS4` or `ENV`, and `env -i` hands rw_git.py nothing of the
caller's environment. A prefixed call, `VAR=… rw-git`, must never be
auto-approved: how the exclusion matcher treats a leading assignment is not documented as of 2026-10-19, so keep any
rule that would match one out of your settings. The launcher's `--settings` for a Worker and for a direct
build add `"excludedCommands": ["rw-git *"]` and the allow rule `Bash(rw-git *)`: an excluded command goes through
the regular permission flow
([sandboxing](https://code.claude.com/docs/en/sandboxing#run-commands-outside-the-sandbox-with-excludedcommands)), so
without the rule an unattended Worker would stop at its first `rw-git`. A Planner, an Explainer and the Lead commit
nothing and get neither.
`rw-git --help` lists its subcommands, exit codes and refusal codes.

- **Only a bare call leaves the sandbox.** Claude Code takes a call out of the sandbox only when an entry covers every
  command in it, and keeps it sandboxed for a redirect, a `cd`, a command substitution, a subshell or a control-flow
  block, a command starting with `eval` or `xargs`, or a command name from a variable
  ([settings reference](https://code.claude.com/docs/en/settings-reference#sandbox-excludedcommands)). It matches the
  text of the call, so `./rw-git` or a script that calls `rw-git` does not match. Sandboxed, `rw-git` cannot write the
  git directory, so it fails: `cd <worktree> && rw-git add <path>` ran sandboxed and failed on `index.lock` with
  "Operation not permitted" (observed 2026-10-17), and the message does not say why. `rw-git` takes no repository
  argument and acts on the shell's working directory, so run `cd <repo>` as a call of its own, then each `rw-git …`
  bare. Measured on the Desktop app on 2026-10-18, in a session started in a `desktop_roots` root: that `cd`, then
  `rw-git add` and `rw-git commit --message-file …`, each its own call, committed in a repository under the root that
  `repos` does not list. Claude Code keeps a `cd` only inside the session's folders: in a session started in a project
  folder, a `cd` to a repository outside it was reset ("Shell cwd was reset to …"), so such a session cannot run
  `rw-git` there.
- **Its environment is its own.** The installed wrapper runs it with only `PATH` and `HOME`, so nothing from the
  caller reaches it, an ssh agent's `SSH_AUTH_SOCK` included: an agent found only through that variable is out of
  reach. Run directly, it keeps only `USER`, `LOGNAME`, `LANG`, `LC_*`, `TERM`, `TMPDIR` and `SSH_AUTH_SOCK` from the
  caller. Either way it takes `HOME` from the account database, sets `PATH` to the system folders, and runs `/usr/bin/git`.
  So no `GIT_*`, `XDG_CONFIG_HOME`, `DEVELOPER_DIR` (which chooses the program macOS's `/usr/bin/git` runs) or
  `ROBOWRIGHT_*` variable reaches it, and an `X=… rw-git` prefix, if one ever reached it, would choose no repository, no configuration, no sessions root and no program. Its interpreter is the
  one `install.sh` found and wrote into the wrapper, never `PATH`'s at the call; `~/.local/bin` and every folder
  before it on your `PATH` still must stay unwritable to every session, since whatever is found first as `rw-git`
  runs.
- **It names no program git may run.** Every call reads no attributes from the checkout, and sets `-c` overrides for
  each configuration key that names a program, or `--config-env` ones for a key with a name in its middle, which
  holds for a name holding `=` or an empty one: fsmonitor, hooks (config hooks turned off by name), pager, editor, external diff, ssh command, askpass,
  alternate-refs command, credential helpers (your system and global ones are put back, through `--config-env`, since
  a helper's key can hold a URL with `=`), filter, merge and diff
  drivers the repository's configuration names, automatic gc and maintenance, signing, transports other than ssh and
  https, and upload-pack and receive-pack by their own names. Since it reads no attributes from the checkout, `add`
  would store a file raw where plain `git add` stores a git-lfs pointer, and could convert line endings differently.
  So `add` refuses a regular file whose attributes name a filter, `ident` or an encoding. It also refuses one whose
  line endings plain `git add` would convert and rw-git's own `add` would not, or the reverse
  (`refused: attributes`). It works both out with git's own rules: the attributes, then `eol`, then `core.autocrlf`;
  under `text=auto`, git keeps the file as it is when the file looks binary, or when the index copy already holds a
  CRLF. Under `core.safecrlf=true` it also refuses a file plain `git add` stops on, because a checkout would not give
  it back as it is; under `warn` or `false` the bytes match plain git's. It reads `core.autocrlf` and `core.safecrlf`
  as git does, a word or else a boolean in any spelling. It weighs every file `add` would stage, every unchanged one
  whose stat changed, and every racily clean one (its mtime no older than the index's), since plain `git add` hashes
  both again. It reads the attributes with `git check-attr` and `git ls-files --eol`, which run no program; the second
  gives git's own reading of `text`, `crlf` and `eol`, so a string value spelled `set` is not the state `set`. A
  filter, `ident` or an encoding is refused whatever its value, `-filter` included.
- **Its arguments are typed.** Paths stay inside the worktree and name no `.git`; a branch is the worktree's own
  (`robowright/<slug>`, or `robowright/<slug>-u<N>` for a stack), or, in an unmanaged checkout, one
  `protected_branches` does not protect; a commit is a full id of that repository; a message comes from a file under
  the session's own folders. `reset --hard` and `--mixed`, deleting a branch, `--no-verify`, `config`, `init`, a
  plain force push and any write to another session's branch or a protected one are absent, not switched off.
  `push --force-with-lease` is present for an own branch; in an unmanaged checkout, only for one no remote-tracking
  ref whose name ends `/<branch>` (any depth under `refs/remotes/`, case folded) or upstream tracks, as of your last
  fetch, else `branch-tracked`, and `reset` there is held to the same. `reset
  --soft`, `reset --keep` and `rebase` print the old tip first, so a commit they drop from the branch can be found
  again; `commit --amend` refuses a merge (`amend-merge`) and a commit any `refs/remotes/*` ref holds
  (`amend-pushed`), which is only as current as your last fetch. A commit, or an amend, that adds, removes or moves
  a gitlink is refused (`gitlink`), however `.gitmodules` or the configuration says to ignore it; with
  `--scope-file`, one that changes a path the file does not list is refused (`scope`). `fetch --remote` and
  `push --remote` take a remote the repository configures, by name only; a push goes to `origin`, or to a remote
  `launch.json`'s `push_remotes` lists for that repository, else `remote-unknown`, so a session that adds a remote
  cannot push to it.
- **Outside a managed worktree**, in a main checkout or a linked worktree elsewhere, a repository counts when
  `launch.json`'s `repos` lists it, or when its main checkout lies under a granted folder. A granted folder is a
  `launch.json` `desktop_roots` entry (absolute or `~/`, no glob, no link at any prefix; a bad entry refuses, by name,
  every call outside a `repos` repository), or a `sandbox.filesystem.allowWrite` or
  `permissions.additionalDirectories` entry of your own `~/.claude/settings.json`, read through its link (an entry
  with a glob, a relative path, a link, or a spelling other than the disk's is skipped; such a `desktop_roots` entry
  is a bad one). A `denyWrite` or `Edit(…)` deny there, or in the granted folder's own `.claude/settings.json`, takes
  the repository out when the repository's folder, or a folder above it, matches the deny as written or in any letter
  case or Unicode form: `**` as a segment matches any number of segments, `*` matches within one, and a deny with no glob is
  a folder. A relative deny in your own settings is read from `~/.claude` and, through a link, from the folder the link
  leads to; a relative `Edit(…)` rule also matches at any depth below where it is read (`/` for your own settings, the
  granted folder for its own), because rw-git runs outside the session and cannot see which folder it starts in. A deny in any other glob shape (`?`, `[…]`, `{…}`, or `**` inside a segment) refuses every call in a checkout outside `repos`,
  and every commit in an unmanaged checkout, until you rewrite it; rw-git never widens or skips one. `Edit` alone takes out everything. So the
  leaf deny `~/Code/**/.git` leaves `~/Code/notes-app`, while `~/Code/**/.claude` takes out a repository inside a
  `.claude` folder. A grant made for one session only (`--add-dir`, `/add-dir`, a project's settings) is invisible to
  `rw-git`, which runs outside the session. When your settings file lies under a granted folder, where a session could
  write itself a grant, rw-git takes no grant from it and still reads its denies. A settings file that exists but is
  not a readable JSON object refuses the call.

  There, an own branch is any branch `launch.json`'s `protected_branches` does not protect: an object from a
  repository path, spelled as in `repos`, to a list of branch names or `fnmatch` globs, each 1 to 255 bytes with no
  control byte (a bad value refuses, by name, every call there). Every repository gets the default, `main`,
  `master`, `develop`, `release/*` and `hotfix/*`, and the branch `refs/remotes/origin/HEAD` names when it is set; a
  list adds to them, never replaces them. Names match case folded: on macOS
  a loose `refs/heads/Develop` is the file of `develop`. `switch` goes to any existing branch; `switch -c` makes only
  an unprotected one; `commit`, `commit --amend`, `reset`, `rebase`, `cherry-pick`, `stash` and `push` are refused
  while HEAD is on a protected branch (`branch-protected`), on a detached HEAD, or with a merge, rebase, cherry-pick
  or revert stopped half way (but for the `--continue` and `--abort` steps). The message file there is a plain file
  under `/private/tmp/claude-<uid>/` or your `DARWIN_USER_TEMP_DIR`, where your account owns the folder, or under a
  granted folder no deny covers, and never inside the repository. Every override, the environment allowlist,
  `/usr/bin/git`, no hooks and no signing hold there as in a managed worktree.
- **It authenticates the directory, not the caller.** "Own" means the worktree rw-git's working directory is in, not
  the session that called it: a session whose shell sits in another listed worktree commits, rebases, stashes or
  pushes there as that worktree's owner. A session started in a granted root can reach every worktree under it.
  Whether a launched Worker's shell can reach another worktree is unconfirmed.
- **What it cannot stop.** It commits what the session wrote. Code an agent writes that you later build, test or run
  runs as you; read the diff before you do.
- **Whoever can write the folder `rw-git` is found in, or a folder before it on `PATH`, chooses what runs as you.**
  Keep `~/.local/bin`, and every folder before it on your `PATH`, out of every session's grants.

## The recommended setup

The class of attack is public: a repository's own git configuration names a program, and a git you run outside the
sandbox runs it as you. GitSpawn ([Manifold Security, 2026-09-01](https://www.manifold.security/blog/ai-coding-agents-git-hijack))
showed agents' own background `git status` running a repository's `core.fsmonitor`. Pillar Security's
"[Git directories do not have to be called .git](https://www.pillar.security/blog/git-directories-do-not-have-to-be-called-git)"
bypassed a literal `.git/config` deny with `git init --separate-git-dir`. Git's own position (`git help git`, SECURITY):
cloning a repository with untrusted content is generally safe; running git in a `.git` directory from an untrusted
source is not.

The session behaviour named below was measured on macOS with Claude Code 2.1.302 on 2026-10-17, in `claude -p`
sessions given the same deny shapes under other folder names, unless a step names the Desktop app; a step says where
something was not measured. The steps keep every repository you work in under one root folder, `~/Code` here, and what runs as you in a
second folder, `~/Code-Trusted`, that none of them grants to a session.

1. **Install from a clone no session can write, and work in a second clone.** The launcher, the hooks, `accept.sh` and
   `rw-git` run as you from the installed clone. Put it in a folder no session is granted, such as
   `~/Code-Trusted/robowright` (the Quickstart's `~/src/robowright` qualifies only while nothing grants `~/src`), and
   list a second clone under `~/Code` in `launch.json`'s `repos` if you build Robowright itself.
   `install.sh` refuses a link that resolves outside this clone, except a link into a folder shaped like an earlier
   robowright clone (`install.sh` and `skills/robowright/SKILL.md` as regular files, a shape test and not a provenance
   one) and a link to a path that no longer resolves: both are repointed at this clone, and the `linked` line prints
   the old target as `(was …)`. Read those lines.
   Spell every root folder in `launch.json` (`repos`, `projects_root`, `sessions_root`, `accounting_root`, `desktop_roots`) as the disk
   spells it, reached through no link at any component (`/tmp` is a link to `/private/tmp` on macOS), or the
   launcher and `accept.sh` refuse by name.
2. **Grant the root by starting a session in it, not in your user settings.** A folder your user settings grant
   reaches every session the launcher starts (→ What each role can write), so grant nothing there beyond Claude Code's
   defaults. A session's working directory is its grant, and the only `.claude/settings.json` it loads as project
   settings is its start folder's own: not a parent's, and not the repository root's from a subfolder (measured with
   `claude -p`). So start Desktop sessions in `~/Code`. That such a session loads `~/Code/.claude/settings.json`
   (step 3) was measured on the Desktop app for a session started in the root; a Desktop worktree session is
   unmeasured, and Claude Code's docs say it reads project settings from the repository's main checkout rather than
   the worktree ([worktrees](https://code.claude.com/docs/en/worktrees#what-worktrees-share-with-the-main-checkout),
   read 2026-10-17).
3. **Put the leaf denies in `~/Code/.claude/settings.json`, a link into the trusted folder.** Write this file as
   `~/Code-Trusted/code-settings/settings.json`, then `mkdir -p ~/Code/.claude` and
   `ln -s ~/Code-Trusted/code-settings/settings.json ~/Code/.claude/settings.json`:

   ```json
   {
     "permissions": {
       "deny": ["Edit(~/Code/**/.git)", "Edit(~/Code/**/.git/**)",
                "Edit(~/Code/**/.claude)", "Edit(~/Code/**/.claude/**)", "Edit(~/Code/**/.mcp.json)",
                "Edit(~/Code-Trusted)", "Edit(~/Code-Trusted/**)"]
     },
     "sandbox": {
       "filesystem": {"denyWrite": ["~/Code/**/.git", "~/Code/**/.claude", "~/Code/**/.mcp.json", "~/Code-Trusted"]}
     }
   }
   ```

   - **Each deny is written twice.** A `denyWrite` entry refuses Bash but not the Write tool; an `Edit(…)` deny
     refuses both (measured).
   - **Deny each `.git` by its last component.** A wildcard deny holds only up to its first `**`: under
     `~/Code/**/.git/config` a session renames `.git`, writes the config, and renames it back. A deny whose last
     component is the name, `~/Code/**/.git`, still matches after the parent is renamed, and refuses `git init` and
     `--separate-git-dir` there. Measured from `claude -p` sessions started in the root: `touch` and the Write tool into a
     repository's `.git`, `git init` of a new folder, and a write to a linked worktree's `.git` file were refused.
   - **`**` also matches no folder at all**, so `~/Code/**/.claude` covers `~/Code/.claude` itself. Measured from
     `claude -p` sessions started in the root: a new file in `~/Code/.claude` was refused for Bash and the Write tool,
     and a new `.claude` folder below the root for Bash; so was a `.mcp.json` at the root and below it, while a write
     elsewhere under the root succeeded. Renaming `~/Code/.claude`, unlinking or re-pointing the settings link,
     writing through it and writing its target were refused as well, with no run without the deny to compare, so they
     show the link holds, not which rule holds it. The Write tool refused `~/Code-Trusted`; a Bash write there was
     refused too, though that folder is outside the session's grant anyway. The bare `Edit(~/Code-Trusted)` entry was
     not probed.
   - **No session started in the root edits a `.claude` folder under `~/Code`**, a repository's tracked `.claude/`
     rules included, which is why worktrees live at `<repo>/.worktrees/`. A Worker the launcher starts in its worktree
     does not load this file (measured with `claude -p` in a linked worktree), so its tracked `.claude/` prose stays
     writable, and its `.git` leaf deny comes from the launcher's own settings (→ What each role can write).
4. **Name the root in `launch.json`**: `"desktop_roots": ["~/Code"]`. `rw-git` runs outside the session and cannot
   see the folder a session started in, so this entry is how it serves a repository whose main checkout lies under
   `~/Code`. It reads the root's `.claude/settings.json` and leaves out any repository the denies there cover; write
   the denies with `**` and `*` only (→ rw-git, "Outside a managed worktree").
5. **Exclude `rw-git` from the sandbox, and allow it, in your user settings.** Neither grants a folder:

   ```json
   {
     "permissions": {"allow": ["Bash(rw-git *)"]},
     "sandbox": {"excludedCommands": ["rw-git *"]}
   }
   ```

   An excluded command still goes through the permission flow, which an unattended session cannot answer by prompt,
   so give it the allow rule. A call leaves the sandbox only when every command in it matches an entry:
   `cd <repo> && rw-git add <path>` stayed sandboxed and failed on `index.lock` (observed), and a script that calls
   `rw-git` does not match. So `cd <repo>` in a call of its own, then `rw-git …` bare: from a Desktop session started
   in the root, that committed in a repository under it (measured; → rw-git). Never approve, or write a rule for, a
   prefixed call, `VAR=… rw-git`: how the exclusion matcher treats a leading assignment is not documented as of
   2026-10-19 (→ rw-git). Claude Code merges settings lists across scopes
   ([settings](https://code.claude.com/docs/en/settings)), so from your user settings both entries reach every session,
   the launcher's Planners and Explainers included, whose own settings give them neither; `rw-git` still acts only on the directory it runs in (→ rw-git,
   "It authenticates the directory, not the caller").
6. **Set two global git settings.** `git config --global safe.bareRepository explicit` stops git treating a folder of
   `HEAD`, `objects` and `refs` as a repository unless you name it with `--git-dir`: the leaf deny does not match a
   bare repository, so this closes that route (git 2.38 or later). `git config --global core.fsmonitor false` says
   what you mean, but a repository's own `core.fsmonitor` still wins over it; the leaf deny is what keeps a session
   from writing one.
7. **Keep `rw-git` where no session writes** (→ rw-git).

**What it costs.**

- **A session started anywhere but the root is not covered.** A session started in a project folder or a repository
  does not load the root's settings (measured with `claude -p`), so it has no root grant and none of the leaf denies,
  and is expected to write its own repository's git directory as before, but for Claude Code's own protected paths
  (below); no probe wrote one. It also cannot run `rw-git` in a repository outside its own folder, since Claude Code
  reset a `cd` out of a session's folders (→ rw-git). To cover it, start it in the root. Desktop sessions started below the root are
  unmeasured, a Desktop worktree session of a repository under it included (step 2): Claude Code's docs say that one
  reads project settings from the repository's main checkout, not from `~/Code`, so it may get none of the denies.
- **Plain git cannot write under the root.** In a session started in the root, `touch`, the Write tool and `git init`
  were refused on a `.git` under the root (measured), so plain `git add`, `commit`, `switch` and `clone` there are
  expected to fail too, and such a session writes git only through `rw-git`.
- **macOS only.** Claude Code honours a wildcard in `denyWrite` on macOS only; on Linux and WSL2 it skips the entry
  ([settings reference](https://code.claude.com/docs/en/settings-reference#sandbox-path-prefixes)), so there the
  `denyWrite` leaf denies are skipped, and a sandboxed `git init` of a folder under the root is expected to succeed
  (untested). Only macOS is covered here.
- [Protected paths](https://code.claude.com/docs/en/sandboxing#protected-paths) cover `.git/hooks` and `.git/config`
  in the working directory only, not in a directory you add.

**Why not grant `~/Code` in your user settings**, with the same denies beside the grant: a user-settings grant reaches
every session the launcher starts, so every Worker could write all of `~/Code` but the leaf denies (the grant
measured with other folders; the denies beside it seen only at project scope). A user-scope `**/.claude` deny would also reach every Worker and refuse its edits to its worktree's tracked `.claude/`
rules; that is inferred from a project-scope deny standing in for the user-scope one, not observed.

## The threat model: prompt injection

A session reads text it did not write (files, web pages, build logs), and text written to steer a
model can ask it to run a command your install runs unasked, or outside your harness's sandbox.

- **No install's allow rules or sandbox exceptions ship here**, only the MCP entries', each
  reaching its own server. No `launch` key in `launch.json` means `paste`: the launcher prints the
  `claude --bg` line for you (`/robowright-onboard` defaults to it). Under the opt-in `auto` it runs
  it, so the Lead starts Planner, Worker and Explainer sessions unattended, under your settings.
- **A plugin may ask for a helper outside the sandbox**, such as a simulator broker run as a
  launchd agent. If it runs a script from the main clone, point it at a copy no session can write.
- **A repository's own project hook is instructions**: `<repo>/.claude/robowright/project.md` wins
  over a machine-local hook and names a Worker's commands. Read it, as you would a build script,
  before running a session in a repository you did not write.
- **Keep what runs without asking narrow**: a push, deploy or network call your settings
  auto-approve is one an injected instruction can reach.

## The scrub gate is a tripwire

`tools/scrub-gate.sh` refuses a commit or push whose added lines match your install's private list
(`${ROBOWRIGHT_DENYLIST:-~/.config/robowright/denylist}`, never committed, no pattern ever printed).
It catches the everyday slip, nothing more: git does not clone hooks, so it runs only where
`git config core.hooksPath tools/hooks` was run; `--no-verify` skips it; it is not a secret scanner.

## Agent symlinks

`install.sh` symlinks each `agents/` file into `~/.claude/agents/`. The docs cover symlinked skills; the [subagents page](https://code.claude.com/docs/en/sub-agents)
(read 2026-09-26) is silent on symlinked agent files, so this is tested only by use:
if a release stops following the links, the agents vanish.

## History

This repository started from a fresh snapshot of a private tree; nothing predates its first commit.

## Reporting a vulnerability

Use GitHub's private reporting (**Security** tab → **Report a vulnerability**), not a public issue.
