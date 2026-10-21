# Scrub gate — behaviors

Commit ids in this record refer to the project's history before it was published; they are not in this repository.

The rules for `tools/scrub-gate.sh` and `tools/hooks/{pre-commit,pre-push}`, written before the
gate existed; rules 7–9, and every hit line rewritten to name the denylist line instead of the pattern,
were written under U2 before the gate changed; rules 10–13 were written under U5 before the gate changed. Suite: `tests/scrub-gate/test_scrub_gate.py`; each test's docstring starts with its
row id. Every fixture is synthetic: invented patterns (`forbidden-token`, `example-secret-[0-9]+`),
a scratch repository, a scratch `HOME`, a scratch denylist. The suite never opens a real denylist.

## Rules

R1 — A commit whose **added** lines match a denylist pattern is refused, naming file, line and the denylist line; a removed line matching is not a hit.
R2 — A pattern is a POSIX ERE matched case-insensitively; a `#` line and a blank line in the denylist are not patterns.
R3 — `ROBOWRIGHT_DENYLIST` names the denylist; unset, it is `$HOME/.config/robowright/denylist`; a missing file refuses with exit 2 naming the path it looked for.
R4 — `--cached` reads the index (pre-commit); `--range <old> <new>` reads every commit in the range, and an all-zeros `<old>` means every commit not on any remote (pre-push, new branch); `--tree` reads every tracked file.
R5 — *(superseded by R7 under U2; rows R5.1 and R5.2 keep their ids and cite R7.)*
R6 — `pre-push` reads its stdin lines as git documents them (`<local-ref> <local-oid> <remote-ref> <remote-oid>`) and runs the range check per line; any hit aborts the push.
R7 — A clean run prints `scrub: clean` and exits 0; a hit prints one `scrub: <file>:<line>: denylist:<n>` per hit and exits 1, `<n>` the matching pattern's 1-based line number in the denylist file, comment and blank lines counted. No output of the gate — a hit line, an error line, a diagnostic — contains any part of a pattern's text; an unusable pattern is reported as `denylist:<n>`.
R8 — A tracked file name is printed exactly as `git ls-files` lists it unless rule 10 withholds it: a backslash in a name is a backslash in the output, and a hit after such a name still names its own file and line (the record alignment does not depend on the name's characters).
R9 — A tracked file name containing a newline cannot be reported on one line: the gate refuses with exit 2 naming the count of such names, and prints no hit line (fail closed, as a missing denylist does).
R10 — A file name is content. Before any hit line prints, every path in the run's scope is matched, whole and as `git ls-files` lists it, against every pattern under R2. The scope: `--cached`, every path staged as added, modified, renamed-to or copied-to (a staged deletion is not in scope); `--range`, for each commit, every path that commit adds or changes (not deletes); `--tree`, every tracked path. A matching path is a hit in its own right: one line `scrub: (name withheld):0: denylist:<n>` per matching pattern, exit 1. That path is printed as `(name withheld)` everywhere it would otherwise appear, so a content hit inside it is `scrub: (name withheld):<line>: denylist:<n>`. A path under a directory whose name matches is a matching path. No output — stdout, stderr — contains any part of a withheld name. A run whose only hits are names still prints no `scrub: clean`.
R11 — The denylist path (`ROBOWRIGHT_DENYLIST`, else the default) is resolved against the caller's working directory once, before the mode runs, and read from that resolution in every mode: a relative path from a subdirectory reads the same file `--cached` would. A path that is missing, unreadable or a directory refuses with exit 2 naming the path as given, prints no hit line and no `scrub: clean`, in every mode.
R12 — `--tree` reads a tracked symlink's link text, never its target: a dangling link whose text matches is a hit at line 1; a link to a matching file outside the repository is clean when its text is. A regular file is still read from the working copy (R4.10); a tracked path absent from disk is still skipped.
R13 — R1–R9 are unchanged: a removed line, a deleted path and a commit message are not matched; `denylist:<n>` still counts the denylist's lines from 1.

## Questions

Q1 — Is `<file>` the path relative to the repository root, or absolute? → Assumed: repo-relative, as git names it (`docs/guide.md`), because that is how git reports paths and an absolute path would print a machine path the scrub exists to keep out.
Q2 — For a renamed file, does it fail, and which name is `<file>`? → Settled that it fails: "a renamed file with a hit must fail". Assumed: `<file>` is the new path, because "`<line>` is the line number in the new version of the file" — the new version has the new name.
Q3 — A line matching two patterns: one hit or two? → Assumed: one output line per matching pattern, because R7 prints one line "per hit" and each line names the matching pattern's denylist line — two patterns are two lines to name.
Q4 — In what order are hit lines printed, and may other lines appear? → Not pinned: tests compare the set of `scrub: <file>:<line>: denylist:<n>` lines, sorted. Settled by: "The gate's output format beyond `scrub: <file>:<line>: denylist:<n>` (a summary line, colors) — the Session's call, logged. Printing any part of a pattern's text is not: D8 is settled."
Q5 — Is a whitespace-only denylist line blank? → Assumed: yes, because as a pattern it would refuse every line containing a space, which no one writes a denylist to do.
Q6 — A denylist file that exists but holds only comments and blank lines: pass or refuse? → Assumed: pass (`scrub: clean`, exit 0), because R2 leaves no patterns and R7 (was R5) calls a run with no hit clean; the refusal is named only for an **absent** denylist ("an absent denylist is a refusal (exit 2), not a pass").
Q7 — Does `--tree` read a tracked file's working-tree content or its committed content? → Assumed: working-tree content, because the acceptance check runs "`tools/scrub-gate.sh --tree` on the worktree" and the release check must see the files it ships.
Q8 — Does a rename inside a pushed commit (`--range`) fail the way a staged rename does? → Assumed: yes, with the new path, because a rename that leaks through push but not commit would make the push gate weaker than the commit gate on the same content.
Q9 — A `(delete)` stdin line (local oid all zeros) on pre-push? → Assumed: not a hit, because it adds nothing (brief: "default it (Assumed) as not a hit (nothing added)").
Q10 — Where does the exit-2 message go, and is `$HOME` expanded in it? → Assumed: stdout or stderr (tests read both), with the path expanded as looked up, because "naming the path it looked for" names a path, not a template.
Q11 — What exit code does a hook return on refusal? → Not pinned: tests assert non-zero plus the commit or ref not landing, because the rules say "refused" and "aborts", not a code.

Questions raised under U2 (rules 7–9):

Q12 — "Printed exactly as `git ls-files` lists it": git's default listing C-quotes a name holding a backslash, a tab or a non-ASCII byte (`"a\\nb"`, `"a\tb.txt"`, `"\303\251t\303\251.md"`). Is that the printed form, or the name's bytes unchanged? → Assumed: the bytes unchanged, as `git ls-files -z` gives them, because the rule's own gloss "a backslash in a name is a backslash in the output" rules out the quoted form, which doubles it, and the U2 acceptance row asks that "the hit line carries that name unchanged".
Q13 — What exit code does an unusable pattern give? Rule 7 says only "reported as `denylist:<n>`". → Assumed: exit 2, because exit 1 means a hit and there is none, exit 0 would pass a run that applied only part of the denylist, and exit 2 is the brief's fail-closed refusal (D2; rule 9 "fail closed, as a missing denylist does"). The line starts `scrub: ` and is read from stdout or stderr (Q10). Whether a hit on another, usable pattern is also reported is not pinned: R7.4 stages only a clean line.
Q14 — Where does the rule 9 refusal go, and what counts as "naming the count"? → Assumed: a stderr line starting `scrub: ` that holds the count as a standalone number, because the U2 spec request reads "the stderr names the count of such names" and every gate line the rules spell starts `scrub: `. The Givens plant three such names, so the count (3) differs from the exit code (2) and from a lone flag (1).
Q15 — In `--cached` and `--range`, does rule 9 count every tracked name holding a newline, or only the names the change adds? → Not pinned: in R9.2 and R9.3 every such name is added by the change under test and the base has none, so both readings give 3. A change that leaves an already-tracked newline name alone is untested.
Q16 — "Any part of a pattern's text" cannot be checked substring by substring; which parts do the tests look for? → Assumed: each literal run of three or more characters, case-insensitively (`quokka`, `zebra`, `[0-9]` in R7.1; `zqx`, `wvu` in R7.4 and R7.5), because a one- or two-character fragment cannot be told from ordinary output, and the invented patterns hold runs no other text in the run contains.
Q17 — The hotspot lists a non-UTF-8 byte in a file name; is it covered? → Not tested: APFS, where the suite runs, is expected to refuse a file name that is not valid UTF-8, so the scratch repository cannot hold one (not verified when this row was written). R8.6 uses a non-ASCII UTF-8 name instead.

Questions raised under U5 (rules 10–13):

Q18 — What line number does a name hit print? → Settled by: "a name hit itself prints line `0` (a name is not a line)" (brief, Rebrief 2).
Q19 — Are two withheld names told apart? → Settled by: "every withheld name prints the same `(name withheld)`" (brief, Rebrief 2); an ordinal is out of scope.
Q20 — A name that holds a newline and matches a pattern: R9 (exit 2, the count, no hit line) or R10 (exit 1, a `:0:` line)? → Assumed: R9 wins, and no part of the name reaches either stream, because R13 keeps R1–R9 unchanged, R9 "prints no hit line (fail closed …)", and R10's no-leak sentence holds under either reading. (H15)
Q21 — Which parts of a withheld name do the no-leak checks look for? → Assumed: every word of three or more letters in the name and in the pattern it holds (`wombat`, `forbidden`, `token`, `kestrel`, `example`, `secret`, `ibis`), in any case, because Q16 set that reading for patterns and nothing else in a run prints those words.
Q22 — "Naming the path as given" for a relative `ROBOWRIGHT_DENYLIST`: the relative text or its resolution? → Settled by: R11 "naming the path as given": the relative text exactly as set. Stream not pinned, as Q10.
Q23 — `--tree` run from a subdirectory: are hit names repository-relative? → Assumed: yes, as Q1 and G13, because a caller-relative name would differ between two runs on the same tree.
Q24 — One matching path added by one commit of a range and changed by the next: one `:0:` line per commit, or one per run? → Not pinned: no row puts a matching path in two commits of one range.
Q25 — Two different matching paths on one pattern: two identical `:0:` lines, or one? → Not pinned: no row has two matching paths on one pattern.
Q26 — `--tree`, a tracked matching name absent from disk: a name hit (R10 "every tracked path") or skipped (R12 "a tracked path absent from disk is still skipped")? → Not pinned: no row has it. Neither reading prints the name.
Q27 — A rename from a matching name to a clean one, `--cached`: is the old name in scope? → Settled by: R10 "renamed-to or copied-to (a staged deletion is not in scope)". (H13)
Q28 — Is a name matched per path component or as the whole path? → Settled by: R10 "matched, whole"; brief, Decision authority "the Owner scoped D10 to whole paths". (R10.13)
Q29 — On which stream do a hook's lines reach the caller, and with what exit? → Not pinned, as Q11: tests read both streams and assert non-zero plus HEAD or the remote ref not moving.
Q30 — `--tree`, a matching name whose file cannot be read: a name hit (exit 1) or the gate's "could not read" refusal (exit 2)? → Assumed: exit 2, because a file the gate cannot read has not been checked (fail closed, as rule 9 and rule 11), and the exit code carries no part of the name either way. (H18)

## Behavior table

Mode rows call `tools/scrub-gate.sh` directly from the scratch repository root; wiring rows (R1.5, R1.6, R3.6, R3.7, R6.x) go through real `git commit` / `git push` to a bare scratch `origin` with `core.hooksPath=tools/hooks`. Givens that need a hit already in history or on the remote are made with `--no-verify`. Default denylist for every row unless the Given says otherwise, line by line: a `#` comment (1), `forbidden-token` (2), `example-secret-[0-9]+` (3). Every `denylist:<n>` in a Then is sourced to D8 as well as to the row's own column: "`<n>` the pattern's 1-based line number in the denylist file (comments and blank lines count)" — so a hit on the default denylist reads `denylist:2` or `denylist:3`.

| # | Rule | Given | When | Then | Expected value from |
|---|---|---|---|---|---|
| R1.1 | added line hits | base commit; staged new `notes.txt` = `alpha` / `forbidden-token here` / `charlie` | `--cached` | exit 1; hits = `scrub: notes.txt:2: denylist:2` | R1 "refused, naming file, line and the denylist line"; R7 "exits 1" |
| R1.2 | removed line is not a hit | committed `notes.txt` with `forbidden-token here` at line 2; staged removal of that line | `--cached` | exit 0; `scrub: clean` | R1 "a removed line matching is not a hit"; R5 |
| R1.3 | line is new-version | committed `alpha…echo` (5 lines); staged `bravo` / `charlie` / `forbidden-token here` / `delta` / `echo` | `--cached` | exit 1; hits = `scrub: notes.txt:3: denylist:2` (new line 3; old-side position would be 4) | hotspot "`<line>` is the line number in the new version of the file" |
| R1.4 | first commit is gated | empty repository (no HEAD); staged `notes.txt` = `forbidden-token first` | `--cached` | exit 1; hits = `scrub: notes.txt:1: denylist:2` | R1 "A commit whose added lines match" — any commit, the first included |
| R1.5 | commit refused through the hook | base commit; staged `notes.txt` with `forbidden-token here` at line 2 | `git commit` | non-zero; HEAD unchanged; output has `scrub: notes.txt:2: denylist:2` | R1 "is refused"; D1 "runs at pre-commit"; exit code not pinned (Q11) |
| R1.6 | clean commit lands | base commit; staged `notes.txt` = `alpha` / `bravo` | `git commit` | exit 0; HEAD moved | R5 "A clean run … exits 0"; D1 |
| R2.1 | case-insensitive | staged line 2 `Found FORBIDDEN-Token again` | `--cached` | exit 1; hits = `scrub: notes.txt:2: denylist:2` | R2 "matches case-insensitively"; R1 "naming … the denylist line" |
| R2.2 | ERE | staged line 3 `key example-secret-42 end` | `--cached` | exit 1; hits = `scrub: notes.txt:3: denylist:3` | Language "one POSIX ERE per line" |
| R2.3 | ERE boundary | staged `example-secret-x` | `--cached` | exit 0; `scrub: clean` | Language "one POSIX ERE per line" — `[0-9]+` needs a digit |
| R2.4 | `#` line not a pattern | denylist `# release-notes` / `forbidden-token`; staged line `# release-notes` | `--cached` | exit 0; `scrub: clean` | R2 "a `#` line … in the denylist are not patterns" |
| R2.5 | blank line not a pattern | denylist with an empty line between two patterns; staged `alpha` / `bravo` | `--cached` | exit 0; `scrub: clean` | R2 "a blank line in the denylist are not patterns" |
| R2.6 | whitespace-only line not a pattern | denylist with a line holding one space; staged `alpha bravo` | `--cached` | exit 0; `scrub: clean` | Assumed: whitespace-only is blank (Q5) |
| R2.7 | two patterns, one line | staged line 1 `forbidden-token beside example-secret-9` | `--cached` | exit 1; hits = `scrub: notes.txt:1: denylist:2` and `scrub: notes.txt:1: denylist:3` | Assumed: one line per matching pattern (Q3) |
| R2.8 | no patterns at all | denylist `# nothing listed yet` + blank line; staged `alpha` | `--cached` | exit 0; `scrub: clean` | Assumed: present-but-empty passes (Q6) |
| R3.1 | variable wins | default `$HOME/…/denylist` = `forbidden-token`; `ROBOWRIGHT_DENYLIST` file = `example-secret-[0-9]+`; staged `forbidden-token here` / `example-secret-7 here` | `--cached` | exit 1; hits = only `scrub: notes.txt:2: denylist:1` (line 1 of the named file) | R3 "`ROBOWRIGHT_DENYLIST` names the denylist" |
| R3.2 | default path | variable unset; `$HOME/.config/robowright/denylist` = `forbidden-token`; staged `forbidden-token here` | `--cached` | exit 1; hits = `scrub: notes.txt:1: denylist:1` | R3 "unset, it is `$HOME/.config/robowright/denylist`" |
| R3.3 | empty variable = default | variable set to empty; default = `forbidden-token`; staged `forbidden-token here` | `--cached` | exit 1; hits = `scrub: notes.txt:1: denylist:1` | Language "`${ROBOWRIGHT_DENYLIST:-$HOME/.config/robowright/denylist}`" — `:-` treats empty as unset |
| R3.4 | missing default refuses | variable unset; no file at the default path; staged clean line | `--cached` | exit 2; output names `<scratch HOME>/.config/robowright/denylist` | R3 "a missing file refuses with exit 2 naming the path it looked for"; D2 |
| R3.5 | missing named file refuses | variable names a path with no file; staged clean line | `--cached` | exit 2; output names that path | R3 as above; D2 "an absent denylist is a refusal (exit 2), not a pass" |
| R3.6 | missing denylist refuses a commit | variable names a missing file; staged clean line | `git commit` | non-zero; HEAD unchanged; output names the path | D2; D1 pre-commit |
| R3.7 | missing denylist refuses a push | variable names a missing file; one clean local commit, empty remote | `git push origin main` | non-zero; remote `main` absent; output names the path | D2; D1 pre-push |
| R4.1 | `--cached` reads the index | committed 10-line file; staged clean edit of line 1; unstaged edit putting `forbidden-token` on line 10 | `--cached` | exit 0; `scrub: clean` | R4 "`--cached` reads the index"; hotspot "a hit in an unstaged hunk and a clean staged hunk must pass" |
| R4.2 | staged rename | committed `draft.txt` with `forbidden-token here` at line 2; `git mv draft.txt renamed.txt` | `--cached` | exit 1; hits = `scrub: renamed.txt:2: denylist:2` | hotspot "a renamed file with a hit must fail"; path Assumed new name (Q2) |
| R4.3 | every commit in range | base B0; C1 adds `forbidden-token here` at `notes.txt:2`; C2 removes it | `--range B0 C2` | exit 1; hits = `scrub: notes.txt:2: denylist:2` | R4 "reads every commit in the range" — not the net diff |
| R4.4 | `<old>` is outside the range | C1 adds the hit; C2 removes it | `--range C1 C2` | exit 0; `scrub: clean` | R4 range `<old> <new>`; R1 removed line not a hit |
| R4.5 | zero `<old>`, nothing on a remote | C1 adds `forbidden-token here` at `notes.txt:2`; C2 adds a clean file; no remote-tracking refs | `--range 000…0 C2` | exit 1; hits = `scrub: notes.txt:2: denylist:2` | R4 "`<old>` all zeros means every commit not on any remote" |
| R4.6 | zero `<old>` skips remote commits | C1 with the hit pushed to `origin/main`; branch `feature` adds clean C3 | `--range 000…0 C3` | exit 0; `scrub: clean` | R4 as above; hotspot "a zero remote oid (new branch: only commits not on any remote)" |
| R4.7 | committed rename | C0 commits `draft.txt` with the hit at line 2; C1 renames it `renamed.txt` | `--range C0 C1` | exit 1; hits = `scrub: renamed.txt:2: denylist:2` | Assumed: rename in a range fails like a staged one (Q8) |
| R4.8 | `--tree` reads tracked files | committed `docs/guide.md` with `forbidden-token appears here` at line 3 | `--tree` | exit 1; hits = `scrub: docs/guide.md:3: denylist:2` | R4 "`--tree` reads every tracked file"; path Assumed repo-relative (Q1) |
| R4.9 | `--tree` skips untracked | clean tracked tree; untracked `scratch.txt` = `forbidden-token` | `--tree` | exit 0; `scrub: clean` | R4 "every **tracked** file" |
| R4.10 | `--tree` reads the working copy | committed clean `docs/guide.md`; uncommitted edit adds the hit at line 3 | `--tree` | exit 1; hits = `scrub: docs/guide.md:3: denylist:2` | Assumed: working-tree content (Q7) |
| R5.1 | clean output | staged `alpha` / `bravo` | `--cached` | exit 0; stdout has the line `scrub: clean`; no hit lines | R7 "A clean run prints `scrub: clean` and exits 0" |
| R5.2 | one line per hit | staged `notes.txt:1` `forbidden-token one` and `docs/guide.md:2` `example-secret-12 two` | `--cached` | exit 1; hits = `scrub: docs/guide.md:2: denylist:3` and `scrub: notes.txt:1: denylist:2`; no `scrub: clean` | R7 "one `scrub: <file>:<line>: denylist:<n>` per hit and exits 1"; path Assumed repo-relative (Q1) |
| R6.1 | first push reads all unpushed commits | empty remote; C1 adds the hit at `notes.txt:2`; C2 clean tip | `git push origin main` | non-zero; remote `main` absent; output has `scrub: notes.txt:2: denylist:2` | R6; R4 zero oid "every commit not on any remote"; githooks "remote oid all zeros = remote ref does not exist" |
| R6.2 | update push reads only new commits | remote `main` holds a commit with the hit; local adds clean C2 | `git push origin main` | exit 0; remote `main` = C2 | R6 "runs the range check per line"; R4 `--range <old> <new>` |
| R6.3 | update push with a hit | remote `main` at clean A; local adds C1 with the hit at `notes.txt:2` | `git push origin main` | non-zero; remote `main` = A; output has `scrub: notes.txt:2: denylist:2` | R6 "any hit aborts the push" |
| R6.4 | new branch off pushed history | `origin/main` holds the hit commit; `feature` adds clean C3 | `git push origin feature` | exit 0; remote `feature` = C3 | R4 zero oid "every commit not on any remote"; hotspot "a zero remote oid" |
| R6.5 | force-push, clean rewrite | remote `main` = A → B (B has the hit); local reset to A, adds clean C | `git push --force origin main` | exit 0; remote `main` = C | hotspot "a force-push of a rewritten branch"; R4 range `B..C` = {C}; R1 removed line not a hit |
| R6.6 | force-push, rewrite adds a hit | remote `main` = A → B clean; local reset to A, adds C with the hit at `notes.txt:2` | `git push --force origin main` | non-zero; remote `main` = B; output has `scrub: notes.txt:2: denylist:2` | hotspot "a force-push of a rewritten branch"; R6 "any hit aborts the push" |
| R6.7 | several refs, one hit | remote `main` = A; local `main` adds clean C; new `feature` adds the hit | `git push origin main feature` | non-zero; remote `main` = A; remote `feature` absent | hotspot "a push of several refs in one call"; R6 "any hit aborts the push" |
| R6.8 | every stdin line is read | `main` clean, `feature` with the hit at `notes.txt:2`; no remote refs | `tools/hooks/pre-push origin <url>` with stdin `main` line first, `feature` line second, both remote oids zero | non-zero; output has `scrub: notes.txt:2: denylist:2` | R6 "reads its stdin lines … runs the range check per line"; githooks stdin format |
| R6.9 | delete is not a hit | remote `feature` holds the hit commit | `git push origin --delete feature` | exit 0; remote `feature` absent | Assumed: `(delete)` is not a hit (Q9); githooks "a deleted local ref arrives as local oid all zeros with local-ref `(delete)`" |

## Held-out examples

One per rule, added after the implementation went green; the rows above were written before it existed.

| # | Rule | Given | When | Then | Expected value from |
|---|---|---|---|---|---|
| H1 | R1 | a ten-line file gains a hit above line 1 and another before its ninth original line | `--cached` | exit 1; `scrub: notes.txt:1: denylist:2` and `scrub: notes.txt:10: denylist:2` | rule 1 "naming file, line"; new-side numbering as R1.3 |
| H2 | R2 | denylist `Forbidden-TOKEN`; text `a forbidden-token here` | `--cached` | exit 1; `scrub: notes.txt:1: denylist:1` | rule 2 "matches case-insensitively" |
| H3 | R3 | `ROBOWRIGHT_DENYLIST` names a path containing a space | `--cached` on a hit | exit 1; `scrub: notes.txt:1: denylist:1` (line 1 of the named file) | rule 3 "`ROBOWRIGHT_DENYLIST` names the denylist" |
| H4 | R4 | tracked `a-first.txt` holds a hit, `z-last.txt` is clean | `--tree` | exit 1; `scrub: a-first.txt:1: denylist:2` | rule 4 "`--tree` reads every tracked file" |
| H5 | R4 | range base..tip: a clean commit, then a tip commit adding a hit | `--range base tip` | exit 1; `scrub: notes.txt:1: denylist:2` | rule 4 "reads every commit in the range" |
| H6 | R5 | a hit staged in `my notes/to do.txt` | `--cached` | exit 1; `scrub: my notes/to do.txt:1: denylist:2` | rule 7 "`scrub: <file>:<line>: denylist:<n>`" |
| H7 | R6 | pre-push stdin: a `(delete)` line, then a new branch carrying a hit | the hook | non-zero; output has `scrub: notes.txt:1: denylist:2` | rule 6 "runs the range check per line" |
| H8 | R7 | denylist `# synthetic`, blank, `forbidden-token`, CRLF line endings; a commit adds a hit | `--range base tip` | exit 1; `scrub: notes.txt:1: denylist:3` | rule 7 "comment and blank lines counted" |
| H9 | R8 | a commit adds `a\nb` (backslash, `n`) and `b.md`, each holding a hit | `--range base tip` | exit 1; `scrub: a\nb:1: denylist:2` and `scrub: b.md:2: denylist:2` | rule 8 "a backslash in a name is a backslash in the output" |
| H10 | R9 | a staged name holding a newline; no line matches | `--cached` | exit 2; a stderr line `scrub: …1…`; no `scrub: clean` | rule 9 "the gate refuses with exit 2 naming the count" |

## Gate findings

From the U1 gate review (F1, F2). Under a UTF-8 locale, the macOS default, a byte that is not valid UTF-8
(Latin-1 `naïve`, `0xEF`) hid every hit. Rows written and seen red before the fix.

| # | Rule | Given | When | Then | Expected value from |
|---|---|---|---|---|---|
| G1 | R1 | `a-latin.txt` (a Latin-1 line) staged ahead of `z-plain.txt` with a hit on line 1 | `--cached` | exit 1; `scrub: z-plain.txt:1: denylist:2` | rule 1 "a commit whose added lines match … is refused" |
| G2 | R1 | the hit is on the Latin-1 line itself, line 2 of `a-latin.txt` | `--cached` | exit 1; `scrub: a-latin.txt:2: denylist:2` | rule 1 |
| G3 | R4, R6 | the tip commit adds both files as in G1 | `--range base tip` | exit 1; `scrub: z-plain.txt:1: denylist:2` | rule 4 "reads every commit in the range"; rule 6 |
| G4 | R4 | tracked `a-latin.txt` with its Latin-1 line 2 matching | `--tree` | exit 1; `scrub: a-latin.txt:2: denylist:2` | rule 4 "`--tree` reads every tracked file" |

From the second U1 gate review (F1–F3). G7 and G9 are the same kind of gap, found while fixing those: git or a
byte-level check deciding a file is not text. Rows written and seen red before the fix.

| # | Rule | Given | When | Then | Expected value from |
|---|---|---|---|---|---|
| G5 | R2 | denylist `ëvarnoq`; staged `Contact Ëvarnoq today`; UTF-8 locale | `--cached` | exit 1; `scrub: a.txt:1: denylist:1` | rule 2 "matches case-insensitively" |
| G6 | R1 | `*.cfg diff=first`, `diff.first.textconv = head -1`; `app.cfg` line 2 matches | `--cached` | exit 1; `scrub: app.cfg:2: denylist:2` | rule 1 "added lines" |
| G7 | R1 | `*.cfg -diff`; `app.cfg` line 1 matches | `--cached` | exit 1; `scrub: app.cfg:1: denylist:2` | rule 1 |
| G8 | R1 | added line 2 is `pre<NUL> forbidden-token`, after a 9000-byte line 1 | `--cached` | exit 1; `scrub: n.txt:2: denylist:2` | rule 1 |
| G9 | R4 | tracked `blob.bin` holds NUL bytes, and its line 2 matches | `--tree` | exit 1; `scrub: blob.bin:2: denylist:2` | rule 4 "`--tree` reads every tracked file" |
| G10 | R8 | one commit turns `a.txt` into a symlink, adds a hit at `m.txt` line 3, and changes `z.txt` | `--range base tip` | exit 1; hits = `scrub: m.txt:3: denylist:2` | rule 8 "a hit … still names its own file and line" (U2 gate attempt 1, F1) |
| G11 | R8 | `diff.submodule=log`; a submodule bump and a hit in `z.txt` staged | `--cached` | exit 1; hits = `scrub: z.txt:1: denylist:2` | rule 8, as G10 (U2 gate attempt 1, F1) |
| G13 | R1 | hits staged in `sub/hit.txt`, `other/hit.txt`, `top.txt`; the gate run by hand from `sub/` | `--cached` | exit 1; all three hits, named from the repository root | rule 1 "refused, naming file, line" (U2 gate attempt 2, F1) |
| G14 | R8 | an index name in decomposed Unicode (`cafe` + U+0301 `.txt`) holding a hit | `--cached` | exit 1; `scrub: café.txt:1: denylist:2`, the bytes as stored | rule 8 "exactly as `git ls-files` lists it" (U2 gate attempt 2, F2) |
| G12 | R9 | a tracked newline name, staged `git mv` to `plain.txt` | `--cached` | exit 0; `scrub: clean` | rule 9 "cannot be reported on one line": a name the change removes is never reported. Assumed, settles Q15 for deleted names (U2 gate attempt 1, F2) |

## U2 · a hit names the denylist line, never the pattern

Written under U2 before `tools/scrub-gate.sh` changed, from the brief's rules 7–9 and D8, D9. A row's
`denylist:<n>` counts the lines of that row's own denylist from 1, comment and blank lines included. R7.5 and
R8.2 are the two record-misalignment scenarios of `reviews/U2-gate-3.md` F1 (B and A), on placeholder patterns.
`⏎` is a real newline in a file name; `\n` and `\t` inside a file name are a literal backslash and a letter.

| # | Rule | Given | When | Then | Expected value from |
|---|---|---|---|---|---|
| R7.1 | hit names its line, never its text | denylist `# synthetic patterns for the leak check` / (empty) / `forbidden-token` / `# a second comment` / `quokka-[0-9]+-zebra`; staged `notes.txt` = `a quokka-42-zebra b` | `--cached` | exit 1; hits = `scrub: notes.txt:1: denylist:5`; neither stdout nor stderr contains `quokka`, `zebra` or `[0-9]`, in any case | rule 7 "`<n>` the 1-based line number … comment and blank lines counted" (5th line); "No output of the gate … contains any part of a pattern's text"; parts Assumed (Q16) |
| R7.2 | counted from 1 | denylist `forbidden-token` / `# a trailing comment`; staged `forbidden-token here` | `--cached` | exit 1; hits = `scrub: notes.txt:1: denylist:1` | rule 7 "the 1-based line number" |
| R7.3 | a whitespace-only line counts | denylist `forbidden-token` / ` ` / `example-secret-[0-9]+`; staged `key example-secret-5 end` | `--cached` | exit 1; hits = `scrub: notes.txt:1: denylist:3` | rule 7 "comment and blank lines counted"; whitespace-only is blank, Assumed (Q5) |
| R7.4 | unusable pattern | denylist `# synthetic patterns` / `forbidden-token` / `zqx-[wvu` (unclosed bracket: no POSIX ERE); staged `notes.txt` = `alpha` | `--cached` | exit 2; a line `scrub: …denylist:3…` on stdout or stderr; neither stream contains `zqx` or `wvu`, in any case | rule 7 "An unusable pattern is reported as `denylist:<n>`"; D8 "an error line names a path or a line number, never a pattern's text"; exit 2 Assumed (Q13) |
| R7.5 | F1 B: a pattern shaped like a hit tail | denylist `# synthetic patterns` / `zqx:12: wvu`; tracked `a\nb\tc` = `clean line` and `c.md` = `ZQX:12: WVU here` | `--tree` | exit 1; hits = `scrub: c.md:1: denylist:2`; neither stream contains `zqx` or `wvu`, in any case | rule 7 "No output … contains any part of a pattern's text"; rule 8 "a hit after such a name still names its own file and line"; `reviews/U2-gate-3.md` F1 scenario B |
| R8.1 | backslash name unchanged | tracked `a\nb` = `forbidden-token here` | `--tree` | exit 1; hits = `scrub: a\nb:1: denylist:2` | rule 8 "a backslash in a name is a backslash in the output"; unquoted, Assumed (Q12) |
| R8.2 | F1 A: alignment after a backslash name | tracked `a\nb\tdenylist not found` = `one line of text`, listed before `c.md` = `intro` / `forbidden-token here` | `--tree` | exit 1; the only hit-shaped line (`denylist:<digit>` or `:<digits>: `) in either stream is `scrub: c.md:2: denylist:2` | rule 8 "a hit after such a name still names its own file and line (the record alignment does not depend on the name's characters)"; `reviews/U2-gate-3.md` F1 scenario A |
| R8.3 | backslash name at pre-commit | base commit; staged new `a\nb` = `alpha` / `forbidden-token here` | `--cached` | exit 1; hits = `scrub: a\nb:2: denylist:2` | rule 8 as R8.1; Assumed (Q12) |
| R8.4 | tab in a name | tracked `a<TAB>b.txt` = `forbidden-token here` | `--tree` | exit 1; hits = `scrub: a<TAB>b.txt:1: denylist:2`, the tab a real tab | rule 8 "the record alignment does not depend on the name's characters"; hotspot "a file name with … a tab"; unquoted, Assumed (Q12) |
| R8.5 | colon in a name | tracked `docs/a:b.md` = `one` / `two` / `three` / `forbidden-token here` | `--tree` | exit 1; hits = `scrub: docs/a:b.md:4: denylist:2` | rule 8 as R8.4; hotspot "a colon" |
| R8.6 | non-ASCII name | tracked `été.md` = `forbidden-token here` | `--tree` | exit 1; hits = `scrub: été.md:1: denylist:2` | rule 8 "exactly as `git ls-files` lists it"; unquoted, Assumed (Q12); the non-UTF-8 case is untested (Q17) |
| R9.1 | newline names in the tree | tracked `one⏎name.txt` = `forbidden-token here`, `two⏎name.txt` = `alpha`, `three⏎name.txt` = `bravo`, `notes.txt` = `forbidden-token here` | `--tree` | exit 2; a stderr line `scrub: …3…`; no hit-shaped line in either stream | rule 9 "refuses with exit 2 naming the count of such names, and prints no hit line"; stream and shape Assumed (Q14) |
| R9.2 | newline names staged | base commit; the four files of R9.1 staged | `--cached` | exit 2; a stderr line `scrub: …3…`; no hit-shaped line in either stream | rule 9 as R9.1; Assumed (Q14); count reading not pinned (Q15) |
| R9.3 | newline names in a pushed range | base commit; one commit adds the four files of R9.1 | `--range base tip` | exit 2; a stderr line `scrub: …3…`; no hit-shaped line in either stream | rule 9 as R9.1; Assumed (Q14); count reading not pinned (Q15) |

## U5 · a file name is content

Written under U5 before `tools/scrub-gate.sh` changed, from the brief's rules 10–13 and D10–D12, and from
`reviews/end-of-stack.md` F1–F5 (the G rows). **N** is the file name `wombat-forbidden-token-kestrel.md`; on
the default denylist it matches line 2 and no other. "No leak of W…" means neither stdout nor stderr holds
any of the listed words, in any case (Q21). Every `:0:` is sourced to Q18 and every `(name withheld)` to Q19,
as well as to the row's own column. H11–H17 are hostile shapes written with the rule rows, before the gate
changed. They are not held out as H1–H10 were.

| # | Rule | Given | When | Then | Expected value from |
|---|---|---|---|---|---|
| R10.1 | name and line both match, index | base commit; staged N = `alpha` / `key example-secret-7 end` | `--cached` | exit 1; hits = `scrub: (name withheld):0: denylist:2` and `scrub: (name withheld):2: denylist:3`; no leak of `wombat`, `forbidden`, `token`, `kestrel`, `example`, `secret` | R10 "one line `scrub: (name withheld):0: denylist:<n>` per matching pattern … a content hit inside it is `scrub: (name withheld):<line>: denylist:<n>` … No output — stdout, stderr — contains any part of a withheld name"; R7 "No output … contains any part of a pattern's text"; Assumed (Q21) |
| R10.2 | name and line both match, range | base commit B; tip T adds N = `alpha` / `key example-secret-7 end` | `--range B T` | as R10.1 | R10 "`--range`, for each commit, every path that commit adds"; as R10.1 |
| R10.3 | name and line both match, tree | base commit; committed N = `alpha` / `key example-secret-7 end` | `--tree` | as R10.1 | R10 "`--tree`, every tracked path"; as R10.1 |
| R10.4 | a directory's name matches | base commit; staged `wombat-forbidden-token/kestrel.md` = `alpha` | `--cached` | exit 1; hits = `scrub: (name withheld):0: denylist:2`; no `scrub: clean`; no leak of `wombat`, `forbidden`, `token`, `kestrel` | R10 "A path under a directory whose name matches is a matching path … A run whose only hits are names still prints no `scrub: clean`" |
| R10.5 | commit refused on a name | base commit; staged N = `alpha` | `git commit` | non-zero; HEAD unchanged; output has `scrub: (name withheld):0: denylist:2`; no leak of `wombat`, `forbidden`, `token`, `kestrel` | R10 "A matching path is a hit in its own right"; D1 pre-commit; exit not pinned (Q11, Q29) |
| R10.6 | untouched old name, range | C0 commits `readme.txt` and N = `alpha`; C1 edits only `readme.txt` | `--range C0 C1` | exit 0; `scrub: clean` | R10 "every path that commit adds or changes"; brief, U5 acceptance "A name that predates the range and is untouched by it (`--range`) — not a hit" |
| R10.7 | the same tree, whole | the tree of R10.6 at C1 | `--tree` | exit 1; hits = `scrub: (name withheld):0: denylist:2`; no `scrub: clean`; no leak of `wombat`, `forbidden`, `token`, `kestrel` | R10 "`--tree`, every tracked path"; brief, U5 acceptance "and `--tree` on the same tree — a hit" |
| R10.8 | renamed to a matching name | committed `draft.txt` = `alpha`; `git mv draft.txt N` | `--cached` | exit 1; hits = `scrub: (name withheld):0: denylist:2`; no leak of `wombat`, `forbidden`, `token`, `kestrel` | R10 "every path staged as … renamed-to" |
| R10.9 | a staged deletion | committed `readme.txt` and N = `alpha`; `git rm N` | `--cached` | exit 0; `scrub: clean` | R10 "a staged deletion is not in scope"; R13 "a deleted path … not matched" |
| R10.10 | a staged edit to a matching name | committed `readme.txt` and N = `alpha`; staged N = `alpha` / `bravo` | `--cached` | exit 1; hits = `scrub: (name withheld):0: denylist:2`; no `scrub: clean`; no leak of `wombat`, `forbidden`, `token`, `kestrel` | R10 "every path staged as added, modified" |
| R10.11 | an unstaged matching name | committed `readme.txt` and N = `alpha`; staged edit to `readme.txt` only | `--cached` | exit 0; `scrub: clean` | R10 "`--cached`, every path staged as …": N is not staged |
| R10.12 | a commit edits a matching name | C0 commits N = `alpha`; C1 changes N to `alpha` / `bravo` | `--range C0 C1` | exit 1; hits = `scrub: (name withheld):0: denylist:2`; no `scrub: clean`; no leak of `wombat`, `forbidden`, `token`, `kestrel` | R10 "`--range`, for each commit, every path that commit adds or changes" |
| R10.13 | whole path, across a slash | denylist `# synthetic patterns for the path check` / `ibis/kestrel`; base commit; staged `ibis/kestrel.md` = `alpha` | `--cached` | exit 1; hits = `scrub: (name withheld):0: denylist:2`; no leak of `ibis`, `kestrel` | R10 "matched, whole" (Q28): no single component matches |
| R11.1 | relative denylist from a subdirectory, tree | tracked `sub/keep.txt` = `alpha`, `notes.txt` = `alpha` / `forbidden-token here`; the default denylist at `<scratch>/<id>.denylist`; `ROBOWRIGHT_DENYLIST=../../<id>.denylist`, which from the repository root names no file | `--tree`, run from `sub/` | exit 1; hits = `scrub: notes.txt:2: denylist:2` | R11 "resolved against the caller's working directory once, before the mode runs … a relative path from a subdirectory reads the same file `--cached` would"; name repository-relative, Assumed (Q23); end-of-stack F2 |
| R11.2 | relative denylist missing, tree | the tree of R11.1; `ROBOWRIGHT_DENYLIST=../../<id>-absent.denylist`, no such file | `--tree`, run from `sub/` | exit 2; output holds `../../<id>-absent.denylist`; no `scrub: clean`; no hit-shaped line | R11 "A path that is missing … refuses with exit 2 naming the path as given, prints no hit line and no `scrub: clean`" (Q22) |
| R11.3 | directory as denylist, index | `ROBOWRIGHT_DENYLIST` names a directory; base commit; staged `notes.txt` = `forbidden-token here` | `--cached` | exit 2; output holds the directory's path; no hit-shaped line; no `scrub: clean` | R11 "a directory refuses with exit 2 naming the path as given, prints no hit line and no `scrub: clean`, in every mode"; end-of-stack F5 |
| R11.4 | directory as denylist, tree | as R11.3; `notes.txt` committed | `--tree` | as R11.3 | R11 as R11.3 |
| R12.1 | dangling link, matching text | base commit; tracked symlink `link-dangling` → `/nonexistent/forbidden-token/path` | `--tree` | exit 1; hits = `scrub: link-dangling:1: denylist:2`; no leak of `forbidden`, `token` | R12 "a dangling link whose text matches is a hit at line 1"; end-of-stack F3 |
| R12.2 | link out of the repository | `<scratch>/outside.txt` = `forbidden-token here`; base commit; tracked symlink `outside-link` → that file's absolute path | `--tree` | exit 0; `scrub: clean` | R12 "a link to a matching file outside the repository is clean when its text is" |
| R12.3 | link inside the repository | tracked `m.txt` = `alpha` / `forbidden-token here`; tracked symlink `a-link` → `m.txt` | `--tree` | exit 1; hits = `scrub: m.txt:2: denylist:2` only | R12 "reads a tracked symlink's link text, never its target"; R4 "`--tree` reads every tracked file" for `m.txt` |
| R12.4 | tracked path absent from disk | base commit; committed `notes.txt` = `forbidden-token here`, then deleted from the working copy, not staged | `--tree` | exit 0; `scrub: clean` | R12 "a tracked path absent from disk is still skipped" |
| R13.1 | a commit deletes a matching name | C0 commits `readme.txt` and N = `alpha`; C1 `git rm N` | `--range C0 C1` | exit 0; `scrub: clean` | R10 "every path that commit adds or changes (not deletes)"; R13 "a deleted path … not matched" |
| R13.2 | commit message not matched | base commit B; C1 adds `notes.txt` = `alpha` with message `forbidden-token in the message` | `--range B C1` | exit 0; `scrub: clean` | R13 "a commit message [is] not matched"; D10 "Commit messages stay unmatched" |
| R13.3 | non-matching names pass through | the R8.1–R8.6 and H9 Givens: no name matches a pattern | as those rows | as those rows, unchanged | brief, U5 Verification standard "an R8 row whose name matches no pattern is untouched" — no new test |
| H11 | a withheld name with a tab, between names printed as listed | tracked `a\nb` = `forbidden-token here`; `m<TAB>wombat-forbidden-token.md` = `alpha` / `key example-secret-7 end`; `z.md` = `one` / `two` / `forbidden-token here` | `--tree` | exit 1; hits = `scrub: (name withheld):0: denylist:2`, `scrub: (name withheld):2: denylist:3`, `scrub: a\nb:1: denylist:2`, `scrub: z.md:3: denylist:2`; no leak of `wombat`, `forbidden`, `token`, `example`, `secret` | R10 as R10.3; R8 "unless rule 10 withholds it … the record alignment does not depend on the name's characters" |
| H12 | a name that matches only by case | base commit; staged `Wombat-FORBIDDEN-Token-Kestrel.md` = `alpha` | `--cached` | exit 1; hits = `scrub: (name withheld):0: denylist:2`; no leak of `wombat`, `forbidden`, `token`, `kestrel`, in any case | R10 "against every pattern under rule 2"; R2 "matched case-insensitively" |
| H13 | renamed from a matching name | committed N = `alpha`; `git mv N plain.txt` | `--cached` | exit 0; `scrub: clean` | R10 "renamed-to or copied-to (a staged deletion is not in scope)" (Q27) |
| H14 | two patterns, one name | base commit; staged `wombat-forbidden-token-example-secret-42.md` = `alpha` | `--cached` | exit 1; hits = `scrub: (name withheld):0: denylist:2` and `scrub: (name withheld):0: denylist:3`; no leak of `wombat`, `forbidden`, `token`, `example`, `secret` | R10 "one line … per matching pattern" |
| H15 | a matching name holding a newline | tracked `wombat-forbidden-token⏎kestrel.md` = `alpha`, `two⏎name.txt` = `alpha`, `three⏎name.txt` = `bravo`, `notes.txt` = `forbidden-token here` | `--tree` | exit 2; a stderr line `scrub: …3…`; no hit-shaped line in either stream; no leak of `wombat`, `forbidden`, `token`, `kestrel` | Assumed: R9 wins (Q20); R9 "refuses with exit 2 naming the count … prints no hit line"; R10 "No output … contains any part of a withheld name"; Q14 |
| H16 | push refused on a name | empty remote; base commit, then a commit adding N = `alpha` | `git push origin main` | non-zero; remote `main` absent; output has `scrub: (name withheld):0: denylist:2`; no leak of `wombat`, `forbidden`, `token`, `kestrel` | R10 `--range` scope; R6 "any hit aborts the push" |
| H17 | unreadable denylist | the denylist file has mode `000`; committed `notes.txt` = `forbidden-token here` | `--tree` | exit 2; output holds the denylist's path; no hit-shaped line; no `scrub: clean` | R11 "A path that is missing, unreadable or a directory refuses with exit 2 naming the path as given, prints no hit line and no `scrub: clean`" |
| H18 | an unreadable file with a matching name | committed `readme.txt`, and N = `alpha` with mode `000` | `--tree` | exit 2; no `scrub: clean`; no leak of `wombat`, `forbidden`, `token`, `kestrel` | R10 "No output — stdout, stderr — contains any part of a withheld name"; exit 2 Assumed (Q30) (U5 gate attempt 1, F1) |
| H19 | a tool's warning names a path under a matching directory | base commit; staged `wombat-forbidden-token/kestrel.md` = `alpha` and `wombat-forbidden-token/.gitattributes` = `[attr]bin -diff` (git warns naming that file on every diff) | `--cached` | exit 1; hits include `scrub: (name withheld):0: denylist:2`; no leak of `wombat`, `forbidden`, `token`, `kestrel` | R10 "No output — stdout, stderr — contains any part of a withheld name" (U5 gate attempt 2, F1) |
| H20 | as H19, pushed | base commit B; T commits the H19 files | `--range B T` | as H19 | R10 as H19; R6 "runs the range check per line" |
| H21 | a tracked file under a directory the gate cannot search | committed `sealed/notes.txt` holding a hit; `sealed` mode `000` | `--tree` | exit 2; no `scrub: clean` | R4 "`--tree` reads every tracked file"; exit 2 Assumed as Q30 — a file that cannot be read has not been checked (end-of-stack F1) |
| G15 | F1: a directory so named, content hit inside | base commit; committed `wombat-forbidden-token/kestrel.md` = `intro` / `key example-secret-7 end` | `--tree` | exit 1; hits = `scrub: (name withheld):0: denylist:2` and `scrub: (name withheld):2: denylist:3`; no leak of `wombat`, `forbidden`, `token`, `kestrel`, `example`, `secret` | end-of-stack F1 "A directory named after a pattern leaks the same way"; R10 "A path under a directory whose name matches is a matching path" |
| G16 | F2 in another mode: relative denylist, range | base commit B; T adds `sub/keep.txt` = `alpha` and `notes.txt` = `alpha` / `forbidden-token here`; relative denylist as R11.1 | `--range B T`, run from `sub/` | exit 1; hits = `scrub: notes.txt:2: denylist:2` | R11 "read from that resolution in every mode" |
| G17 | F5 in the third mode: directory, range | as R11.3; B, then T adds `notes.txt` = `forbidden-token here` | `--range B T` | exit 2; output holds the directory's path; no hit-shaped line; no `scrub: clean` | end-of-stack F5; R11 "a directory refuses with exit 2 … in every mode" |
| G18 | F3's other side: the same link staged | base commit; staged symlink `link-dangling` → `/nonexistent/forbidden-token/path` | `--cached` | exit 1; hits = `scrub: link-dangling:1: denylist:2`; no leak of `forbidden`, `token` | end-of-stack F3 "`--cached` prints `scrub: link-dangling:1: denylist:3`" (its own denylist); R13 |

## Polish · every refusal says why

Written under tracer-polish P1 before `tools/scrub-gate.sh` changed, from the brief's Goal and P-D1–P-D3. The
reason lines' wording is the Session's, under the brief's "The exact wording of each reason line, so long as it
is fixed text starting `scrub: ` — the Session's call"; the Givens are the Session's measured fixtures. Every row
runs on the default denylist. "No leak" means neither stdout nor stderr holds, in any case, `forbidden`, `token`,
`example`, `secret`, the scratch base's path or the scratch repository's path, nor any path the row's Given names.

R14 — Every refusal, a bash error inside the gate included, prints exactly one reason line on stderr, `scrub: <fixed text>`, nothing on stdout, and exits 2. A reason line is fixed text: it names no path, no pattern and no part of a withheld name (R7, R10 hold for it).

| # | Rule | Given | When | Then | Expected value from |
|---|---|---|---|---|---|
| R14.1 | no scratch directory | base commit; `TMPDIR` = `<scratch>/no-such-tmpdir`, which does not exist | `--tree` | exit 2; stdout empty; stderr lines = `scrub: could not create a scratch directory`; no leak, nor of the `TMPDIR` path | Goal "never exits without a line: every refusal … prints exactly one fixed sentence on fd 3 … exits 2"; P-D1 "`mktemp` at `:57` … each get a fixed sentence"; wording, the Session's; P-D3 |
| R14.2 | `<new>` names no commit | base commit B | `--range B nonexistent` | exit 2; stdout empty; stderr lines = `scrub: could not list the commits to check`; no leak | Goal, as R14.1; P-D1 "`git rev-list` on a bad `<new>` at `:183`"; wording, the Session's; P-D3 |
| R14.3 | no repository to list | a directory under the scratch base, outside the scratch repository; `GIT_CEILING_DIRECTORIES` = the scratch base's parent | `--tree`, run from that directory | exit 2; stdout empty; stderr lines = `scrub: could not list the tracked files`; no leak | Goal, as R14.1; P-D1 "`git ls-files` failing at `:205`"; brief hotspot "'outside a repo' exits at `:205`, not `:236`"; wording, the Session's; P-D3 |
| R14.4 | top level cannot be entered | base commit; `GIT_WORK_TREE` = `<scratch>/no-such-work-tree`, which does not exist | `--tree`, run from the scratch repository | exit 2; stdout empty; stderr lines = `scrub: could not enter the top level of the repository`; no leak, nor of the work-tree path | Goal, as R14.1; P-D1 "`cd` to the top level failing at `:236` … interpolating … `$(git rev-parse …)` is what could carry a path"; wording, the Session's; P-D3 |
| R14.5 | a bash error | base commit; `HOME` and `ROBOWRIGHT_DENYLIST` both unset | `--tree` | exit 2; stdout empty; stderr lines = `scrub: stopped on an internal error`; no leak | Goal "every refusal, including a bash error inside the gate, prints exactly one fixed sentence … and exits 2"; P-D2 "A bash error inside the gate … becomes a refusal"; wording, the Session's; P-D3 |
| H23 | held out: the scratch directory goes with the run | base commit; `TMPDIR` = `<scratch>/tmp`, an empty directory | `--tree` | exit 0; `scrub: clean`; `<scratch>/tmp` is empty afterwards | P-D2 "the EXIT trap … removes `$work` if set" |
| H24 | an inherited `work` | a directory `<scratch>/victim` holding `keep.txt`; `work` = that directory in the environment; `ROBOWRIGHT_DENYLIST` names no file | `--tree` | exit 2; `<scratch>/victim/keep.txt` still exists | P-D2 "removes `$work` if set" — the gate's own `$work`; brief hotspot "it must not `rm -rf` an unset or empty `$work`" (P1 gate F1) |
| H25 | an inherited `verdict` | as R14.5, plus `verdict=hit` in the environment | `--tree` | as R14.5 | R14; P-D2 (P1 gate F2) |

## Polish · the pre-push fallback and the ancestor that is now a file

Written under tracer-polish P2 from what the gate does at `77218ce` (P-D4, P-D6), not from a rule's ideal. The
fallback: when `<old>` is all zeros or `git cat-file -e "<old>^{commit}"` fails, `--range` reads
`git rev-list <new> --not --remotes`. A force-push after another clone moved the remote hands pre-push a remote
oid the pusher's object store does not hold.

| # | Rule | Given | When | Then | Expected value from |
|---|---|---|---|---|---|
| R4.11 | the fallback reads the unpushed commit | base B pushed; a second clone pushes clean R, never fetched here (`git cat-file -e R` fails); local adds H with `forbidden-token here` at `notes.txt:2` | `git push --force origin main` | non-zero; remote `main` = R; output has `scrub: notes.txt:2: denylist:2` | R4 "an all-zeros `<old>` means every commit not on any remote", extended by the gate at `:177-181` to an `<old>` not in the store; P-D4 "a hit in an unpushed commit is refused" |
| R4.12 | the fallback lets a clean push through | as R4.11; local adds clean `other.txt` instead | `git push --force origin main` | exit 0; remote `main` = the local tip | P-D4 "the fallback keeps its behavior … fails closed (over-scan)" — it scans, it does not refuse; R6.5 |
| R12.5 | the ancestor is now a regular file | committed `a/notes.txt` = `forbidden-token here`; on disk `a/` replaced by a regular file `a` | `--tree` | exit 0; stdout = `scrub: clean` | R12 "a tracked path absent from disk is still skipped"; P-D6 "`a` tracked as a directory, replaced on disk by a regular file → `scrub: clean`, exit 0" |
