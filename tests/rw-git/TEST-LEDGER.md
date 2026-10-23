# rw-git — test ledger

2026-10-17. U46. Every row of `BEHAVIORS.md` was written before `rw_git.py`, and seen red against a missing or
unfinished `rw_git.py`, except E7, which went red against the shipped code and found a gap: rw-git's own `launch.json`
and worktree lookups ran git with the caller's environment, so a caller's `DEVELOPER_DIR` chose the program macOS's
`/usr/bin/git` runs. `main` now keeps only the variables `KEPT` names, plus `LC_*`, before anything runs.

Each mutation ran in its own scratch copy of the tree, one suite run per mutation, the red set predicted in writing
first. The table is the last full run, made after review 3's fixes. Ids M69–M97 were reassigned in review 3.

| # | Aimed at | Mutation | Predicted red | Observed red | Verdict |
|---|---|---|---|---|---|
| M01 | W1 | `return os.path.join(entries, entry)` → `continue` | W1 W8 S1 S2 S3 S4 S5 S6 S7 S8 S9 S10 S11 S12 S14 R1 R2 R3 R4 R5 R6 R7 R9 R10 R11 R13 R14 R15 K0 K1 K2 K13 K14 K16 K17 K19 K20 K22 E1 E2 E4 | 72 rows | KILLED; predicted, stayed green: R1 |
| M02 | W2 | `if worktree == repo:⏎ return common` → `if worktree == repo:⏎ raise Refused("worktree-unlisted", …` | W2 R8 | K19 R8 W2 | KILLED; also red: K19 |
| M03 | W3 W4 W7 | `worktree, repo = owner_git.check(os.getcwd(), owner_git.i…` → `worktree, repo = os.path.realpath(os.getcwd()), repos[0]` | W3 W4 W7 | W3 W4 W7 | KILLED |
| M04 | W5 | `raise Refused("launch-config", str(refusal)) from None⏎ try:` → `repos = []⏎ try:` | W5 | W5 W6 | KILLED; also red: W6 |
| M05 | W6 | `for entry in role_grants.spelled_repos():⏎ role_grants.un…` → `(removed)` | W6 | W6 | KILLED |
| M06 | W8 | `WORKTREE_FOLDERS = (".worktrees", ".claude/worktrees")` → `WORKTREE_FOLDERS = (".worktrees",)` | W8 | W8 | KILLED |
| M07 | E6 E7 | `if name in KEPT or name.startswith("LC_")}` → `if not name.startswith("GIT_")}` | E6 E7 | E6 E7 | KILLED |
| M08 | E4 | `GIT = "/usr/bin/git"⏎SAFE_PATH = "/usr/bin:/bin:/usr/sbin…` → `GIT = "git"⏎SAFE_PATH = os.environ["PATH"]` | E4 | E4 | KILLED |
| M09 | S1 | `found.append(relative)⏎ return found` → `found.append(relative)⏎ return found[:1]` | S1 | R18 R26 S1 | KILLED; also red: R18 R26 |
| M10 | S2 | `"--staged" if staged else "--worktree"` → `"--worktree"` | S2 | S2 | KILLED |
| M11 | S3 | `"--staged" if staged else "--worktree"` → `"--staged"` | S3 K13 K19 | K13 K19 S3 | KILLED |
| M12 | S4 | `"commit", "-F", "-"` → `"commit", "--cleanup=verbatim", "-F", "-"` | S4 | S4 | KILLED |
| M13 | S5 | `return run(place, "switch", "--no-track", f"--create={bra…` → `return run(place, "branch", "--no-track", branch)` | S5 | S5 | KILLED |
| M14 | S6 | `return run(place, "switch", "--no-guess", branch)` → `return run(place, "switch", "--no-guess", "--detach", bra…` | S6 | S6 | KILLED |
| M15 | S7 | `owner_git.emit(sys.stdout, f"rw-git: rebase: {branch} was…` → `(removed)` | S7 | S7 | KILLED |
| M16 | S8 | `*(["--autosquash"] if autosquash else [])` → `*([])` | S8 | S8 | KILLED |
| M17 | S9 | `*(["-c", "core.editor=true"] if step == "--continue" else…` → `*([])` | S9 | S9 | KILLED |
| M18 | S10 | `"cherry-pick", target)` → `"cherry-pick", "--no-commit", target)` | S10 | K14 K17 S10 S11 | KILLED; also red: K14 K17 S11 |
| M19 | S11 | `return run(place, "cherry-pick", step)` → `return run(place, "cherry-pick", "--quit")` | S11 | S11 | KILLED |
| M20 | S12 | `if place.slug and subject.endswith(tag)` → `if place.slug` | S12 R14 | R14 S12 | KILLED |
| M21 | S13 | `"origin", "+refs/heads/*:refs/remotes/origin/*")` → `"origin", "refs/heads/*")` | S13 K11 | 11 rows | KILLED |
| M22 | S14 | `*([f"--force-with-lease=refs/heads/{branch}"] if lease el…` → `*([])` | S14 | S14 | KILLED |
| M23 | S15 | `stash-none no stash entry is this worktree's` → `(removed)` | S15 | S15 | KILLED |
| M24 | S16 | `HELPER_SCOPES = ("system", "global", "unknown")` → `HELPER_SCOPES = ("system", "unknown")` | S16 | S16 | KILLED |
| M25 | R1 | `raise Refused("usage", f"rw-git {owner_git.shown(' '.join…` → `return (lambda place: run(place, *args)), []` | R1 | R1 | KILLED |
| M26 | R2 | `if full != place.worktree and not full.startswith(place.w…` → `if False:` | R2 | R2 | KILLED |
| M27 | R3 | `if os.path.islink(current):` → `if False:` | R3 | R3 | KILLED |
| M28 | R4 | `if any(part.lower() == ".git" for part in parts):` → `if False:` | R4 | R4 | KILLED |
| M29 | R5 | `return branch == own or re.fullmatch(re.escape(own) + r"-…` → `return branch.startswith(own)` | R5 | R5 | KILLED |
| M30 | R6 | `def switch(place, create, branch):⏎ own_branch(place, bra…` → `def switch(place, create, branch):⏎ if create:⏎ own_branc…` | R6 | R6 | KILLED |
| M31 | R7 R8 | `def commit(place, path):⏎ own_head(place)` → `def commit(place, path):` | R7 R8 | R7 R8 | KILLED |
| M32 | R9 | `if read(place, "rev-parse", "--verify", "--quiet", "--end…` → `if False:` | R9 | R9 | KILLED |
| M33 | R10 | `if not (path.startswith(session) or (prs is not None and …` → `if False:` | R10 | R10 | KILLED |
| M34 | R11 | `os.O_RDONLY \| os.O_NOFOLLOW \| os.O_NONBLOCK, dir_fd=fol…` → `os.O_RDONLY \| os.O_NONBLOCK, dir_fd=folder)` | R11 | R11 R19 | KILLED; also red: R19 |
| M35 | R12 | `if strategy not in PUSHED:` → `if False:` | R12 | R12 | KILLED |
| M36 | R13 | `def push(place, lease, branch):⏎ own_branch(place, branch)` → `def push(place, lease, branch):` | R13 | R13 | KILLED |
| M37 | R14 | `raise Refused("stash-none",` → `return 0⏎ raise Refused("stash-none",` | R14 | R14 | KILLED |
| M38 | R15 | `return 0 if done.returncode == 0 else EXIT_FAILED` → `return 0 if done.returncode == 0 else EXIT_REFUSED` | R15 S9 S11 K10 K23 P1 | K10 K23 P1 R15 S11 S9 | KILLED |
| M39 | K1 | `"core.fsmonitor=false",` → `(removed)` | K0 K1 | K0 K1 | KILLED |
| M40 | K2 | `"core.hooksPath=/dev/null",` → `(removed)` | K0 K2 | K0 K2 | KILLED |
| M41 | K3 | `"core.pager=cat",` → `(removed)` | K3 | K3–K6 | KILLED |
| M42 | K4 | `"core.editor=false",` → `(removed)` | K3 | K3–K6 | KILLED |
| M43 | K5 | `"sequence.editor=false",` → `(removed)` | K3 | K3–K6 | KILLED |
| M44 | K6 | `"diff.external=",` → `(removed)` | K3 | K3–K6 | KILLED |
| M45 | K7 | `"core.sshCommand=ssh",` → `(removed)` | K7 | K7 | KILLED |
| M46 | K8 | `"credential.helper=",` → `(removed)` | K0 K8 | K8 | KILLED; predicted, stayed green: K0 |
| M47 | K9 | `"core.askPass=",` → `(removed)` | K9 | K9 | KILLED |
| M48 | K9 | `dict(os.environ, GIT_TERMINAL_PROMPT="0")` → `dict(os.environ)` | K9 | none | SURVIVED; predicted, stayed green: K9 |
| M49 | K9 | `"core.askPass=",` → `(removed)` | K9 | K9 | KILLED |
| M50 | K10 K23 | `NAMED = ((re.compile(r"protocol\.(.+)\.allow"), "never"),` → `NAMED = (` | K10 K23 | K10 K23 | KILLED |
| M51 | K11 | `run(place, "fetch", UPLOAD_PACK,` → `run(place, "fetch",` | K11 | K0 K11 | KILLED; also red: K0 |
| M52 | K12 | `run(place, "push", RECEIVE_PACK,` → `run(place, "push",` | K12 | K0 K12 | KILLED; also red: K0 |
| M53 | K13 | `(re.compile(r"(filter\|merge\|diff)\..+\.(clean\|smudge\|…` → `(removed)` | K0 K13 | K13 | KILLED; predicted, stayed green: K0 |
| M54 | K14 | `(re.compile(r"(filter\|merge\|diff)\..+\.(clean\|smudge\|…` → `(removed)` | K14 | 11 rows | KILLED |
| M55 | K15 | `"core.alternateRefsCommand=",` → `(removed)` | K15 | K15 | KILLED |
| M56 | K16 | `"gc.auto=0",⏎ "maintenance.auto=false",` → `(removed)` | K16 | K16 | KILLED |
| M57 | K17 | `"commit.gpgSign=false",` → `(removed)` | K0 K17 | K0 K17 | KILLED |
| M58 | K18 | `(re.compile(r"http\..+\.cookiefile"), ""),` → `(removed)` | K18 | K18 | KILLED |
| M59 | K18 | `"http.cookieFile=",` → `(removed)` | K18 | K18 | KILLED |
| M60 | K19 | `f"--work-tree={worktree}",` → `(removed)` | K19 | K19 | KILLED |
| M61 | K20 | `"rebase", "--no-update-refs",` → `"rebase",` | K20 | K20 | KILLED |
| M62 | K21 | `"--refmap=",` → `(removed)` | K21 | K21 | KILLED |
| M63 | K22 | `"remote.origin.mirror=false",` → `(removed)` | K22 | K22 | KILLED |
| M64 | K22 | `"push.followTags=false",` → `(removed)` | K22 | K22 | KILLED |
| M65 | P1 | `PROTOCOLS = ("ssh", "https")` → `PROTOCOLS = ("ssh", "https", "file")` | P1 | P1 | KILLED |
| M66 | K13 | `return list(attributes), extra` → `return [], extra` | — | 9 rows | KILLED, not its aim |
| M67 | E5 | `os.environ.update(kept, PATH=SAFE_PATH, HOME=owner_home())` → `os.environ.update(kept, PATH=SAFE_PATH)` | E5 | E5 | KILLED |
| M68 | E1 E2 E3 E6 E7 | `if name in KEPT or name.startswith("LC_")}` → `if name}` | E1 E2 E3 E6 E7 | E1 E2 E3 E6 E7 | KILLED |
| M69 | R16 R17 | `unconverted(place, relative)` → `(removed)` | R16 R17 R21 R24 R25 R26 R27 R29 R30 K13 | 11 rows | KILLED |
| M70 | R16 | `CONVERTING = ("filter", "ident", "working-tree-encoding")` → `CONVERTING = ("filter", "working-tree-encoding")` | R16 | R16 | KILLED |
| M71 | R16 | `CONVERTING = ("filter", "ident", "working-tree-encoding")` → `CONVERTING = ("filter", "ident")` | R16 | R16 | KILLED |
| M72 | R21 | `if value in ("set", "input"):⏎ return "text"` → `if value in ("set", "input"):⏎ return "auto"` | R21 | R21 R25 R30 R31 | KILLED; also red: R25 R30 R31 |
| M73 | R26 | `return crlf, crs > crlf or nul > 0 or (printable >> 7) < …` → `return crlf, crs > crlf or (printable >> 7) < controls` | R26 | R26 | KILLED |
| M74 | R11 | `return os.open(parts[-1], os.O_RDONLY \| os.O_NOFOLLOW \|…` → `return os.open(parts[-1], os.O_RDONLY \| os.O_NOFOLLOW, d…` | R11 | R11 | KILLED |
| M75 | R22 | `fd = open_unlinked(place.worktree.split("/")[1:] + name.s…` → `fd = os.open(os.path.join(place.worktree, name), os.O_RDO…` | R19 R22 | R19 R22 | KILLED |
| M76 | R16 R17 | `*CONVERTING, *LINE_ENDINGS, data=stdin,⏎ attributes=True))` → `*CONVERTING, *LINE_ENDINGS, data=stdin,⏎ attributes=False))` | R16 R17 R21 R24 R26 R27 R29 | 10 rows | KILLED |
| M77 | R18 | `if value == "unset":⏎ return "binary"` → `(removed)` | R18 | R18 R25 | KILLED; also red: R25 |
| M78 | R20 | `if not stat.S_ISREG(os.fstat(fd).st_mode):⏎ os.close(fd)⏎…` → `(removed)` | R20 | R20 | KILLED |
| M79 |  | `listed = call(place, "ls-files", "-z", "--modified", "--o…` → `listed = call(place, "ls-files", "-z", "--modified", "--o…` | — | none | SURVIVED |
| M80 | R18 | `return crlf, crs > crlf or nul > 0 or (printable >> 7) < …` → `return crlf, nul > 0 or (printable >> 7) < controls` | R18 | R18 | KILLED |
| M81 | R26 | `if last == b"\x1a":⏎ controls -= 1 # git does not count a…` → `(removed)` | R26 | R26 | KILLED |
| M82 | R23 | `except OSError:⏎ return None⏎ if not stat.S_ISREG` → `except OSError:⏎ return "unreadable"⏎ if not stat.S_ISREG` | R22 R23 | R19 R20 R22 R23 | KILLED; also red: R19 R20 |
| M83 | R21 | `for key in ("text", "crlf"):` → `for key in ("text",):` | R21 | R21 | KILLED |
| M84 | R17 R24 | `return "auto" if declared == "auto" else "text"` → `return "auto"` | R17 R24 | R24 | KILLED; predicted, stayed green: R17 |
| M85 | R25 | `return autocrlf if declared is None else declared` → `return declared` | R25 | R25 | KILLED |
| M86 | R29 | `return None if typed.stdout.strip() == b"false" else "auto"` → `return "auto"` | R29 | R29 | KILLED |
| M87 | R26 | `if call(place, "config", "--get", "core.autocrlf").return…` → `(removed)` | R17 R21 R24 R26 R29 | R17 R18 R21 R26 R27 | KILLED; predicted, stayed green: R24 R29; also red: R18 R27 |
| M88 | R27 | `return crlf > 0 and not binary and not held` → `return crlf > 0 and not binary` | R27 | R27 R30 | KILLED; also red: R30 |
| M89 | R27 | `crlf, binary = text_stats(io.BytesIO(blob.stdout))⏎ retur…` → `crlf, binary = text_stats(io.BytesIO(blob.stdout))⏎ retur…` | R27 | R27 | KILLED |
| M90 | R30 | `parts[2] in ("0", "2")` → `parts[2] in ("0",)` | R30 | R30 | KILLED |
| M91 | R26 | `crlf += chunk.count(b"\r\n") + (last == b"\r" and chunk.s…` → `crlf += chunk.count(b"\r\n")` | R26 | R26 | KILLED |
| M92 | R17 R24 | `own = attributes_of(call(place, "check-attr", "-z", "--st…` → `own = attributes_of(call(place, "check-attr", "-z", "--st…` | R17 R21 R24 R25 R29 | 9 rows | KILLED |
| M93 | R28 | `own.get(name, {})` → `{}` | R28 | R28 | KILLED |
| M94 | R26 | `printable = size - crs - lfs - controls` → `printable = size - controls` | R26 | R26 | KILLED |
| M95 | R18 | `if declared == "binary":⏎ return None` → `(removed)` | R18 | R18 R25 | KILLED; also red: R25 |
| M96 | R31 | `names = list(dict.fromkeys(name for name in (listed.stdou…` → `names = list(dict.fromkeys(name for name in listed.stdout…` | R31 | R31 | KILLED |
| M97 |  | `"diff-files", "--ignore-submodules=all", "--name-only"` → `"diff-files", "--name-only"` | — | none | SURVIVED |

## Survivors, mismatches and what changed

First round, seven survivors:
- **M07 and M68 (E1–E3, E6).** `main` and `child_env` each removed the caller's variables, so neither layer alone
  could redden a test. Now `main` holds the one allowlist and `child_env` inherits it. M07, with `main` dropping only
  `GIT_*`, kills E6 and E7. M68, with `main` keeping everything, kills E1–E3, E6 and E7.
- **M58 and M59 (K18).** `http.saveCookies=false` alone keeps git from writing a cookie file, so neither
  `cookieFile` override was tested. A second K18 test plants a file of cookies for the origin, once under each key,
  and asserts that neither cookie is sent. M58 and M59 now kill it.
- **M60 (K19).** git ignores `core.worktree` in a linked worktree's shared config. K19 now also restores in the main
  checkout, where git honours it, and M60 kills it.
- **M48 (K9).** Declared guard, kept: `GIT_TERMINAL_PROMPT=0` keeps a fetch that needs credentials from prompting on
  the Owner's terminal and waiting. No test has a terminal, so nothing can redden it. `core.askPass=` is the other
  layer: M49 is M47 run with M48 applied, and kills K9.
- **M66 (K13).** Declared guard, kept: `--attr-source` with an empty tree reads no attributes from the checkout. The
  per-driver `-c` overrides are the second layer. M54 runs with M66 applied and kills K14.

Prediction mismatches:
- **M01.** R1 was predicted red. It stayed green, because an unknown subcommand is refused before any worktree is
  located. K0, K2 and K14 were also predicted red but passed while every call was refused, since each asserted only
  that no marker appeared. Each now also asserts that its work happened: K0 and K2 that the push reached origin, K14
  that the pick stopped on the conflict. On the re-run, M01 kills all three.
- **M46.** K0 was predicted red. Its origin is a local path, and no credential is asked for over a local path. K8,
  over http, kills it.
- **M04, M18, M51, M52, M54.** More rows went red than predicted (see the table); every aimed row is red.


## Review 1 (R16–R19, K0, K13)

Review 1 F2 found that `rw-git add`, which reads no attributes, staged raw bytes where plain `git add` stores a git-lfs
pointer or converted line endings. R16–R19 were written first: R16 and R17 red on the shipped code, R18 and R19 green
there, owing kills. Review 2 rewrote that code, so its mutations are the ones below; review 1's run is
`rw-git-mutations-r1fix.md` in the unit's evidence. What still holds from it:
- **M76:** K13 was predicted red too, and stayed green: git reads `info/attributes` even under `--attr-source`, so K13's
  refusal still fires.
- K13 now expects `add` refused. K0 planted its filter attributes on `*` too, so its `add` was refused and its commit
  never ran, and M57 lost its K0 kill. K0 now plants them on `*.dat`, and M57 kills it again; M53 (a filter key) is
  K13's alone since.

## Review 2 (R17, R18, R20–R23)

Review 2 found the line-ending check wrong in two ways: a NUL exempted a file under forced `text`, and a listed folder
ended in a traceback. It also found that a link in a parent folder answered whether an outside file held a CR, and
that the deletion of a filtered file was refused. The check now follows git's `convert.c`. R20–R23 were written first
and seen red on review 1's code; R18 and R21 grew cases that were red too. Running the batch found two more gaps:
- **M78 survived.** The regular-file check sat after `os.fdopen`, which raises on a folder first. A tracked file
  replaced by a folder is listed without a slash, and `add .` ended in a traceback. R20 grew that case, seen red on
  `IsADirectoryError`. The check now runs on the descriptor before the read, and M78 kills R20.
- **M84 survived.** No row had `eol` alone. R17 grew `i.eol` under `eol=crlf`. It was green at red, since the code
  already followed git there, and M84 kills it. M84 was aimed at R18 by mistake; R17 holds the case.

Declared guards, unchanged:
- **M48 (K9)**, **M66 (K13)**: above.
- **M79:** `ls-files` runs with no attributes read. `--modified` hashes a racily clean file, and with attributes read
  that would run its clean filter; no test makes an index entry racy on purpose. The `-c` override of each configured
  filter driver (M54) is the other layer.

`O_NONBLOCK` on the file open (M74) is now killed by R11. M82 (an unopenable file refused) reddens R19 and R20 as well
as R22 and R23: a dangling link and a folder entry hit the same `except`. Review 3 reassigned these ids.

## Review 3 (R24–R31)

Review 3 found:
- `eol` with no `text` read as auto. git's `convert_attrs` makes it a forced text.
- rw-git's own `add` still applies `core.autocrlf` and `info/attributes`. A `-text` file was converted where plain git
  keeps it.

The check now works out git's line-ending action twice with one function:
- once from every attribute, for plain git;
- once from what `check-attr` reads under rw-git's empty attribute source, for rw-git's own `add`.

Both fall back to `core.autocrlf`, and it refuses only where the two would store different bytes. It also models
`convert_is_binary` (the control-byte ratio, a final `\x1a`) and `has_crlf_in_index` (stage 0, or else ours).

Every expected value in R24–R31 was checked against plain git before the test was written
(`evidence/probe-convert.py`, `evidence/probe-stat.py`):
- R24, R25 a.bin, R26 a/b/f/h.bin, R27, R28 and R31 were red on the code they were written against.
- R25 c.ctl, R26 e/g.txt, R29 and R30 were green there, and each is killed: M80, M81, M86, M90, M91, M94.

A differential run (`evidence/fuzz-add.py`, 20,400 cases) compares rw-git's `add` with plain `git add`. The cases
cross 17 attribute sets, 4 `info/attributes`, 5 `core.autocrlf` values, 4 index copies and 15 contents, three of
them across the 1 MiB read. It found 405 divergences at review 2's code. After the first fix it still found 35,
every one an unchanged tracked file whose stat had changed:
- plain git hashes such a file again, with its attributes;
- rw-git's `ls-files --modified`, which reads none, skipped it.

R31 was written red, and the check now also weighs what `diff-files` lists, which hashes nothing. The last run found
no divergence and no over-refusal: 1,656 refusals, each a case where the two would store different bytes.

Prediction mismatches:
- **M84:** R17 was predicted red. Its `i.eol` holds a plain text CRLF, which auto converts too.
- **M87:** R24 and R29 were predicted red. R24 stays refused because a forced `text` still differs from auto on a
  binary file. R29 sets `core.autocrlf`. R18 and R27 went red as well.
- **M66 (K13)** is no longer a declared guard. Without the empty attribute source, rw-git's own side reads the
  checkout's attributes, and nine rows go red.

Declared guards:
- **M48 (K9)**: above.
- **M79**: above.
- **M97:** `diff-files --ignore-submodules=all`. Without it, a submodule's dirtiness is checked by running git inside
  it, as the Owner. No test holds a submodule, and the leaf `**/.git` deny keeps a session from making one.

No test was deleted. Accepted untested: none.

## Review 4 (R31–R37): line endings under `core.safecrlf`, racily clean entries, boolean spellings, string values

Every expected value in R32–R37 was checked against plain `git add` before the test was written. R32, R34, R36 and
R37 were red on the code they were written against; R33 and R35 were green there and owe their kills below. One
compiling mutation per row, applied once, run against `AttributeTests`:

| # | Row | Mutation | Predicted | Observed | Verdict |
|---|---|---|---|---|---|
| A01 | R32 | the `core.safecrlf=true` round trip in `add_stores` skipped | R32 | R32 | KILLED |
| A02 | R32 | the checkout half of that round trip skipped | R32 | R32 | KILLED |
| A03 | R32 R35 | a config value read as spelled, not through `--type=bool` | R32 R35 | R32 R35 | KILLED |
| A04 | R35 | every boolean read as false (review 3's survivor) | R32 R35 | R32 R33 R34 R35 | KILLED |
| A05 | R35 | `core.autocrlf=true` mapped to binary | R35 | R32 R33 R34 R35 | KILLED |
| A06 | R33 | an unset `core.safecrlf` read as `true` | R33 | R25 R28 R33 R36 | KILLED |
| A07 | R33 | `warn` matched in lower case only | R33 | R33 | KILLED |
| A08 | R34 | racy when the mtime is later than the index's, not no earlier | R34 | R34 | KILLED |
| A09 | R34 | racily clean entries not weighed | R34 | R34 | KILLED |
| A10 | R36 | the string `text=set` read as the state `text` | R36 | R36 | KILLED |
| A11 | R37 | a converting attribute valued `unset` passed | R37 | R37 | KILLED |
| A12 | R31 | what `diff-files` lists not weighed | R31 | R31 | KILLED |

A12 first survived: once racily clean entries were weighed, R31's touched `a.txt` was caught by that check too. R31's
Given now moves `a.txt`'s mtime further into the past, so its stat changed but it is not racily clean, and A12 kills
it. A04, A05 and A06 redden more rows than predicted: autocrlf and safecrlf feed every row that sets them.

## U48 part B (U1–U17, G1–G4, R8)

Every row but U3, U4, U7, U9, U10 and U15 was red on `b0d73ba` (part A's tip): 22 failures and 4 errors over the 22
tests. Those six were green there, since nothing outside `repos` was served at all, and owe their kills below. One
compiling mutation per row, applied once, run against `UnmanagedTests`, `GrantsReaderTests` and `RefusalTests`
(driver: the project's `prs/<unit>/evidence/rw-git-mutations-B.py`):

| # | Row | Mutation | Predicted | Observed | Verdict |
|---|---|---|---|---|---|
| B01 | U1 U2 | an unmanaged commit checks `own_head` | U1 U2 U8 U12 U14 U16 U17 | R8 U1 U2 U8 U14 U16 U17 | KILLED |
| B02 | U2 | a granted repository not added to the listing | U2 U8 U12–U14 U16 U17 | U2 U8 U12–U14 U16 U17 | KILLED |
| B03 | U3 | no grant needed | U3 U9 U10 | U3 U7 U8 U9 | KILLED |
| B04 | U4 | denies not applied | U4 | U4 | KILLED |
| B05 | U4 | a granted folder's own settings not read | U4 | G3 U4 U14 | KILLED |
| B06 | U4 | a deny not widened at its glob | U4 | G2 U4 | KILLED |
| B07 | U5 | a `desktop_roots` entry's shape not checked | U5 | U5 | KILLED |
| B08 | U5 | a string `desktop_roots` taken | U5 | U5 | KILLED |
| B09 | U6 | a `desktop_roots` entry not checked for links | U6 | U6 | KILLED |
| B10 | U8 | a glob grant taken with its `*` removed | U8 | G1 | KILLED |
| B11 | U8 | a settings grant through a link kept | U8 | none | EQUIVALENT |
| B12 | U8 | `additionalDirectories` not read | U8 | G1 U8 | KILLED |
| B13 | U11 | settings under a granted folder taken | U11 | U11 | KILLED |
| B14 | U12 | a stopped operation not looked for | U12 | U12 | KILLED |
| B15 | U12 | a detached HEAD taken | U12 | U12 | KILLED |
| B16 | U14 R8 | an unmanaged message anywhere outside the repository | U14 R8 | R8 U14 | KILLED |
| B17 | U14 | a message inside the repository taken | U14 | U14 | KILLED |
| B18 | U14 | a deny over a message folder not applied | U14 | U14 | KILLED |
| B19 | U17 | the temp folders not counted | U17 | U17 | KILLED |
| B20 | U15 | a managed worktree held to the unmanaged rule | U15 | R10 R15 U15 | KILLED |
| B21 | G1 | `//b` kept as spelled by `normpath` | G1 U8 | none | EQUIVALENT |
| B22 | G2 | a bare `Edit` deny ignored | G2 | G2 | KILLED |
| B23 | G3 | an unreadable root settings file read as `{}` | G3 | G3 | KILLED |
| B24 | G4 | the temp folder's owner not checked | G4 | none | DECLARED GUARD |
| B25 | U16 | `core.fsmonitor=false` dropped | U16 | U16 | KILLED |

- B11 is equivalent: repositories and paths are compared by canonical path, so a grant spelled through a link never
  holds one, and a message path through it fails `open_unlinked`. The `unlinked` call on settings grants stays as the
  shape check B2 names.
- B21 is equivalent: `normpath` keeps a leading `//`, and `unlinked` then drops the empty part.
- B24: no test on one account can plant a temp folder another account owns. G4's doc comment names it as a declared
  guard.

## Review 1 of U48 (fixes on top of `b6f9e22`)

U11 (changed), U12's `sequencer` case, U18 and U19 were red on `b6f9e22`: 4 failures and 1 error (U19's FIFO hung
until the test's timeout). The reviewer's own reproductions (`t7`, `t11`, `t12`) were rerun against the fix: the
recommended setup and the settings link under the root now exit 0, the FIFO and the broken user settings are refused
promptly.

| # | Row | Mutation | Predicted | Observed | Verdict |
|---|---|---|---|---|---|
| F01 | U11 | grants taken from a settings file under a granted folder | U11 | U11 | KILLED |
| F02 | U18 | a named deny widened like any other | U18 | U18 | KILLED |
| F03 | U18 | a named deny covering its whole folder | U18 | U18 | KILLED |
| F04 | U19 | the regular-file check dropped | U19 | none | EQUIVALENT |
| F05 | U19 | a settings file that is not JSON read as `{}` | U19 | G3 U19 | KILLED |
| F06 | U12 | `sequencer` not looked for | U12 | U12 | KILLED |

F04 is equivalent: opened `O_NONBLOCK` with no writer, a FIFO reads empty and the JSON parse refuses it, and the size
cap refuses a link to `/dev/zero`. The check stays as the shape `settings_of` documents.

## Decided (Lead): denies matched as globs (U47 review 1 F2)

G2 (changed: denies are kept as written, not widened), U20, U21 and U22 were red on `b6f9e22`: 7 failures over the 4
tests. U18 and U4 still hold under the new matching.

| # | Row | Mutation | Predicted | Observed | Verdict |
|---|---|---|---|---|---|
| L01 | G2 | `**` matches one or more segments, not none | G2 | G2 U4 | KILLED |
| L02 | U21 | `*` crosses segments | U21 | U21 | KILLED |
| L03 | U21 | only the path itself matched, no folder above it | U21 | G2 U18 U21 | KILLED |
| L04 | U22 | a glob shape it cannot match taken | U22 | U22 | KILLED |
| L05 | U20 | a glob deny widened to its literal folder, as before | U20 U18 | G2 U18 U20 U21 U22 | KILLED |
| L06 | U21 | a folder above the path not matched | U21 | G2 U18 U21 | KILLED |

L05 first ran as a malformed mutant that widened only the last spelling of each deny and survived; rewritten per
spelling, it kills U20.

## U49 part A: own and protected branches, amend, reset, rebase --onto

D1–D16 and S15's new words were red on `8349f22` (`evidence/red-A.log`: 18 tests, 75 failing subtests, no error).
Four subtests were added after the first green run, each to give a mutant below something to kill: D1's
`stash pop` and `push notes` (A23, A24), D4's `switch -c @{-1}` and `MERGE_HEAD` cases (A27, A28), D6's
`cherry-pick --abort` (A26). U2 changed (its second branch was `release/1.0`, now protected by default) and U13 is
retired (D2 allows what it refused). Run with `mutate.py`, each mutant in its own copy, over DailyTests,
UnmanagedTests and S15.

| # | Mutation | Predicted | Observed | Verdict |
|---|---|---|---|---|
| A01 | default list drops develop | D1 D4 | D6 D1 D4 | KILLED |
| A02 | protected names match case-sensitively | D4 | D4 | KILLED |
| A03 | a listed entry is ignored | D2 D2~ | D2 D2~ | KILLED |
| A04 | a ~/ key is not expanded | D2~ | D2~ | KILLED |
| A05 | a control byte in an entry passes | D16 | D16 | KILLED |
| A06 | an entry of 256 bytes passes | D16 | D16 | KILLED |
| A07 | an empty entry passes | D16 | D16 | KILLED |
| A08 | unmanaged own_head skips the protected check | D2 D1 | D2 D2~ D1 | KILLED |
| A09 | unmanaged switch -c makes a protected branch | D4 | D4 | KILLED |
| A10 | unmanaged switch goes only to unprotected branches | D4 | D4 | KILLED |
| A11 | a merge is amended | D9 | D9 | KILLED |
| A12 | no remote-tracking check | D8 | D8 | KILLED |
| A13 | only origin's refs count | D8 | D8 | KILLED |
| A14 | amend makes a new commit | D7 D3 | D7 D3 | KILLED |
| A15 | reset skips own_head | D15 D1 | D15 D11 D10 D1 | KILLED |
| A16 | reset skips known_commit | D12 | D12 | KILLED |
| A17 | reset prints no old tip | D11 D10 | D11 D10 | KILLED |
| A18 | reset takes --mixed | D12 | D12 | KILLED |
| A19 | rebase --onto drops <upstream> | D13 | D13 | KILLED |
| A20 | rebase --onto skips the upstream check | D14 | D14 | KILLED |
| A21 | a stopped protected rebase is head-not-own | D6 | D6 | KILLED |
| A22 | unmanaged stash entries share one tag | D5 | D5 | KILLED |
| A23 | push skips the HEAD check | D1 | D1 | KILLED |
| A24 | stash pop skips the HEAD check | D1 | D1 | KILLED |
| A25 | help omits branch-protected | S15 | S15 | KILLED |
| A26 | cherry-pick steps need a settled checkout | D6 | D6 | KILLED |
| A27 | switch ignores a stopped operation | D4 | D4 | KILLED |
| A28 | a name holding @{ is writable | D4 | D4 | KILLED |
| A29 | main protected by default | D16 D13 D10 D6 D5 D3 D4 | U48 rows on `main` D3 | KILLED |
| A30 | a protected_branches list is not checked | D16 | D16 | KILLED |

Prediction misses, each a reading error and not a gap: A01 also reddens D6 (its stopped rebase is on `develop`); A08
also D2~; A15 also D10 and D11 (their old-tip line names the branch own_head returns); A29 reddens the U48 rows
that commit on `main` and D3, not the rows on `feature` the prediction listed.

## U49 part B: scope file, gitlinks, named remotes

D20–D30 and S15's new words were red on `215eee0` (`evidence/red-B.log`: 12 tests, 28 failing subtests, no error).
D28's expected ref order was a test bug (`for-each-ref` sorts by name) and was corrected before the first green run.
B02, B06, B10 and B15 survived the first run, each because its row could not tell the cases apart. The rows were
tightened, the code unchanged: D20 stages a file named like its comment line, D23's bad line is a NUL, D25 commits a
`.gitmodules` giving the paths `ignore = all`, and D29 configures the out-of-shape names it passes. Then all four
were killed.

| # | Mutation | Predicted | Observed | Verdict |
|---|---|---|---|---|
| B01 | scope check skipped | D20 D24 D22 | D20 D24 D22 | KILLED |
| B02 | comment lines kept as pathspecs | D20 | D20 | KILLED (survived the first run; the row was tightened) |
| B03 | renames not detected | D21 | D21 | KILLED |
| B04 | outside names printed as git gave them | D22 | D22 | KILLED |
| B05 | scope file not read through the message rules | D23 | D23 | KILLED |
| B06 | a control byte in a scope line passes | D23 | D23 | KILLED (survived the first run; the row was tightened) |
| B07 | an amend diffed against HEAD | D26 D24 | D26 D24 | KILLED |
| B08 | gitlink check skipped | D25 D26 | D25 D26 | KILLED |
| B09 | only the new mode is weighed | D25 | D25 | KILLED |
| B10 | configuration may hide a gitlink | D25 | D25 | KILLED (survived the first run; the row was tightened) |
| B11 | the scope file's message-file code | D23 | D23 | KILLED |
| B12 | a named remote fetched into origin's refs | D27 | D27 | KILLED |
| B13 | push ignores --remote | D28 | D28 | KILLED |
| B14 | named remote's mirror kept | D28 | D28 | KILLED |
| B15 | any configured name, no shape check | D29 | D29 | KILLED (survived the first run; the row was tightened) |
| B16 | no membership check | D29 | D29 | KILLED |
| B17 | help omits remote-unknown | S15 | S15 | KILLED |
| B18 | push's named remote skips the shape check | D29 | D29 | KILLED |

## U49 review 1 fixes (D31–D33)

Rows D31–D33 were written from the review's findings and seen red on their assertions before the fix: `push 'd*'`
exit 0, `switch -c café` exit 0, and `reset --soft` finished while the lock was held. Each mutation ran in its own
copy against `DailyTests`. D33 holds a shared lock, so an exclusive lock is the only one that waits for it, and it
runs a second call from a linked worktree, so a lock in the worktree's own git directory does not wait.

| # | Mutation | Predicted | Observed | Verdict |
|---|---|---|---|---|
| C01 | no non-ASCII class in UNWRITABLE | D32 | D32 | KILLED |
| C02 | no `*` in UNWRITABLE | D31 | D31 | KILLED |
| C03 | no `:` | D31 | D31 | KILLED |
| C04 | no `~` | D31 | D31 | KILLED |
| C05 | no `^` | D31 | D31 | KILLED |
| C06 | no `?` | D31 | D31 | KILLED |
| C07 | no `[` | D31 | D31 | KILLED |
| C08 | no `\` | D31 | D31 | KILLED |
| C09 | no `..` | D31 | D31 | KILLED |
| C10 | no `@{` | D4 | D4 | KILLED |
| C11 | no flock | D33 | D33 | KILLED |
| C12 | a shared lock | D33 | D33 | KILLED |
| C13 | the lock in the worktree's own git directory | D33 | D33 | KILLED |
| C14 | the handler runs before the lock is taken | D33 | D33 | KILLED |

Accepted untested: `O_NOFOLLOW` on the lock file. It guards against a link at `<git dir>/rw-git.lock` leading the
Owner's `O_CREAT` to a file elsewhere. A session cannot plant that link, because its sandbox denies the git
directory, so no row can reach it.

## U49 review 2 fix (D34, D35)

The Lead's review 2, N1. Both rows were red on `3ec579b`: the sibling worktree's `rw-git add` was still waiting when
the test's 15 s and 20 s timeouts ran out (`TimeoutExpired`). Each mutation ran in its own copy against D33–D35. D33
stayed green under every one.

| # | Mutation | Predicted | Observed | Verdict |
|---|---|---|---|---|
| E01 | a blocking `LOCK_EX` again | D34 | D34 | KILLED |
| E02 | git's output written under the lock | D35 | D35 | KILLED |
| E03 | no deadline | D34 | D34 | KILLED |

## U52a · what rw-git serves (W7.1–W7.4); a deny in any spelling (U23–U26)

Each mutation applied in the build's worktree, `WhereItRunsTests` or `UnmanagedTests` run, then restored (`git
status` clean after each batch); predictions written before the run. W7.1, W7.2 and U23–U26 were red before the
code; W7.3 and W7.4 are pass-throughs, green at red.

| # | Mutation | Predicted | Observed | Verdict |
|---|---|---|---|---|
| M13 | `locate` no longer catches `UnlistedDirectory` | W7.1 W7.2 | W7.1 W7.2 | KILLED |
| M14 | `check` raises its untrusted-hint refusal as `UnlistedDirectory` | W7.3 | W7.3 | KILLED |
| M15 | `check` raises `worktree-foreign-gitdir` as `UnlistedDirectory` | W7 W7.4 | W7 W7.4 | KILLED |
| MC1 | `is_denied` compares without folding case and form | U23 | U23 | KILLED |
| MC2 | a relative `Edit(…)` rule is read only where it is anchored | U24 | U24 | KILLED |
| MC3 | a linked user settings file's denies are read from the link's folder only | U25 | U25 | KILLED |
| MC4 | `is_denied` drops the comparison as written, keeping only the folded one | U26 | U26 | KILLED |
| MC1b | `is_denied` drops the folded comparison, keeping only the one as written (MC1 on the S1 shape) | U23 | U23 | KILLED |

## U52b · config hooks and `=` names (K24, K25); protected branches (D2, D3, D36, D37, R38)

Each mutation applied in the build's worktree, the new tests run, then restored from a copy (`git status` showed only
the change's files after each); predictions written before the run. Every test here was red before the code.

| # | Mutation | Predicted | Observed | Verdict |
|---|---|---|---|---|
| C1 | `extra_options` emits no `hook.<name>.enabled` line | K24 | K24 | KILLED |
| C2 | a `NAMED` override back to `-c name=value` | K25 | K25 | KILLED |
| DM1 | `DEFAULT_PROTECTED` without `main` | D3 | D3 | KILLED |
| DM2 | a `protected_branches` list replaces the default | D2 D37 | D2 D37 | KILLED |
| DM3 | `locate` drops `origin_head` | D36 | D36 | KILLED |
| DM4 | `reset` skips `untracked` | R38 | R38 | KILLED |
| DM5 | `push --force-with-lease` skips `untracked` | R38 | R38 | KILLED |
| DM6 | `untracked` ignores the upstream | R38 | R38 | KILLED |

## U52b · push goes to origin or a `push_remotes` remote (D38, D39)

Both red before the code (the push exited 0). D28's Given gains `push_remotes` listing `fork`; its Then is unchanged.

| # | Mutation | Predicted | Observed | Verdict |
|---|---|---|---|---|
| EM5 | `known_remote` skips the `push_remotes` check | D38 | D38, D39 | KILLED |
| EM6 | `fetch` held to `push_remotes` too | D38 | D38 | KILLED |
| EM7 | a `push_remotes` list's entries unchecked | D39 | D39 | KILLED |
| EM8 | any key's list applies to every repository | D38 | D38 | KILLED |

## U52b · gate fix round (K24 empty name, K25.1, S16.1)

| # | Mutation | Predicted | Observed | Verdict |
|---|---|---|---|---|
| G1r | `HOOK_KEY` back to `(.+)` | K24 | K24 | KILLED |
| G1n | the driver pattern back to `.+` | K25.1 | K25.1 | KILLED |
| G4 | the Owner's helpers back to `-c <key>=<value>` | S16.1 | S16.1 | KILLED |

## U58 · E1 (D40)

D40 went red before the code on the call's own refusal (`gitlink: git could not list the staged paths: ambiguous
argument`), so the unfixed line is its mutation.

| # | Mutation | Predicted | Observed | Verdict |
|---|---|---|---|---|
| U58-E1 | `staged` passes `--` only when there are pathspecs | D40 | D40 | KILLED |

## U63 · an explicit worktree: `--dir`, `where`, `switch --detach` (X1–X21)

Each mutation applied to `rw_git.py` alone, `ExplicitWorktreeTests` run, then the file restored from a copy and
compared; the red set predicted in writing before each run. Red before the code: X1, X2, X14, X16, X18 and X20 on their
Then; X3 and X19 in their Given (`where` and the detach were not forms yet). Green when written, so each owed its kill
first: X4–X13, since the peel that came with X1 serves every form and holds the shape; X15 and X17, which the existing
`switch` and `parse` already met; X21, written after the docstring it reads.

| # | Mutation | Predicted | Observed | Verdict |
|---|---|---|---|---|
| U63-1 | the peel drops `--dir`'s path, so the working directory decides | X1 X3 X4 X5 X6 X7 X10 X11 X12 X13 | the same | KILLED |
| U63-2 | the peel's shape check dropped | X8 | X8 | KILLED |
| U63-3 | `--dir` mapped to the main checkout above it | X9 | X9 X1 X3 X4 X5 X6 X7 X12 X13 | KILLED; mispredicted: a linked worktree maps to its main checkout too |
| U63-4 | `--dir` walked up to the nearest folder holding a `.git`, as `git -C` discovers | X9 | X9 | KILLED |
| U63-5 | without `--dir`, `locate` starts from the first `repos` entry | X2 | X2 | KILLED |
| U63-6 | `known_commit` dropped from the detach | X16 | X16 | KILLED |
| U63-7 | `--discard-changes` added to the detach | X18 | X18 | KILLED |
| U63-8 | `unstopped` dropped from the detach | X20 | X20 | KILLED |
| U63-9 | managed `switch` calls `own_head` first | X15 | X15 | KILLED |
| U63-10 | `switch --detach` takes its last word whatever precedes it | X17 | X17 | KILLED |
| U63-11 | managed `own_head` takes a detached HEAD | X19 (managed) | X19 (managed) | KILLED |
| U63-12 | unmanaged `own_head` takes a detached HEAD | X19 (unmanaged) | X19 (unmanaged) | KILLED |
| U63-13 | `where` prints `detached` without the id | X14 | X14 | KILLED |
| U63-14 | `where` rewrites HEAD to the branch it names | X3 | X3 | KILLED |
| U63-15 | the `switch --detach` line dropped from `--help` | X21 | X21 | KILLED |

## U63 · review fix round (X22–X24)

X22 and X23 were red before the fix, so the unfixed line is each one's mutation.

| # | Mutation | Predicted | Observed | Verdict |
|---|---|---|---|---|
| U63-16 | the detach without `--no-overwrite-ignore` | X22 | X22 | KILLED |
| U63-17 | the `worktree-unlisted` refusal prints the resolved path, not `--dir` as spelled | X23 | X23 | KILLED |
| U63-18 | `--dir` resolved to the disk's letter case (`F_GETPATH`) | X24 | X24 X23 | KILLED; also red: X23, since `F_GETPATH` resolves the link too. X24 was green when written: it pins the refusal both reviews accepted |

## U65 · every switch form keeps an ignored file (X25, X26)

X25 was red before the code, so the unfixed line is its mutation. X26 is a declared guard: `--create` starts from
HEAD, so no file changes and no compiling edit reddens it, the flag's removal included (U65-2). It guards against a
git that refuses the flag beside `--create`, which would fail every `switch -c`.

| # | Mutation | Predicted | Observed | Verdict |
|---|---|---|---|---|
| U65-1 | plain `switch <branch>` without `--no-overwrite-ignore` | X25 | X25 | KILLED; X26 and X22 green, as predicted |
| U65-2 | `switch -c` without `--no-overwrite-ignore` | none | none | GUARD (X26): no compiling edit reddens it |
