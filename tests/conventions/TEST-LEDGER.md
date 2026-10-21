# conventions lint — test ledger

Commit ids in this record refer to the project's history before it was published; they are not in this repository.

2026-10-14. 17 tests written from `BEHAVIORS.md` against a skeleton `lint.py` that checks nothing:
the ten finding rows (C1–C8, A2, A3) failed on their assertion, and the twins, A1 and T1 passed,
so those seven owed a kill. The implementation was written with no Given, When or Then edited.

The first adversarial review found evasions, and nine more rows came of it (C2b, C4b, C5b, C6b,
C7b, C8b, C8c, A4, A5). All nine failed on their assertion before the fix. One Given changed
before the fix landed: C8b's helper call moved to its own line, so it no longer shared a finding
with `max(names)` (M23 below found this).

The second review found more evasions and two regressions in the first round's fixes, and four
more rows came of it (C5c, C5d, C7c, C8d). C5c, C7c and C8d failed on their assertion before the
fix; C5d, a twin, passed and owes its kill. C8b was split to one case per line, because the review
showed that undoing either the `%` fix or the template fix left it green. C8d's Then lost a call-site
line before the fix landed: a nested helper is flagged where it is written, not at its calls.

The third review found that the heredoc tracker added for C5c switched checks off for the rest of
a file and misread quoted heredocs, and that the shell JSON check (failing review for the third time)
and the raw-git pattern still missed ordinary forms. Both shell checks were rebuilt on one reader
that takes a script whole as shell words, `$( )` included. Heredoc tracking was dropped, and JSON
over several lines became a stated limit. So C5c lost its heredoc line and C5d lost its literal
heredoc, before the fix landed; C5d gained the `$( )` case that review found flagged in error, and
C7d and C7e were added. C5d and C7d failed on their assertion first; C7e, a twin, passed and owes its
kill.

The fourth review found that the reader lost its quote state on a backslash inside `$( )` and on an
apostrophe in a heredoc body, so the checks went blind for the rest of the file, and that it missed
git in backticks inside double quotes and after a `\` line continuation. Heredoc bodies are now read
apart from shell: an expanding body line by line for JSON, a quoted one not at all. C5e and C7f
failed on their assertion before the fix. C7f's heredoc turned out to hold two apostrophes, which
pair, so it never needed the heredoc fix (M42 left it green); C7g, written after the fix with one
apostrophe, owes its kill and has it in M42. C5c passed at red in the third round with its heredoc
line gone; its kill is M29.

The fifth review found the heredoc fix reached only the top level: a heredoc inside `$( )` was still
read as code, so an apostrophe in a commit message opened a quote that blinded the rest of the file;
and a command inside an expanding heredoc body was no longer read. The `$( )` end is now where the
reader itself stops, so one reader handles quotes, escapes and heredocs at every depth, and an
expanding body's `$( )` and backtick commands are read. C7h and C7i failed on their assertion before
the fix. C7j, written after it, owes its kills and has them in M46 and M47. Tracking nested
parentheses inside `$( )` survived its mutation and was removed, on the reasoning that closing early
leaves the rest to the enclosing reader.

The sixth review showed that reasoning holds only outside quotes: inside `"$( )"`, a process
substitution, subshell or `$(( ))` ended the substitution early and the rest was read as string
text, losing words or blinding the file. The depth count is back, and C7k, which failed on its
assertion first, is its kill (M39).

One mutation per test, each applied alone to `lint.py` and reverted, with the kill set predicted
before the run.

| # | Mutation | Predicted to fail | Observed | Verdict |
|---|---|---|---|---|
| M1 | `k.arg == "shell"` → `k.arg == "shel"` | A1, A4, A5, C1 | observed ['A1', 'A4', 'C1'] | KILLED |
| M2 | `func.value.id == "os" and func.attr in ("system", "popen")` → `func.value.id == "os" and func.attr in ("popen",)` | C2 | same | KILLED |
| M3 | `func.id == "eval"` → `func.id == "evil"` | C3 | same | KILLED |
| M4 | `re.fullmatch(r"-[A-Za-z]*c[A-Za-z]*", elt.value)` → `elt.value == "-e"` | C4, C4b, T1 | same | KILLED |
| M5 | `and not ( isinstance(nxt, ast.Constant)` → `and not (False and isinstance(nxt, ast.Constant)` | C4a | same | KILLED |
| M6 | `PRINTF_JSON.search(line) or` → `False or` | C5 | same | KILLED |
| M7 | `word.startswith('"')` → `True` | C5a, T1 | observed ['C5a', 'C5d', 'T1'] | KILLED |
| M8 | `if is_hook and any(` → `if False and any(` | C6, T1 | observed ['C6', 'C6b', 'T1'] | KILLED |
| M9 | `if is_hook and any(` → `if True and any(` | C6a, T1 | same | KILLED |
| M10 | `if rel in OWNER_SIDE and command_word(elts[0], constants) == "git"` → `if rel not in OWNER_SIDE and command_word(elts[0], constants) == "git"` | C7, C7b, T1 | same | KILLED |
| M12 | `if line is not None:` → `if False:` | C8, C8b, T1 | observed ['C8', 'C8b', 'C8d', 'T1'] | KILLED |
| M13 | `SAFE_CALLS = {"e",` → `SAFE_CALLS = {` | C8a, C8b, T1 | observed ['C8a', 'T1'] | KILLED |
| M14 | `(e[1], e[2], e[3]) == (check, rel, source)` → `(e[1], e[2], e[3]) == (check, rel, source + " ")` | A1, A4, T1 | observed ['A1', 'T1'] | KILLED |
| M15 | `if not reason.strip():` → `if False:` | A2 | same | KILLED |
| M16 | `for e in entries if e[0] not in used]` → `for e in entries if False]` | A3 | observed ['A3', 'A5'] | KILLED |
| M18 | `(func.value.id == "subprocess" and func.attr in ("getoutput", "getstatusoutput"))` → `False` | C2b | same | KILLED |
| M19 | `if command_word(elts[0], constants) == "env":` → `if False:` | C4b | same | KILLED |
| M21 | `(?<!\$)\(\(` → `(?:^\|[\s;&\|!])\(\(` | C6b | same | KILLED |
| M23 | `if not (isinstance(node.func, ast.Name) and node.func.id in self.raw):` → `if True:` | C8b, T1 | observed ['C8b', 'C8d', 'T1'] | KILLED |
| M24 | `and fn.name in self.called:` → `:` | C8 | observed ['C8', 'C8b', 'C8d'] | KILLED |
| M25 | `params = self.params(fn) if self.safe(value, fn, bound \| params):` → `params = self.params(fn) if False:` | C8c, T1 | observed ['C8b', 'C8c', 'C8d', 'T1'] | KILLED |
| M26 | `and e[0] not in used]` → `]` | A4 | observed ['A4', 'T1'] | KILLED |
| M27 | `used.add(match[0][0])` → `used.update(e[0] for e in match)` | A5 | observed ['A5', 'T1'] | KILLED |
| M28 | `any(JSON_KEY.search(word) and expands for word` → `False and any(JSON_KEY.search(word) and expands for word` | C5b, C5c | observed ['C5', 'C5b', 'C5c', 'C5e'] | KILLED |
| M30 | `JSON_KEY.search(word) and expands for word` → `JSON_KEY.search(word) for word` | C5d | observed ['C5d', 'T1'] | KILLED |
| M32 | `for a in [*node.args, *(k.value for k in node.keywords)])` → `for a in node.args)` | C8d | same | KILLED |
| M33 | `self.functions.get(fn.name) is fn and fn.name in self.called` → `fn.name in self.called` | C8d | same | KILLED |
| M34 | `(positional[i] in raw if i < len(positional) else star)` → `(positional[i] in raw if i < len(positional) else False)` | C8d | same | KILLED |
| M35 | `not isinstance(node.op, (ast.Add, ast.Mod))` → `not isinstance(node.op, ast.Add)` | C8b | same | KILLED |
| M36 | `if isinstance(node, ast.Name): node = self.constants.get(node.id) return isinstance(node, ast.Constant) and isinstance(node.value, str) and self.is_html` → `return isinstance(node, ast.Constant) and isinstance(node.value, str) and self.is_html` | C8b | same | KILLED |
| M11 | `if rel in OWNER_SIDE and any(word ==` → `if any(word ==` | C7a, T1 | same | KILLED |
| M17 | `elif c in " \t\n;\|&<>()":` → `elif c in " \t;\|&<>()":` | T1 | observed ['C5b', 'C5c', 'C5d', 'C7f', 'C7h', 'C7k', 'T1'] | KILLED |
| M22 | `any(word == "git" or word.endswith("/git")` → `any(word == "gitx" or word.endswith("/gitx")` | C7, C7b, C7c, C7d | observed ['C7', 'C7b', 'C7c', 'C7d', 'C7f', 'C7g', 'C7h', 'C7i', 'C7j', 'C7k', 'T1'] | KILLED |
| M41 | `elif c == "\\" and text[i + 1:i + 2] == "\n" and not quote:` → `elif False:` | C7f | same | KILLED |
| M42 | `elif c == "<" and text[i:i + 3] != "<<<"` → `elif False and c == "<"` | C5e, C7g | observed ['C5e', 'C7g', 'C7h', 'C7i', 'C7j'] | KILLED |
| M43 | `if expanding:` → `if False:` | C5e | observed ['C5e', 'C7i', 'C7j'] | KILLED |
| M44 | `line += len(lines) + 1` → `line += len(lines)` | C7f | observed ['C7f', 'C7g', 'C7h', 'T1'] | KILLED |
| M37 | `elif c == "#" and not word:` → `elif False:` | C7e | observed ['C7e', 'T1'] | KILLED |
| M29 | `words.extend(inner) word, expands = word + "$()", True` → `word, expands = word + "$()", True` | C5c, C7, C7f | observed ['C5c', 'C7', 'C7f', 'C7k'] | KILLED |
| M31 | `elif c == "$" and text[i + 1:i + 2] == "(" and text[i + 2:i + 3] != "(": inner, i, line` → `elif False: inner, i, line` | C5d | observed ['C5d', 'C7k'] | KILLED |
| M38 | `elif c == ")" and inside and depth == 0:` → `elif c == ")" and False:` | C7f, C7h, T1 | observed ['C7f', 'C7h', 'C7k', 'T1'] | KILLED |
| M40 | `` elif c == "`": end = backtick_end(text, i) `` → `elif False: end = backtick_end(text, i)` | C7c, C7f | same | KILLED |
| M45 | `inner, j, _ = read_shell(text, j + 2, number, True) words.extend(inner)` → `inner, j, _ = read_shell(text, j + 2, number, True)` | C7i | same | KILLED |
| M46 | `` elif text[j] == "`": `` → `elif False:` | C7j | same | KILLED |
| M47 | `if text[j] == "\\": j += 2` → `if text[j] == "\\": j += 1` | C7j | same | KILLED |
| M39 | `depth += (c == "(") - (c == ")")` → `depth += 0` | C7k | same | KILLED |

No survivors, no tests deleted. Every test has a kill of its own. The missed predictions:
- M1: A5 stays green. With no `shell-true` finding at all, both entries go stale and the line it
  asserts is still printed.
- M7 and M30: C5d reddens alongside C5a, and T1 alongside C5d; each is the same jq filter path.
- M8: C6b reddens too; it is the same hook check.
- M12, M23, M24 and M25: C8b and C8d redden too; they share the dashboard paths each mutation
  breaks.
- M13 and M14: C8b and A4 hold, since each has a finding the mutation does not touch.
- M16: A5 reddens; it asserts a stale line.
- M26 and M27: T1 reddens, because the tree's two identical `bash -n -c` entries now pair one to
  one.
- M28: C5 and C5e redden too; their lines are caught by the same word check.
- M17: C5b, C5c, C5d, C7f, C7h and C7k redden too; with no newline separator, words run across lines.
- M29 and M31: C7k reddens too; its git calls sit inside `$( )`.
- M22: every raw-git row with a git line reddens, and T1, whose `git` allowlist entries go stale.
- M37: T1 reddens; a comment's `git` shows.
- M42: C7h, C7i and C7j redden too; each needs its heredoc read as a heredoc.
- M43: C7i and C7j redden too; their bodies expand. C7h's is quoted.
- M38: C7f, C7h and C7k redden, and T1; a `$( )` that never closes swallows the lines after it.
- M44: C7g, C7h and T1 redden too; every line after a heredoc is off by one, in the tree as well.

C4a, C5a, C5d, C6a, C7a, C7e, C8a and C8c are the twins that keep a check from flagging everything.

## The session-write check (C9)

2026-10-15. C9 was red on `ece9986`, before the check existed. One mutation: the `session-write` yield
replaced by `pass` reddens C9 alone. The negative half of C9 (`>/dev/null`, `2>&1`, `>&2`, a script
outside the hooks and the launcher) and T1 over this tree keep the check from flagging everything.

## The pre-commit hook

The Owner asked for the lint on every commit, so `tools/hooks/pre-commit` runs the scrub gate and
then the lint on the index, exported to a scratch directory. H1–H5 were written first against the
old hook, which only ran the scrub gate: H1, H3, H4 and H5 failed on their assertion
(`evidence/red-precommit.log`), and H2, the twin, passed and owes its kill. H6 was written after the
hook and owes its kill. One mutation per behaviour, applied to the hook alone and reverted; P7 is
judged by the scrub-gate suite, whose scratch repositories carry no lint and so take the skip.

| # | Mutation | Predicted to fail | Observed | Verdict |
|---|---|---|---|---|
| P1 | `echo "pre-commit: refused by the conventions lint" >&2 status=1` → `echo "pre-commit: refused by the conventions lint" >&2` | H1, H3, H4 | observed ['H1', 'H3', 'H7'] | KILLED |
| P2 | `--root="$staged"` → `--root="$top"` | H3 | same | KILLED |
| P3 | `echo "pre-commit: refused by the scrub gate" >&2 status=1` → `echo "pre-commit: refused by the scrub gate" >&2` | H5 | same | KILLED |
| P4 | `exit "$status"` → `exit 1` | H2, H3, H6 | same | KILLED |
| P5 | `echo "pre-commit: refused by the scrub gate" >&2` → (deleted) | H4, H5 | same | KILLED |
| P6 | `--allowlist="$staged/tests/conventions/allowlist.txt"` → `--allowlist="$top/tests/conventions/allowlist.txt"` | H6 | same | KILLED |
| P7 | `echo "pre-commit: no tests/conventions/lint.py staged; the conventions lint is skipped" >&2` → `echo "pre-commit: no tests/conventions/lint.py staged; the conventions lint is skipped" >&2 status=1` | the scrub-gate suite | 1 scrub-gate test | KILLED |
| P8 | `-a --ignore-skip-worktree-bits --prefix` → `-a --prefix` | H7 | same | KILLED |

All killed. P1's missed prediction: H4 stays refused, by the scrub gate, and both refusal lines
still print; H7 reddens, as it is another lint refusal.

The eighth review found that `checkout-index -a` leaves out skip-worktree entries, so a staged
finding on one was never linted. H7 failed on its assertion before the fix (`evidence/red-review-8.log`);
P8 is its kill. Two parts of the hook have no row: the scratch directory under `${TMPDIR:-/tmp}`,
which matches the scrub gate and guards against a sandbox that can write only there, and running the
staged `lint.py` rather than the working tree's, which the ask does not require. Both are declared,
not tested.
