# Test ledger — scrub gate

Commit ids in this record refer to the project's history before it was published; they are not in this repository.

Every test in `test_scrub_gate.py` fails under at least one compiling edit to `tools/scrub-gate.sh` or
`tools/hooks/pre-push`. Rows are the `BEHAVIORS.md` ids. Each mutant was one edit, one suite run, then reverted.

| mutant | edit | tests it reddens |
|---|---|---|
| A | pre-push stops after the first stdin line | R6.7, R6.8, H7 |
| B | patterns match case-sensitively | R2.1, H2 |
| C | patterns match as fixed strings, not ERE | R2.2, R2.7, R3.1, R5.2 |
| D | `#` and blank denylist lines are read as patterns | R2.4, R2.5, R2.6, R2.8 |
| E | the default denylist path is misspelled | R3.2, R3.3, R3.4 |
| F | a missing denylist exits 0 | R3.4, R3.5, R3.6, R3.7 |
| G | removed lines are collected as well as added ones | R1.2, R4.3, R4.4 |
| H | rename detection left on | R4.2, R4.7 |
| I | `--cached` diffs the working tree against HEAD | R1.4, R4.1 |
| J | an all-zero `<old>` reads all history, not just commits on no remote | R4.6, R6.4 |
| K | `--range` reads only the tip commit | R4.3, R4.5, R6.1 |
| L | `--tree` also reads untracked files | R4.9 |
| M | `--tree` skips tracked files with uncommitted edits | R4.10 |
| N | each commit's or file's lines overwrite the previous ones | R6.8, H4, H5, H7 |
| P | a run with hits exits 0 | R1.1, R1.3, R1.4, R1.5, R2.1, R2.2, R2.7, R3.1–R3.3, R4.2, R4.3, R4.5, R4.7, R4.8, R4.10, R5.2, R6.1, R6.3, R6.6–R6.8, H1–H7 |
| QR | a clean run prints nothing and exits 1 | R1.2, R1.6, R2.3–R2.6, R2.8, R4.1, R4.4, R4.6, R4.9, R5.1, R6.2, R6.4, R6.5, R6.9 |

## Weakest proofs

R1.3, R1.5, R4.8, R6.3, R6.6, H1, H3 and H6 are reddened only by P, through the exit code rather than the
line number, path or hook wiring each one pins. These edits would pin them more tightly:

- an off-by-one in the hunk header's start line (R1.3, H1)
- a `pre-commit` hook that exits 0 (R1.5)
- word-splitting the file path in `--tree` (H6)

## Gate findings

G1–G4 were written after the four mutation rounds were used. Their kill is the unfixed gate at 9e07a54: all
four failed on the exit code (`0 != 1`) before `LC_ALL=C` was added.

No test reaches the two other parts of the fix:

- `unreadable`, which exits 2 if the collector fails. Under `LC_ALL=C` nothing in the suite makes awk fail, so it
  guards against a future locale or awk regression.
- `grep -a` on the pattern grep. It keeps the output as matching lines if a scanned byte ever makes grep call its
  input binary. BSD grep under `C` did not do this for these inputs.

More mutation rounds would drop `-a` under GNU grep and replace awk with one that exits 1 on read.

G5–G9 come from the second gate review. Their kill is the gate at 73ab83c, before the fix: all five failed on
the exit code (`0 != 1`). The red run shows each row failing without the whole fix. It does not show that each
part is needed on its own: that would take one revert per part, and the mutation ceiling was already spent.

| part of the fix | row written for it |
|---|---|
| the pattern pass under the caller's locale | G5 |
| `--no-textconv` | G6 |
| `--text` | G7 |
| NUL → space before collection | G8 |
| `--tree` no longer skips binary files | G9 |

The NUL → space step in `--tree` has no test. G9 stays green without it, because G9's NUL is on a line of its
own. It guards against a tracked file where a NUL sits before the matching text on the same line: the gate
review verified that without it such a file reads as clean.

## U2 · the denylist line, and file names (R7–R9)

Mutants against `tools/scrub-gate.sh` at 30894de, predictions written first (the session's
`evidence/U2-mutation.md`). Every row whose Then changed to `denylist:<n>` is reddened by U2a or U2g.

| mutant | edit | tests it reddens |
|---|---|---|
| U2a | the denylist line counts only pattern lines | R1.1, R1.3–R1.5, R2.1, R2.2, R2.7, R4.2, R4.3, R4.5, R4.7, R4.8, R4.10, R5.2, R6.1, R6.3, R6.6, R6.8, R7.1, R7.3–R7.5, R8.1–R8.6, H1, H4–H7, G1–G4, G6–G9 |
| U2b | the hit line escape-expands the name (`printf %b`) | R8.1, R8.3 |
| U2c | no newline-name refusal | R9.1–R9.3 |
| U2d | the unusable-pattern line also prints the pattern | R7.4 |
| U2e | a hit also prints its pattern to stderr | R7.1, R7.5 |
| U2f | diff-mode names read without `-z` (quoted by git) | R8.3, R9.2, R9.3 |
| U2g | diff-mode header index off by one (at 30894de; that mapping is gone, see below) | R1.1, R1.3–R1.5, R2.1, R2.2, R2.7, R3.1–R3.3, R4.2, R4.3, R4.5, R4.7, R5.2, R6.1, R6.3, R6.6, R6.8, R7.1–R7.3, R8.3, H1–H3, H5–H7, G1–G3, G5–G8 |
| U2h | the newline count ignored in diff modes | R9.2, R9.3 |
| U2i | `--tree` carries the name in the record through `awk -v` (the design before U2) | R7.5, R8.1, R8.2, R9.1 in `--tree` |
| U2j | `--tree` names read from `git ls-files` without `-z` | R8.1, R8.4, R8.6, R9.1 |
| U2k | the printed name is cut at its first colon | R8.5 |

H8–H10 were written after the implementation, one per rule, and passed on their first run. U2a reddens H8
and H9, U2f H9 and H10, U2c H10.

No test reaches `2> /dev/null` on the pattern grep: dropping it reddens nothing, because this Mac's BSD grep
names the fault (`brackets ([ ]) not balanced`) and not the pattern. It guards against a grep build whose
message quotes part of a pattern, which rule 7 forbids.

G10–G12 come from the first U2 gate review. Their kill is the gate at 3547f1c, before the fix: G10 named
`z.txt:3` for the hit in `m.txt`, G11 named `a-sub:1` for the hit in `z.txt`, G12 exited 2 (`2 != 0`).
The fix diffs each name on its own, so U2g's edit no longer exists to apply. The tests only U2g reddened
among the U2 mutants (R3.1–R3.3, R7.2, H2, H3, G5, all on a one-line denylist) were seen failing on their
name then; the mutation ceiling is spent, and the next edit to run is `denylist_line` counted from 1.

G13 and G14 come from the second U2 gate review. Their kill is the gate at 2715c8b, before the redesign: both
exited 0 (`0 != 1`), the per-name pathspec matching nothing. The redesign reads each diff section's file from
its own `+++ b/` line, so no pathspec, order or count ties a section to a name.

Two flags have no test that fails without them; each guards a user config: `--no-relative` against
`diff.relative=true`, which would narrow the diff to the working directory and shorten names, and
`--submodule=short` against `diff.submodule=diff`, which would scan a submodule's own files as added lines.
Both were checked by hand in a scratch repo with those settings, run from a subdirectory.

## U5 · kills

Written with the U5 spec, before `tools/scrub-gate.sh` changed; each row is the one edit to the U5 gate
that should redden the listed tests. The red baseline is the gate at `be7bf72`: it matches no name, re-reads a relative
denylist after its `cd` (F2), follows links under `--tree` (F3), and exits 1 on a directory denylist (F5).
The rows predicted **green** at `be7bf72` (R10.6, R10.9, R10.11, R11.2, R12.4, R13.1, R13.2, H13, H15, H17,
G16, G18) owe their kill first.

| mutant | edit | tests it should redden |
|---|---|---|
| U5a | `--cached` matches no names | R10.1, R10.4, R10.5, R10.8, R10.10, R10.13, H12, H14 |
| U5b | `--range` matches no names | R10.2, R10.12, H16 |
| U5c | `--tree` matches no names | R10.3, R10.7, H11, G15 |
| U5d | a content hit inside a withheld path prints the name as listed | R10.1–R10.3, H11, G15 |
| U5e | a name hit prints line `1`, not `0` | R10.1–R10.5, R10.7, R10.8, R10.10, R10.12, R10.13, H11, H12, H14, H16, G15 |
| U5f | the `--cached` name list keeps staged deletions (no deletion filter) | R10.9, H13 |
| U5g | the `--cached` name list is every index path (`git ls-files`), not the staged ones | R10.11 |
| U5h | the `--range` name list is every path in each commit's tree (`ls-tree -r`), not the changed ones | R10.6 |
| U5i | the `--range` name list keeps deleted paths | R13.1 |
| U5j | a name is matched one `/`-separated component at a time | R10.13 |
| U5k | names are matched case-sensitively | H12 |
| U5l | only the first matching pattern is reported per name | H14 |
| U5m | names are matched and printed before the newline-name count refuses | H15 |
| U5n | the denylist path is resolved after the `cd` to the toplevel, in every mode | R11.1, G16 |
| U5o | a directory passes the denylist check (`-r` alone, as at `be7bf72`) | R11.3, R11.4, G17 |
| U5p | the refusal line prints the resolved absolute path, not the path as given | R11.2 |
| U5q | the readability check is dropped (existence only) | H17 |
| U5r | `--tree` reads through a symlink to its target (`-f` and `<`, as at `be7bf72`) | R12.1, R12.2, R12.3 |
| U5s | `--tree` refuses (exit 2) on a tracked path absent from disk instead of skipping it | R12.4 |
| U5t | `--range` also matches each commit's message | R13.2 |
| U5u | `--cached` skips symlink entries (mode `120000`) | G18 |
| U5v | `--tree`'s `cat` keeps its own stderr (the gate at `0e47356`) | H18 — killed: red at `0e47356`, green with the redirect |
| U5w | the tools the gate runs keep their own stderr (the gate at `433e11d`, no `exec … 2> /dev/null`) | H19, H20 — killed: red at `433e11d`, green with the redirect. H18's protection moved to the same line; not re-run against it (the four-round ceiling) |

| U5x | `--tree` skips any tracked path that is neither a link nor a file (the gate at `b6b8ec4`) | H21 — killed: red at `b6b8ec4` (`0 != 2`), green with `is_absent` |

Mutant F above (a missing denylist exits 0) should also redden R11.2.

Run against the gate at `0e47356`, four batches of four: U5a+U5b (one edit, both modes), U5c–U5i, U5m–U5o,
U5q–U5u each **killed** exactly its row's tests. U5p ran as "the refusal line drops the path", killing
R11.2 and four R3 rows. U5j, U5k and U5l were not run (the four-round ceiling); R10.13, H12 and H14 were
each killed by U5a and U5e. Every U5 test is killed; none is declared.

No test reaches `is_absent`'s branch for an ancestor that is now a file (the path is absent, skipped). It guards
a tree changed on disk since it was staged; the end-of-stack review checked it by hand. R12.4 reaches the
top-level-name branch.

## Polish P1 · every refusal says why

| id | mutation | killed |
|---|---|---|
| P1a | the `mktemp` reason line reworded | R14.1 |
| P1b | the `rev-list` reason line reworded | R14.2 |
| P1c | the `ls-files` reason line reworded | R14.3 |
| P1d | the `cd` reason line reworded | R14.4 |
| P1e | the trap refuses only on a status above 2 (the brief's literal discriminator) | R14.5 |
| P1f | the trap no longer removes `$work` | H23 |
| P1g | the hit exit no longer sets `verdict` | every exit-1 hit row (67 tests); no R14 row |
| P1h | the trap line no longer clears `work` (the gate at `01f281e`) | H24 — killed: red at `01f281e`, green with the clear |
| P1i | the trap line no longer clears `verdict` (the gate at `01f281e`) | H25 — killed: red at `01f281e` (`1 != 2`), green with the clear |

Three rounds: P1a–P1d, P1e+P1f, P1g over the whole suite. Each killed exactly its predicted tests. H24 and H25
are the gate review's regression tests, red on the unfixed gate. Every P1 test is killed; none is declared.
H22 (`--cached` with the same bash error) is deleted: the error fires at the `$HOME` read, before the mode
dispatch, so it never reached the index mode and could not fail apart from R14.5.

## Polish P2 · the fallback, the ancestor that is a file, H18 at the exec line

| id | mutation | killed |
|---|---|---|
| P2a | `scan_range` drops `\|\| ! git cat-file -e "$old^{commit}"`: an `<old>` the store lacks becomes `^<old>` | R4.11 (no hit line, the rev-list refusal instead), R4.12 (push refused) |
| P2b | `is_absent`'s `[[ ! -d "$path" \|\| -x "$path" ]]` → `[[ -x "$path" ]]` | R12.5 (`2 != 0`) |
| P2c | the exec line keeps stderr: `exec 3>&2` without `2> /dev/null` (P-D5, re-running U5w against the line that carries H18 now) | H18, H19, H20, and the rows that assert stderr exactly: R14.1–R14.5, H25 |

Two rounds over the whole suite: P2a+P2b, then P2c. Each killed exactly its predicted tests
(`Ran 130 tests`, `failures=3`, then `failures=10`, with H22 still in the suite). `is_absent`'s ancestor-is-a-file branch now has a test (R12.5).
