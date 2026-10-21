platform: web

# Platform plugin — Web (a static site, served and read in a browser)

What is true of building, testing and observing a static web app, in any repository. The project
hook names the commands, paths, launch entries and its own gate script; this file says what their
output, device and lock mean. Written against `../PLUGIN-CONTRACT.md`.

## 0. Identity

| | |
|---|---|
| Toolchain | No compiler and no bundler assumed: a static site of HTML/CSS/JS served as-is, and a browser to read it |
| Last verified against | Not recorded |
| Base | None — this plugin is a base |

## 1. Verdict shapes

**Build.** None on this platform — a static site has no build step; "build" is serving the
files. The hook names its own local-server command.

**Test run.** There is no test runner for a static site. The gate is whatever the hook names —
typically a doc or link checker plus evidence that the changed page renders — read for its own
exit code, `0` green. The count-based traps a compiled-language plugin warns about (a filter
selecting zero tests, a marker line with no count behind it) do not apply here: there is no test
count to under-select. **Reading it — the one sanctioned way.** The reading command the hook
names, else the `log-reader` agent with the log's path.

- **Cadence.** A whole-target run is owed at the brief's `whole_suite_runs_owed` points, and
  only when a source file (the hook's patterns) changed since the last one; otherwise cite the
  previous run's log.

## 2. Hang shape

None on this platform. Serving static files and reading a page have no long-running compile or
test step to hang; a local server that never starts is an infrastructure failure (→ 3), not a
hang.

## 3. Infrastructure-failure shapes

None of these is a verdict; each is retried or reported as itself.

| Shape | What the session does |
|---|---|
| The local server never starts, or the port is already bound | Retry once before anything else; a second failure is `infra` (Worker handbook, unit-loop step 4) |
| A remote fetch to verify a rendered page times out or refuses | Control check: the same request against the predecessor's rendered page. Fails there too → `infra`, not the unit's red |

## 4. Device model

**No device.** The environment is a browser reading a locally served copy of the site: the hook
names its local-server command and port. There is nothing to lease, install onto, or reset
between runs — starting the server and re-requesting the page is the whole setup.

- **Read the rendered page**, not a build artifact: fetch it (or open it) and read the markup and
  any console output for the change under test. The hook names its own reading tool and any
  request quirks its environment or its target needs.

## 5. `device: {}` schema

None on this platform. There is no leased device to record in `run.json`.

## 6. Lock name and liveness rule

None on this platform. A locally served static site takes no machine-wide lock: nothing here
contends for a shared simulator or emulator the way a mobile toolchain's device does.

## 7. Kind → check table

| Kind | Check | Rule it enforces |
|---|---|---|
| `tests` | None on this platform. A static site has no test suite to prove a kill against; the hook's own gate script (→ 1) is the check | — |
| `behavior` | A change that reaches a screen owes the `ui` row | — |
| `ui` | Read the rendered page (→ 4): the hook's predicates over the markup as the assertion, a screenshot as the record, the oracle written before the read | A predicate is the check; `blocked` and `unverified` are reported as themselves |
| `refactor` | None on this platform. The hook names a move-equivalence check where it has one | — |
| `docs` | None on this platform | — |

## 8. Sweep method

**Eyeball diff, advisory.** No device and no automated pixel comparison: read the rendered page
against a known-good reference (a prior deployment, or the base build served the same way) and
diff by eye. This never gates — its output is findings for the handoff, the same standing rule as
an exploratory sweep on any other toolchain: a difference nobody can explain is a finding, never
waved through. The hook names its own cache-busting or asset-versioning convention, where it has
one, as a check on top of this.
