# install.sh — test ledger

2026-10-17. U46, rows R10.1–R10.7 of `BEHAVIORS.md`, plus R1.4 and R1.5 widened for the `rw-git` link. R10.1–R10.6, R1.4
and R1.5 were seen red against an `install.sh` that linked no `rw-git`. R10.7 was green there, since that install
made no bin folder either, so it owed a kill: I07. Each mutation ran in its own scratch copy of the tree, with
its red set predicted in writing first.

| # | Mutation | Predicted red | Observed red | Verdict |
|---|---|---|---|---|
| I01 | link named `rw_git`, not `rw-git` | R10.1, R1.5 | R10.1, R1.5, R1.4, R10.3, R10.6 | KILLED |
| I02 | the note drops "or any folder before it on PATH" | R10.2, R1.4 | same | KILLED |
| I03 | an existing `rw-git` link left as it is | R10.3 | same | KILLED |
| I04 | no refusal of a non-link at `rw-git` | R10.4 | same | KILLED |
| I05 | `~/.local/bin` not checked for a link | R10.5 | same | KILLED |
| I06 | uninstall removes any `rw-git` link, wherever it points | R10.6 | same | KILLED |
| I07 | the bin folder made even with no `rw_git.py` in the clone | R10.7 | R10.7, R5.2, R8.1, R8.3, R9.2: their line counts include the link | KILLED |

No survivors. No test was deleted.

## U52b · the rw-git wrapper (R10.1–R10.9)

Red before the code: R10.1, R10.2, R10.3, R10.8 on their assertions, R10.9 an error (the link ran the stub with no
JSON). Green at red, each owing a kill: R10.4 (both cases, the old refusal of any regular file), R10.5, R10.6,
R10.7. R10.9 first went red on the green build too: the interpreter adds `__CF_USER_TEXT_ENCODING` (macOS) and
`LC_CTYPE` (PEP 538) under `env -i`, so the test sets those two aside; the caller's variables are still asserted absent.

| # | Mutation | Predicted | Observed | Verdict |
|---|---|---|---|---|
| FM1 | `#!/bin/sh`, no `-p` | R10.1 R10.9 | R10.1 R10.3 R10.6 R10.8 R10.9 | KILLED |
| FM2 | `env` without `-i` | R10.1 R10.9 | R10.1 R10.3 R10.6 R10.8 R10.9 | KILLED |
| FM3 | python without `-I` | R10.1 R10.9 | R10.1 R10.3 R10.6 R10.8 R10.9 | KILLED |
| FM4 | any regular file refused | R10.8 | R10.8 | KILLED |
| FM5 | any wrapper counted as this clone's | R10.4 R10.6 | R10.4 R10.6 | KILLED |
| FM6 | uninstall skips the wrapper | R10.6 | R10.6 | KILLED |
| FM7 | uninstall removes any regular file | R10.6 | R10.6 | KILLED |
| FM8 | a link again, not the file | R10.1 R10.3 R10.8 R10.9 | same | KILLED |
| FM9 | an existing wrapper never rewritten | R10.8 | R10.8 | KILLED |
| FM10 | a linked bin folder not refused | R10.5 | R10.5 | KILLED |
| FM11 | no `rw_git.py` check | R10.7 | R10.7 | KILLED |
| FM12 | the `/usr/bin/python3` shim | R10.1 | R10.1 R10.3 R10.8 R10.9 | KILLED |

## R10.10–R10.11, and R10.2's interpreter line (U58)

Red before the code, each on its assertion: R10.2 (no `rw-git: interpreter` line after `wrote`), R10.10 (exit 0: the
venv's interpreter was pinned), R10.11 (every skill linked before the exit). R1.4, which lists every stdout line, went
red on the new line once it was printed, and gained it. R10.10 uses a real `python3 -m venv --without-pip`, not the PATH stub the brief named: a stub would answer the probe
itself and never run its `sys.prefix` comparison.

| # | Mutation | Predicted | Observed | Verdict |
|---|---|---|---|---|
| FM13 | the probe always prints `base` | R10.10 | R10.10 | KILLED |
| FM14 | the empty-path branch never taken | R10.11 | R10.11 | KILLED |
| FM15 | a venv not refused | R10.10 | R10.10 | KILLED |
| FM16 | no `rw-git: interpreter` line | R1.4 R10.2 | R1.4 R10.2 (the whole suite) | KILLED |
