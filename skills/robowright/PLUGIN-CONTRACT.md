# Platform plugin contract

A **platform plugin** is one file at `~/.claude/robowright/plugins/<platform>.md` if the machine
has one there, else at `~/.claude/skills/robowright/plugins/<platform>.md`: what is true of a
toolchain, in every repository that builds with it. A file at the first path shadows the second
without a warning, and a `base:` resolves in the same order. A project hook's client table
names it (`../worker/PROJECT-HOOK.md` §1), and `robowright-resolve` prints it into a role's reading
chain after the machine profile and the hook.

A client that names a platform with no plugin on disk is a refusal: the resolver names the id
and the path it looked for. A role never borrows a neighbouring platform's file.

The plugin provides these sections, in this order, each copy-pasteable by an agent with no
other context. A section that does not apply says `None on this platform.` — it is never
omitted, and the numbering never shifts.

0. **Identity** — the file's first non-blank line is `platform: <id>`, with `<id>` equal to the
   file's name without `.md`. The next non-blank line may be `base: <id>`, naming the plugin
   this one builds on; the base is read first and this file adds to it. **One level**: a base
   plugin carries no `base:` of its own, and the resolver refuses a chain of two, naming both
   ids. Then the toolchain and the versions the file was last verified against.
   ```
   platform: watchos
   base: ios
   ```
1. **Verdict shapes** — for a build and for a test run: the exact lines or fields that are a
   verdict (the exit code, a `SUCCEEDED` / `FAILED` line, a status field in a result file, the
   count lines and which framing they are in), and **the one sanctioned way to read them** — a
   script, a result-file query, or the `log-reader` agent. The hook names the commands; the
   plugin names what their output means.
2. **Hang shape** — what a stuck build or test run looks like on this toolchain: no verdict
   line and no exit code, what the session watches to tell a hang from slow progress (log
   growth, elapsed time), the threshold, and the kill-and-re-run rule.
3. **Infrastructure-failure shapes** — the outputs that are not a red: a runner that never
   attached, a device that never booted, dependency resolution that failed. Each with what the
   session does, because none of them is a verdict.
4. **Device model** — the environment a change is observed in: a simulator, an emulator, a
   browser, a headless renderer, or none. How to install, reach a deterministic starting state,
   launch the right build, read the UI, assert on it, and capture a screenshot or dump to
   `evidence/`. What is leased, how a session claims and releases it, and what it does when the
   claim fails.
5. **`device: {}` schema** — the keys of the `device` object a Robowright Session records in
   `run.json` for this platform, each with its type and the step that writes it. It is the one
   block of `run.json` a plugin owns, and core never validates it.
   ```json
   {"udid": "...", "os": "iOS 26"}
   ```
   That is iOS's.
6. **Lock name and liveness rule** — the machine-wide resource a session holds while it uses
   the device or the toolchain: its **name** (lowercase letters, digits, hyphens; a brief that
   needs it adds the name to `run.json.locks`, and a launcher maps each name to
   `<sessions root>/.<name>-lock`), what it protects, the atomic take, how to tell a live holder
   from a stale one, and the exact release point — at handoff and on an early stop. Two
   mechanisms are in use and either may be named: an atomic `mkdir` of the lock directory, and
   a pid recorded in it and checked with `kill -0`. iOS's, as its plugin states it:
   `**Name: \`ios-build\`.** A brief whose units build for iOS on a pinned device carries
   \`"locks": ["ios-build"]\``.
7. **Kind → check table** — the checks a Worker runs for each unit kind beyond build and tests:
   one row each for `tests`, `docs`, `refactor`, `behavior` and `ui`, every row answered or
   `None on this platform.`, each with its command shape and the rule it enforces. A hook row
   for the same kind replaces a plugin row whole; it never adds to it. A hook adds
   **trigger rows** on top: a row keyed on what the diff touches rather than on a kind, in the
   form `<what the diff touches> → <check>, <when>`, or on `depends_on non-empty`, which fires
   whatever the diff touches (`../worker/PROJECT-HOOK.md` §6). The Worker reads trigger rows as prose;
   `robowright-resolve` never parses them. Two, for their shape:
   - anything that draws → `./scripts/verify.sh --render`, always…
   - anything with a user-facing string → `python3 scripts/i18n.py audit`…
8. **Sweep method** — how a base build and a tip build are compared on one device: the walk,
   the comparison, what blocks and what is advisory, how a deliberate change is re-recorded,
   and the standing rule that an artifact which changed in a way nobody can explain is a
   finding rather than a re-record.

The plugin is the toolchain's counterpart of the project hook. The hook says what to run in one
repository — its commands, paths, clients and trigger rows; the plugin says what that toolchain's
output, device and lock mean wherever it runs. A fact that would differ between two repositories
on the same toolchain belongs in the hook.
