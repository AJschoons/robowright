---
paths:
  - "skills/**/scripts/**"
  - "skills/**/hooks/**"
  - "tools/**"
  - "install.sh"
---

# Session inputs

These scripts read files a session wrote and run outside its sandbox. `SECURITY.md` → "Values a
session can write" lists every such value and its check; a value you add gets a row there.

- **Hold every session-file value to its shape before you use it**, through the check that already
  exists:
  - a model: the `form` in `skills/robowright/models.json`, via `check_model` in `run-launch.sh` or
    `role-start.py`;
  - a session id: `SESSION_UUID_FORM` in `run-launch.sh`;
  - a ticket or a directory name: `TICKET_FORM` and `in_unit_form` in `run-launch.sh`;
  - a commit id: `COMMIT_ID` in `skills/worker/scripts/run-cost.py`;
  - a lock name: `LOCK_NAME` in `skills/robowright/scripts/session-state.py`;
  - `run.json` state fields: write them only through `session-state.py`, whose integrity check
    flags a hand edit.

  A new value gets a named check beside these, and a test that a wrong shape is refused.
- **Build JSON only with `jq --arg`/`--argjson` or `json.dumps`.** Never `printf`, `echo`, a
  heredoc, or a jq filter in double quotes. `session_settings` in `run-launch.sh` is the pattern.
- **No arithmetic on file data.** `$(( ))`, `(( ))`, `let` and `[[ -gt ]]` evaluate their operand
  as an expression. Match plain digits first and read them with `10#`, as `stop-gate.sh` does with
  its counter.
- **Pass a value as `--opt=value`, and end options with `--end-of-options` (git) or `--`**, so a
  value starting with `-` never reads as a flag. See `--resume=` in `run-launch.sh` and the diff in
  `run-cost.py`.
- **Run git in a session's worktree only through `skills/robowright/scripts/owner_git.py`.**
  - Python: `owner_git.check(worktree)` first, then `owner_git.run(...)`.
  - Shell: `owner_git.py worktree <path>`, then `GIT=(git)` plus the lines of `owner_git.py flags <repo>`
    before `--env`, with each line after it exported; then `"${GIT[@]}"` (see `hardened_git` in `accept.sh`).
- **Never `eval`, `shell=True`, `os.system`/`os.popen`, or `sh -c`/`bash -c` with data in the
  command string.** If you need a shell, pass a constant script and give it the data as
  positional arguments.
- **Write into a session's folder or worktree, or the accounting root, only through
  `skills/robowright/scripts/session_write.py`.** The session can plant a symlink, a FIFO or a hard
  link at any name there.
  - Python: `session_write.append`, `replace` and `locked`, and `write_json_atomic` for `run.json`.
  - Shell: pipe into `session_write.py append|replace <path>`, never `>` or `>>`.
- **Fence or strip session text before you print it to the Owner.** Use `owner_git.shown()`, or
  `owner_git.py show` from shell. In the roster use `fenced()` in `skills/lead/scripts/run-roster.py`.

`tests/conventions/` is a tripwire for part of this:
- the shell items, and JSON built on one line of shell, everywhere in scope;
- arithmetic only in `skills/**/hooks/**`;
- a bare `>` or `>>` to a file only in `skills/**/hooks/**` and `run-launch.sh`;
- raw git only in `accept.sh`, `run-launch.sh`, `robowright-dash.py`, `run-cost.py` and
  `session-state.py`.

`tests/conventions/lint.py` lists what it cannot see. Those cases, and every other item above, are
yours and the reviewer's. A site it flags that is safe gets a line in
`tests/conventions/allowlist.txt`, with a reason a reviewer can check.
