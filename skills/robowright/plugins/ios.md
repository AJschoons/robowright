platform: ios

# Platform plugin — iOS (Xcode, `xcodebuild`, the iOS Simulator)

What is true of building, testing and observing an iOS app with Xcode, in any repository. The
project hook names the commands, paths, scheme, bundle id, simulator pin and scripts; this file
says what their output, device and lock mean. Written against `../PLUGIN-CONTRACT.md`.

## 0. Identity

| | |
|---|---|
| Toolchain | Xcode (`xcodebuild`, `xcrun simctl`, `xcrun xcresulttool`), XCTest and Swift Testing, the iOS Simulator, `axe` for the accessibility tree. A brief may also pick XcodeBuildMCP (`xcodebuildmcp`) from the approved MCP list (`../mcp/README.md`); it drives the same `xcodebuild` and simulator through `build_sim`, `test_sim` and `snapshot_ui` |
| Last verified against | Xcode 27.0 (27A266a); `xcresulttool get test-results summary` schema 0.4.0; XcodeBuildMCP 2.7.0 in a `claude --bg` Worker (a spike run; its evidence is not in this repository) |
| Base | None — this plugin is a base |

## 1. Verdict shapes

**Build.** The verdict is two things together: the `** BUILD SUCCEEDED **` or
`** BUILD FAILED **` line, and `xcodebuild`'s exit code. The compiler's `error:` lines are the
detail behind a red, never the verdict. `xcodebuild build` does not compile a test target; a
unit that only adds tests is verified by its test run, and `build-for-testing` is the command
that compiles the tests.

**Test run.** The verdict is three things together, all quoted:

1. the `** TEST SUCCEEDED **` or `** TEST FAILED **` marker line,
2. the exit code — `0` green, `65` the usual red,
3. the six-field summary dict of the run's result bundle — `result`, `totalTestCount`,
   `passedTests`, `failedTests`, `skippedTests`, `expectedFailures` — quoted whole.

The marker line is read from the redirected log, not the console. A hook whose gate command
prints only the exit code and the summary dict satisfies item 1 by naming the log that command
wrote.

The marker line alone is not a verdict: an `-only-testing:` path with a typo selects **zero**
tests, prints a clean marker line and exits `0`. The count is what catches it — `totalTestCount`
above zero, and equal to the count the brief expects when it names one. A repository whose
reading script emits only the marker line and the exit code reads the verdict incompletely
against this plugin until that script also reports the counts.

The dict comes from the result bundle, never from stdout:

```sh
rm -rf <bundle>.xcresult    # xcodebuild refuses an existing bundle (exit 64); a reader would take the stale one as this run's
xcodebuild test … -resultBundlePath <bundle>.xcresult > <log> 2>&1
xcrun xcresulttool get test-results summary --path <bundle>.xcresult --compact
```

**Reading it — the one sanctioned way.** The reading command the hook names (a script or the
`xcresulttool` query above), else the `log-reader` agent with the log's path. The log stays out
of the session's context: a question the reading command cannot answer goes to `log-reader`.

**An MCP build or test** (`build_sim` and `test_sim` are the calls measured) is an iOS build: the
verdict rules above hold and are read from different places. The response is XcodeBuildMCP's own
summary (`status`, `counts`) and is never the verdict.

- **No exit code exists.** A failure arrives as an MCP error result, not as `status: FAILED`. The
  error result stands in for the exit code, and is quoted.
- **Build:** `log-reader` on the response's `artifacts.buildLogPath`, for the `** BUILD SUCCEEDED **`
  or `** BUILD FAILED **` line.
- **Test:** item 1 is the log's two marker lines (next bullet), item 2 is the MCP error result or
  its absence, and item 3 is the six-field dict of `xcrun xcresulttool get test-results summary
  --path <xcresultPath> --compact`, for the `xcresultPath` the response returns. `totalTestCount`
  is the count of record: the response's `testCases` omitted a Swift Testing test the bundle
  counted. A bundle with `"result":"unknown"` and `"totalTestCount":0` is the zero-test shape.
- **The log's marker lines differ.** `test_sim` builds for testing, then runs without building, so
  its log carries `** TEST BUILD SUCCEEDED **` and `** TEST EXECUTE SUCCEEDED **`, never
  `** TEST SUCCEEDED **`. A log with the build marker and no execute marker did not run its tests.
  Name both patterns to `log-reader`: asked for "the verdict lines" it looks for
  `** TEST SUCCEEDED **` and runs out of turns.
- **No `xcresultPath` in the response is red**, and the MCP error result plus `log-reader` on the
  log it names are the record. Example: a scheme name xcodebuild does not know fails before it builds.

Traps that change what a verdict means:

- **The masked pipe.** `xcodebuild … | grep …` then `$?` reads the filter's status; even under
  `set -o pipefail` it returns grep's `1`, not `xcodebuild`'s `65`. Capture the exit code
  directly after `xcodebuild`, before any filter runs. A red gate has been reported green this
  way. Where `xcodebuild` is in `sandbox.excludedCommands`, run it bare with
  `run_in_background: true`: the task's output file is the log and the completion notification
  carries the exit code. The exclusion applies only when the whole command matches, so a
  `> log` redirect, a pipe, a `VAR=` prefix or a chain keeps `xcodebuild` sandboxed, where
  SwiftPM fails with `sandbox_apply: Operation not permitted`. Outside a sandbox, redirect to a
  file and read `$?` on the next statement.
- **Expected failures.** A `withKnownIssue` test lands in `expectedFailures`, not `passedTests`,
  so a green total is passed + failed + skipped + expected failures. A total that "grew" is
  usually this.
- **Two runners in one target.** In a target mixing XCTest and Swift Testing, the XCTest half
  ends with `Executed N tests`, then `◇ Test run started.` begins the Swift Testing half. Each
  half's count is its own; read neither as the whole run's count.
- **A crashed test host** reads like an ordinary failure with a lower count than the last gate.
  Compare `totalTestCount` against the last green run before reading the failures.
- **Cadence.** A whole-target run is owed at the brief's `whole_suite_runs_owed` points, and
  only when a source file (the hook's patterns) changed since the last one; otherwise cite the
  previous run's log.

## 2. Hang shape

A hang has no marker line and no exit code, and the log stops growing. In Swift Testing output
the tell is a trailing `◇` (a test started) with no matching result line after it.

- Start every test run and any build over a minute in the background; watch the log's size, not
  the clock alone.
- **Threshold: the hook's, else 300 s with no log growth.** This plugin sets the default; a
  link or one long test can be quiet for a minute or two, so a tighter number belongs to a hook
  that has measured its own runs. Past it, kill the background task.
- An MCP build or test is a blocking tool call, not a background task, and its log path arrives
  only in the response. The spike measured no hung MCP call, so no hang shape is written for one.
- Re-run once, with the hook's known-bad suite excluded through `-skip-testing:` where the hook
  names one, else unchanged.
  Twice hung is a gate failure, reported as a hang: a hang is not a verdict and not a red
  (Worker handbook, rule 3 and unit-loop step 4).

## 3. Infrastructure-failure shapes

None of these is a verdict; each is retried or reported as itself.

| Shape | What the session does |
|---|---|
| The test runner never attached: it ran nothing | Retry once before anything else; a second failure is `infra` (Worker handbook, unit-loop step 4) |
| A signal kill, or a simulator shut down mid-run — fails exactly like broken code | Control run: the same command on the predecessor head. Red there too → `infra`, not the unit's red |
| CoreSimulatorService down (every `simctl` call fails, across sessions) — concurrent `simctl` calls cause it | Stop issuing `simctl`; one `simctl` call at a time on the machine. Report `infra` |

## 4. Device model

An **iOS simulator**, leased by **UDID**.

- **Destination `id=<UDID>`, always.** Two installed runtimes can ship a device of the same name,
  and a `name=` destination picks whichever the list yields first. The hook names the pinned
  device and runtime; a script that resolves a name to a UDID prints the UDID for `id=`.
- **Starting state.** The hook names its setup — install, privacy grants, location, status-bar
  override, appearance, content size, Reduce Motion — built from `xcrun simctl` subcommands, run
  once per installed build. `simctl privacy` terminates the target app if it is running, so
  grants precede sign-in and any launch the setup depends on. A session that changes a device-wide setting (content size above
  all) restores the hook's baseline before handoff: off-screen renders inherit the simulator's
  live settings, so a device left at an accessibility size redefines "default" for everything
  recorded after it.
- **Drive it** through the iOS Simulator control tool — `attach` first, then build, install,
  launch — or `xcrun simctl install` / `launch` with the hook's bundle id, and `axe tap --id <id>`.
  That tool belongs to an attended desktop session. An unattended Worker whose brief picks
  `xcodebuildmcp` (`run.json.mcp`) drives through it, and `axe` through Bash is the fallback.
  - **The first call is `session_set_defaults`** with `simulatorId` set to `device.udid` (and
    `bundleId`, `workspacePath` and `scheme` where the calls need them). A fresh server has no
    defaults. Leave `persist` unset (`../mcp/README.md`, Entries).
  - **`snapshot_ui` is read inline.** Its response was under 1.5 KB in the spike (846 and 1,483
    bytes), a fraction of an `axe describe-ui` tree, so it needs no `ui-tree-reader`: `screenHash`,
    `count` and `targets` such as `e10|tap|button|Enter||`. `tap {elementRef}` returns the post-tap
    capture in its own response.
  - **Allow rules** are the brief's to set (`../mcp/README.md`, A brief's pick); the entry's
    default covers every tool of the workflows the brief picked.
- **Read the tree, not the picture.** `axe describe-ui --udid <UDID> > evidence/<unit>-<screen>.tree.json`
  is the observation (through `xcodebuildmcp`, the `snapshot_ui` response saved to
  `evidence/<unit>-<screen>.snapshot.json` is); an accessibility-tree predicate over that file is the assertion; `xcrun
  simctl io <UDID> screenshot evidence/<unit>-<screen>.png` is the record, opened only to
  sanity-check layout. A tree is 600 KB and more: questions a predicate cannot answer ("which
  screen is this", "which ids match") go to the `ui-tree-reader` agent with the `.tree.json` path.
- **Before writing an oracle**, ask `ui-tree-reader` whether the element carries an
  accessibility node at all. An element without one makes the predicate `blocked` before it is
  written.
- **`Multiple (N) matched`** on a tap: resolve to one element's frame and tap its point.

**The lease.** The session claims one simulator before its first build, records its UDID in
`device.udid`, and releases it at handoff and on an early stop. The hook names the mechanism —
a simulator pool's lease, or a pinned device behind the `ios-build` lock (→ 6). A failed claim
is a stop with `verification-failed` naming the reason; a session never borrows another
session's UDID.

**Build output.** Two DerivedData shapes are both correct Xcode; the hook names the one its
commands use:

- **Xcode's default path** — a per-project folder in Xcode's DerivedData directory, named for the
  project plus a hash of the project's absolute path, so every worktree already gets its own
  folder with no `-derivedDataPath`. `xcodebuild -showBuildSettings` prints the resolved `BUILD_DIR`: run
  it in text form, not `-json`, redirected to an evidence file, then `grep -m1 ' BUILD_DIR = '`
  on that file — two calls. The `-json` form prints concatenated documents that `json.load`
  refuses with `Extra data`.
- **An explicit `-derivedDataPath`** on every call, computed by the repository's worktree
  script, where submodules or a shared cache need a path the default hash does not give.

Either way, the resolved folder goes in `run.json.build_output` at preflight.

**Build setting trap.** `SWIFT_STRICT_CONCURRENCY` is a project build setting, never an
`xcodebuild` command-line override: on the command line it reaches every Swift Package target,
including those that never opted in, and they fail to compile.

## 5. `device: {}` schema

```json
{"udid": "…", "os": "iOS 26"}
```

| Key | Type | Written at |
|---|---|---|
| `udid` | string — the leased simulator's UDID | Worker preflight, device step |
| `os` | string — the runtime, `iOS <major>` | Worker preflight, device step |

## 6. Lock name and liveness rule

**Name: `ios-build`.** A brief whose units build for iOS on a pinned device carries
`"locks": ["ios-build"]`; the launcher maps that name to `<sessions root>/.ios-build-lock` and
refuses to start a second holder.

- **Protects:** one `xcodebuild` and one simulator at a time on the machine, whether the build is
  a Bash `xcodebuild` or an MCP build or test call, driven through `simctl`, `axe` or
  `xcodebuildmcp`. Concurrent builds
  fight over DerivedData and the simulator; concurrent `simctl` calls take CoreSimulatorService
  down for every session at once.
- **Take it before the first iOS build or simulator call of either kind, and again on every resume**, atomically:
  `mkdir <sessions root>/.ios-build-lock` (no `-p` — its failure *is* the lock being held), then
  write the session directory as the first line of `owner` inside it. No pid is recorded: the
  launcher reads that line as a path and compares it to the session it is starting
  (`run-launch.sh`, the lock loop).
- **If the `mkdir` fails**, resolve `owner`'s first line with `realpath`:
  - **Already held** — it is this session's own directory (a rotation, or a resume with no
    stop before it) → continue. Nothing is cleared and nothing is recorded.
  - Otherwise read the holder's roster verdict:
    `python3 ~/.claude/skills/lead/scripts/run-roster.py --runs-root <owner's parent> --only <owner's basename> --no-lead --json`,
    the `verdict` of its one `runs` row.
  - **Live holder** — `running`, `rotating`, `stopping`, `stalled` or `orphaned`, a session that
    can still build → stop with that reason and the owner's session directory; no waiting loop,
    no building anyway.
  - **Stale holder** — `done`, `parked`, `stopped:<code>` or `invalid:<why>`, or no row at all
    (directory gone, `run.json` unreadable) → remove the directory, retake it, and record in
    the ledger whose stale lock was cleared.
- **Release at handoff**, including an early stop or a failure: `rm -rf <sessions root>/.ios-build-lock`.
  A lock outliving its session blocks every later iOS session.
- A repository that isolates builds by DerivedData path and leases simulators from a pool may
  name no lock; its hook says so, and its briefs carry `"locks": []`.

## 7. Kind → check table

| Kind | Check | Rule it enforces |
|---|---|---|
| `tests` | The `load-bearing-tests` loop over the scoped suite: prove the baseline green first, write the predicted kill set to `evidence/<unit>-mutations.md` before mutating, lead each batch with a positive control already seen killed, apply mutations until every new test has been reddened by at least one, expect `** TEST FAILED **` with the targeted test among the failures, restore, `git status --short` clean after | Every new test is proven by a kill or declared a guard; a test nothing reddens is deleted and logged. Against a red baseline every mutant reads as killed, and a batch whose control survives is void |
| `behavior` | The spec tests owe the `tests` row; a change that reaches a screen also owes the `ui` row | As `tests`, plus `ui` |
| `ui` | The accessibility-tree walk of → 4 on each screen the unit row lists: `describe-ui` to `evidence/`, the hook's predicates as the assertion, a screenshot as the record, the oracle written before the walk | A predicate is the check; `blocked` and `unverified` are reported as themselves |
| `refactor` | None on this platform. The hook names a move-equivalence check where it has one | — |
| `docs` | None on this platform | — |

## 8. Sweep method

Base and tip compared on **one leased simulator**, sequentially. The hook names which of the
two methods it runs, and the scripts; both follow the same rules.

**Snapshot matrix.** Every named state, at every device shape, at every text size, rendered
twice — the render and its VoiceOver overlay — and compared exactly, with no tolerance. Read
**both** kinds: the render draws a control's ink and the overlay its frame, so a geometry change
barely touches the render and moves every cell of the overlay.

**Build-and-walk.**

1. Clean tree. Build the base SHA (detached) and keep its `.app`; build the tip and keep its.
2. For each side: uninstall, then the hook's setup with that side's `.app`, then for each sweep
   row — launch into the screen, wait, `describe-ui` to `evidence/sweep/<side>/<screen>.tree.json`,
   run its predicates, screenshot to `evidence/sweep/<side>/<screen>.png`, and write a normalized
   form of the tree.
3. Compare per screen:
   - **predicates — blocking**: passed on base, failed on tip is a defect.
   - **normalized-tree diff — advisory**: list the changed ids.
   - **image diff — advisory**: mask the status bar and any region the hook names; record
     the percentages in the ledger.
4. Leave the tip installed, so the manual pass runs on it.

**Re-recording and findings.** A difference the brief lists as expected (a moved control, a
renamed label) is recorded, not flagged. A change meant to move pixels is re-recorded through
the hook's procedure. Read every changed baseline: **an artifact that changed in a way nobody
can explain is a finding, never a re-record** — and the only cover for the class no sanity
check catches, a plausible image of a screen caught mid-layout. An advisory difference is still
a finding for the handoff; an exploratory pass produces findings and never gates.
