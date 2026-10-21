---
paths:
  - "tests/**"
  - "skills/**/scripts/test_*.py"
---

# Tests

- **A security test proves a refusal or a validity.** Show that a value of the wrong shape is
  refused by name, or that what comes out stays well-formed for any input: valid JSON, one argv
  word, an escaped page.
  - Never commit a working payload: no command that would do something if the check failed, and
    no string built to escape a real shell, page or terminal.
  - A fixture that must hold a forbidden construct is syntax only. Its names stay undefined and
    nothing runs it, as in `tests/conventions/test_conventions.py`.
- **Write the behaviour table and the failing tests before the code.** The project hook
  (`.claude/robowright/project.md` → Kind checks, `behavior`) names the `bdd` standard. The suites
  keep the table in `BEHAVIORS.md` beside the test file.
- **Prove each new test can fail.** The project hook → Kind checks, `tests`, names the
  `load-bearing-tests` skill: one compiling mutation per new test that reddens it. Record the
  mutations in the suite's `TEST-LEDGER.md`.
- **Run tests in scratch space.** Use a scratch `$HOME`, scratch roots and scratch repositories.
  Fake `claude` and remote git. Never touch the real `$HOME` or the main clone.
- **Add a new suite to `tests/run.sh` and to the project hook → Tests.** `bash tests/run.sh` must
  end `EXIT=0`.
