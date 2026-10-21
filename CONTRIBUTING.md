# Contributing

Pull requests are welcome. Support is best effort: a change is read when the maintainer has time,
with no promise of when. There are no issue or pull-request templates; say what the change does
and why.

## The bar

`bash tests/run.sh` from the repository root prints one line per suite and ends `EXIT=0`. There is
no CI, so that run is the only verification. A change that adds behaviour to a script adds
the test that proves it, in that script's suite.

## Wire the scrub gate first

```sh
git config core.hooksPath tools/hooks
```

Git does not clone hooks, so each clone opts in. Then the conventions lint runs at every commit
(see Security conventions), and `tools/scrub-gate.sh` runs at every commit and push, refusing an
added line that matches your install's pattern list at
`${ROBOWRIGHT_DENYLIST:-~/.config/robowright/denylist}`. Those patterns are your own names, the
ones that must never leave your machine; `/robowright-onboard` creates the file with no patterns. The
maintainer's own gate and review guard against a name in your change, never your list, so nobody
asks you to add a pattern for them.

## Security conventions

The launcher, `accept.sh`, the hooks and the dashboard read files a session wrote, outside the
sandbox. The rules for that code live in [`.claude/rules/`](.claude/rules/); Claude Code loads each
one when you read or edit a file it covers, and they read as well by hand:

- [`session-inputs.md`](.claude/rules/session-inputs.md): shape checks, JSON, arithmetic, git
  through `owner_git.py`, no shell built from data;
- [`dashboard.md`](.claude/rules/dashboard.md): escaping, the Host check, loopback, GET-only;
- [`public-content.md`](.claude/rules/public-content.md): invented examples, no real values;
- [`tests.md`](.claude/rules/tests.md): refusals and validity checks, never a working payload.

[`SECURITY.md`](SECURITY.md) lists every session-written value and its check. A value you add gets
a row there.

The maintainer signs every tip of `main` when a change is accepted; the commits in your pull request
need not be signed.

`tests/conventions/lint.py` enforces the code rules, and `tests/run.sh` runs its suite. The
pre-commit hook runs the scrub gate, then the lint, on the staged tree; if either finds something,
the commit is refused with a `pre-commit: refused by ...` line naming which. A commit whose staged
tree has no lint, such as one that deletes it, skips the lint and says so; `tests/run.sh` and
review still catch that.

When the lint flags a safe site, add one tab-separated line to `tests/conventions/allowlist.txt`:

```
<check>	<path>	<why this site is safe>	<the source line, trimmed, as the lint printed it>
```

One entry clears one site. An entry without a reason is refused, and one that no longer matches a
site fails the run. Fix the site instead whenever you can.

## Commits

Subject `<area>: <what changed>`, lowercase, no period: `gate: refuse a commit whose added lines
match the denylist`, `tests: the runner`. The body says why.

## Conventions a change must keep

- A skill that only a person or the launcher invokes, never a model on its own judgment, carries
  `disable-model-invocation: true` in its frontmatter. `review-overlay`, `robowright-onboard`,
  `spend-debug` and `one-off` do today. `worker` does not: in the desktop app the Lead starts each
  unit as a background task, which is a model invocation, so its description limits it to a prompt
  naming a session directory instead.
- A fact about one machine goes in its machine profile, one about a repository in its project
  hook, and one about a toolchain in its platform plugin; the handbooks name the section, never the
  fact (`skills/robowright/SKILL.md`, "Three layers, and where a new fact goes").
- History lives in `CHANGELOG.md`; a change still explains itself in its commit body and change
  description.
- Nothing here names a real person, employer, machine path or private repository. Examples use the
  invented `sample` vocabulary of `examples/laptop/`.
