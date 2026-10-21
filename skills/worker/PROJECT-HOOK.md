# Project hook contract

The `worker` handbook is repo-agnostic and platform-agnostic. Everything that names a build
command, a test target, a device, an artifact id, or a repository convention lives in a
**project hook**: one markdown file per repository, read in full at preflight.

**Resolution order**, at preflight:

1. `<repo>/.claude/robowright/project.md` — the hook committed inside the repository. It wins
   whenever it exists, so every worktree carries its own hook and a command that changes is
   changed once, in the repo that owns it.
2. `~/.claude/robowright/projects/<name>.md` — the machine-local hook, matched against
   `git remote get-url origin`. For a repository that cannot carry the file itself.

In a project that spans several repositories, `robowright.json.repos[].path` picks the checkout the
Lead branches a worktree from. It does not change how a Worker resolves its hook: the Worker
resolves the worktree it runs in, by the order above.

**No hook → the Worker refuses to start**, naming both paths it looked at. It never guesses a
build command, never infers one from the tree, and never falls back to another repository's
hook.

The hook is the per-repository counterpart of the machine profile
(`skills/robowright/PROFILE-CONTRACT.md`): the profile says how a session is launched and
budgeted **on this machine**; the hook says what to run, how work is published, and how it is
named **inside one repository**. The profile never names a scheme or a test target; the hook
never says how sessions are launched or billed.

A hook provides these fourteen sections, in this order, each copy-pasteable by an agent with no
other context. A section that does not apply says `None in this repository.` — it is never
omitted, and the numbering never shifts.

1. **Identity** — origin URL patterns, the main clone path with its exact spelling, the default
   base ref, and the artifact ids a build or an install needs (bundle id, application id,
   package name), release and debug spelled separately where they differ. Two lines in this
   section are read by `robowright-resolve`, which scans from the `## 1` heading to the `## 2`
   heading only:
   - **The client table** — required, for one client or many. A `**Clients**` line, then one
     bullet per client, in file order, each naming the platform plugin that client builds with
     (`../robowright/PLUGIN-CONTRACT.md`):
     ```markdown
     **Clients**

     - **iOS** — `platform: ios`
     - **Android** — `platform: android`
     ```
     The row form is `- **<name>** — \`platform: <id>\``; a line that departs from it is not a
     client. A repo that builds with no platform plugin writes `None in this repository.` under
     the `**Clients**` line, and its reading chain ends at the hook. A repo with more than one
     client carries **one subsection per client** in sections 4–8, and a Robowright Session that
     touches two clients owes both gates.
   - **The origin-match line** — required for a machine-local hook (resolution rule 2): the
     origin row carries `` match on `<token>` ``. The token matches `git remote get-url origin`
     when the URL, or the URL without a trailing `.git`, equals the token or ends with the token
     preceded by `/` or `:`. So `example-org/alpha` and `example-org/alpha.git` both match
     `git@example.com:example-org/alpha.git`, and neither matches
     `git@example.com:example-org/alpha-extra.git`. Exactly one machine-local hook may match
     an origin; none or two is a refusal naming the URL and every candidate.
2. **Preflight extras** — the project-specific checks a session makes before touching anything:
   submodules, generated code, a doc or link gate, a baseline or artifact store, lints. One
   line each, with what a failure means and whether it blocks.
3. **Worktree** — how to create one from a base ref, where it lands, any per-worktree build
   output convention, and how to tear it down. Name the constraints that make the obvious
   command wrong (submodules, generated files, gitignored artifacts a removal would destroy),
   and which teardown steps are the Owner's rather than the session's.
4. **Build** — the one command shape, per client, redirected to a log, with the exit code
   captured on its own line. Plus:
   - **The build-output directory** — where this worktree's build products go, so two
     worktrees never share one; preflight records the resolved path in `run.json`.
   - **The verdict lines** — the exact lines or fields that constitute a verdict (the exit
     code, a `SUCCEEDED` / `FAILED` line, a status field in a result file), and **the one
     sanctioned way to read them**: a script, a result-file query, or the `log-reader` agent.
     Anything else, reading the log by hand included, is not a verdict.
   - **What a hang looks like** — no verdict line and no exit code, and what the session watches
     instead (log growth, elapsed time) to tell a hang from slow progress.
   - **What an infrastructure failure looks like** — the shapes that are not a red build: a
     runner that never attached, a device that never booted, dependency resolution that failed.
     Say what the session does with each, because none of them is a verdict either.
   - **The gate command** — optional, and the repository's own: one script that builds, runs the
     scoped (or whole) suite, prints only the verdict lines named here and in section 5, and
     exits with its own code. It is redirected to one log like every other command in this
     section, and read the sanctioned way, so the gate reviewer still has the artifact behind
     the quoted verdict. Name it and say what it prints; where a hook names one, a session runs
     it once for the unit loop's steps 3 and 4 instead of a call each.
5. **Tests** — the one command shape, per client, how to scope a run to the suites a unit
   touches, the known-hanging or deliberately excluded suites, and any two-phase verdict trap.
   Plus:
   - **The verdict lines** — as in section 4: the pass/fail line or field, the counts and where
     they legitimately come from, and the one sanctioned way to read them. Where a runner can
     print counts in two framings (test cases vs executions), say which framing a quoted number
     is in.
   - **What a hang and an infrastructure failure look like** for a test run specifically.
   - **The gate command's test half** — where section 4 names one: how a unit scopes the suite
     through it, how a whole-suite run is asked for, and which verdict lines it prints here.
   - **Source-file patterns** — which paths count as **code** for deciding whether a whole-suite
     run is owed. A commit touching any of them owes that client's whole suite before it is accepted;
     a commit touching none of them — docs, evidence, ledgers, a change description — owes
     nothing, and cites the last green run's verdict instead. Per client when there is more than
     one, plus the cross-client cases.
6. **Kind checks** — what each `kind` in a brief's unit table selects beyond build and tests:
   the equivalence check a `refactor` owes, the mutation harness a `tests` unit drives, a
   guard suite, a doc gate. Command shapes, and the rule each one exists to enforce.
   For each kind, the row in the kind → check table of the plugin a client names is the
   default; a hook row for the same kind **replaces** it whole and never adds to it. A hook may
   also add **trigger rows**, in the prose form `<what the diff touches> → <check>, <when>`:
   every trigger row whose subject the diff touches fires regardless of the unit's kind, on top
   of the kind row. One subject is not in the diff: **`depends_on non-empty`** fires whenever
   `run.json.depends_on` has an entry, whatever the diff touches. Its check receives each
   entry's `build_output` and its read-only checkout `<session_dir>/deps/<session>` (worker
   Phase 0 step 7a). A check that needs another platform's runtime runs under that platform's
   lock, which the Planner adds to `run.json.locks`; the Worker still loads one plugin. When
   that runtime cannot be reached, or a non-empty `build_output` no longer exists (teardown
   after an accept deletes a worktree's build folder), the check reports `unverified`, in the ledger and as a
   manual-pass row, never pass. Illustrative, not a shipped row: an iOS session finishes with a
   DerivedData `build_output`, an app-extension unit's brief names it in `depends_on`, and the
   extension's hook row reads `depends_on non-empty → scripts/verify-extension.sh <build_output>,
   under the ios-build lock`. A hook with no kind row and no trigger row to add writes
   `None in this repository.`
7. **Device** — the environment a change is observed in: a simulator, an emulator, a browser, a
   headless renderer, or **none**. How to install, reach a deterministic starting state, launch
   the right build (name the artifact id when debug and release differ), read the UI, assert on
   it, and capture a screenshot or dump to `evidence/`. Plus:
   - **The device lease** — what is leased (a device id, a port, a display), how a session
     claims it, how it releases it, and what to do when the claim fails. Releasing happens at
     handoff *and* on an early stop.
   - **Any machine-wide build lock** — its **name** (lowercase letters, digits, hyphens; a
     brief that needs it adds the name to `run.json.locks`, and a launcher maps each
     name to `<sessions root>/.<name>-lock`), what it protects, the atomic take, how to tell a live
     holder from a stale one, and the exact point it is released. A lock that outlives its
     session blocks every later session, so the release point is named explicitly or it is not
     a lock.
8. **Regression sweep** — how a base build and a tip build are compared on one device: the
   walk, the comparison, what blocks and what is advisory, how a deliberate change is
   re-recorded, and the standing rule that an artifact which changed in a way nobody can
   explain is a finding rather than a re-record.
9. **Commits and history** — **the commit tool is the profile's (→ Tools); the hook adds
   message conventions only**: subject and body shape, the types and scopes in use, what a
   verification block quotes, required trailers, and any obligation a commit message must
   carry (a port decision, a ticket reference). Plus the history facts a session can break:
   backup-ref naming, the fold-and-restack procedure, the tree-identity check, and anything
   derived from history shape or commit count.
10. **Publishing** — what "published" means **in this repository** (a local branch and an owner
    brief; or pushed branches and draft pull requests), title and body markers,
    what runs on a draft, how finished work is accepted, and who accepts it. Also: what a finished
    change must carry (a description per unit, one for the whole change, or none) and that
    description's format; where the squash message file sits beside it (the core's is
    `<session_dir>/prs/<unit>/commit-message.txt`, in section 9's commit form with its
    trailers); the review-size ceiling for one change; and whether a predecessor
    branch not yet in `main` is a valid base for the next brief. Plus what publishing obliges on top
    of that: cross-client port obligations, stamps or manifests that may only advance after
    an accept, generated artifacts that must travel with the change.

    **Publish strategies.** The section names exactly one strategy, in a line
    `publish_strategy: <name>` that is its first non-blank line after the heading, so a script
    or a Reader finds it without parsing prose — `publish_strategy: local-branch`, bare, not in
    backticks. The set is closed:
    - `draft-pr` — pushed branches and draft pull requests, left for the Owner to mark ready.
    - `local-branch` — a local branch and an owner brief; nothing is pushed.
    - `push-to-branch` — commits pushed to a remote branch the hook names, with no pull request.
    - `pr-plus-deploy` — a pull request plus a deploy of the change to a preview the hook names.

    The section's prose says what the name does in this repository. Each strategy brings a
    runtime requirement the hook states and its duties check: `draft-pr` and `pr-plus-deploy`
    a remote and `gh`, `push-to-branch` a remote, `local-branch` none. The core records the
    requirement and does not check it. `run.json.publish` carries the `publish_strategy` name,
    or `false` or `null` for no publishing.

    **The `accept` row.** The section carries one line, `accept: <command> — <who runs it>`, naming
    how finished work is integrated into this repository's `main`. The core ships
    `~/.claude/skills/lead/scripts/accept.sh --tip <tip> --message <session_dir>/prs/<unit>/commit-message.txt <session_dir>`,
    naming the full id of the reviewed branch tip and the squash message file the finished change carries, and **the Owner runs it**; no
    role does. It refuses, by name and before writing anything, unless `--tip` is a full commit id
    and the branch is still at it (`tip-missing`, `tip-invalid`, `tip-moved`), the
    message file is readable, the session is `done`, its `INTAKE.md` exists, the main clone's
    branch is an ancestor of the session branch's tip, the main clone is clean, and accept.sh itself is not inside
    the main clone or a worktree of it (`accept-in-target`). It takes the
    squash message from the file, `#` lines dropped, and refuses an empty one or git's
    `Squashed commit of the following:` subject. Without `--message` it refuses `message-missing`
    and opens no editor. It commits the tip's tree onto that branch, fast-forwards it, and
    records `run.json.accepted` through `session-state.py`. It prints the tree-identical check and
    the teardown line, and never runs the teardown. A direct build, which has no session directory,
    is accepted with `~/.claude/skills/lead/scripts/accept.sh --direct --base <base> --tip <tip> --message <file> <project_dir> <unit>`: it
    applies `<base>..robowright/<unit>` as one commit, merging the range when `main` has moved and
    refusing a conflict, and records the accept in `<project_dir>/prs/<unit>/ACCEPTED.json`. A
    repository that integrates another way, such as a pull request merged on the forge, names that
    command instead.
11. **Toolbelt map** — every script or tool a Robowright Session may need in this repository, one
    line each, with anything denied or Owner-only marked as such. Plus **the MCP servers**, if a
    session here needs any: which servers a brief here may pick in `run.json.mcp`, from the
    approved list at `../robowright/mcp/`, and what each is for. Say `None in this repository.`
    and no brief here names a server, so a session starts with none.
12. **Traps** — everything that has cost a session before, one line each with the fix.
13. **Naming** — ticket or slug format, base ref, branch format, session-name prefixes for
    every role, and the attended task session's name.
14. **Duties** — a table of `role · extension point · skill or script to run`, the profile's
    shape (`../robowright/PROFILE-CONTRACT.md` → Duties names the nine extension points, and
    its Review Overlay paragraph says what a `reviewer.overlay` row names), one row per
    point. A handbook reaching a point runs the profile's rows, then these, in order; a point
    this repository adds nothing to says `None in this repository.`

Before section 1, a hook may carry a short preamble: a provenance line (when its commands were
last verified against the repo), a pointer to the repository's collaboration policy, and any
list a profile duty names — a learning-topics opt-in list, for instance, where the profile's
`planner.brief` duty reads one. The preamble never replaces a section.

Anything a phase in `SKILL.md` says "per the project hook" points at one of these sections.
