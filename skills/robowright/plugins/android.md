platform: android

# Platform plugin — Android (Gradle, Paparazzi, Robolectric)

What is true of building, testing and observing an Android app with Gradle, in any repository.
The project hook names the commands, paths, module and task names, JDK pin and device profile;
this file says what their output, device and lock mean. Written against `../PLUGIN-CONTRACT.md`.

## 0. Identity

| | |
|---|---|
| Toolchain | Gradle (`./gradlew`), the Android Gradle Plugin, Paparazzi (JVM screenshot testing), Robolectric, `uiautomator` for a real-device or emulator tree |
| Last verified against | Not recorded |
| Base | None — this plugin is a base |

## 1. Verdict shapes

**Build.** `./gradlew` prints `BUILD SUCCESSFUL` or `BUILD FAILED`, and its own exit code is the
verdict — `0` green, non-zero red. The hook names the task list its build or gate invokes; quote
the exit code and the task list from the run's tail, never grep stdout for it. A task silently
dropped from that list is what the tail catches — a gate that quietly skips a task still exits
`0`.

**Test run.** The verdict is the same exit code, together with the task list in the tail: which
test and lint tasks ran, and whether each is present. A test task's own console total is
*executions*, not necessarily the distinct test estate — a task that runs more than one build
variant counts each test once per variant, so the console total can be a multiple of the estate.
State which framing (executions or estate) a quoted count is.

**Reading it — the one sanctioned way.** The reading command the hook names, else the
`log-reader` agent with the log's path.

Traps that change what a verdict means:

- **The masked pipe.** A build or gate piped through `grep` and read with plain `$?` reads the
  filter's status, not Gradle's: a `grep` that matches a red build's error text still exits `0`,
  silently reporting the red as green. `set -o pipefail` closes that hole — the pipeline
  then carries the rightmost *failing* command's status, so Gradle's red wins over a matching
  `grep`'s `0`. It does not make the pipeline safe to read: with or without it, a `grep` that
  finds no match on a green build still ends the pipeline at `1`, a false red. Capture the exit
  code directly after `./gradlew`, with its output redirected to a file, before any filter runs.
- **Lint is the only `minSdk` check.** The Kotlin compiler ignores `minSdk`, so a call to an API
  newer than `minSdk` compiles, passes every JVM test, and crashes on an older device; lint's
  `NewApi` check is what catches it. A release build's own `lintVitalRelease` does not stand in
  for the lint task: it fails on Fatal issues only, and `NewApi` is Error. Never drop the lint task
  from a gate. The hook names which module's lint task is the gate.
- **Cadence.** A whole-target run is owed at the brief's `whole_suite_runs_owed` points, and
  only when a source file (the hook's patterns) changed since the last one; otherwise cite the
  previous run's log.

## 2. Hang shape

A hang has no `BUILD SUCCESSFUL`/`BUILD FAILED` line, no exit code, and the log stops growing.

- Start any build or gate run over a minute in the background; watch the log's size, not the
  clock alone.
- **Threshold: the hook's, else 300 s with no log growth.** This plugin sets the default; a
  tighter number belongs to a hook that has measured its own runs.
- Re-run once, with the hook's known-bad task excluded where the hook names one, else unchanged.
  A task the unit touched is never the one skipped. Twice hung is a gate failure, reported as a
  hang: a hang is not a verdict and not a red (Worker handbook, rule 3 and unit-loop step 4).

## 3. Infrastructure-failure shapes

None of these is a verdict; each is retried or reported as itself.

| Shape | What the session does |
|---|---|
| The Gradle daemon fails to start, or a dependency fails to resolve, before any task runs | Retry once before anything else; a second failure is `infra` (Worker handbook, unit-loop step 4) |
| An emulator or device disconnects mid-run (→ 4's exception environment only — Paparazzi has no device to disconnect) — fails exactly like broken code | Control run: the same command on the predecessor head. Red there too → `infra`, not the unit's red |
| `Operation not permitted` on a path under the home directory, or tests failing with `Could not self-attach to current VM` — the session's sandbox, not the code | `infra`, never retried in place. The hook names the command that runs Gradle inside the sandbox; a session with none stops and says so. Never widened from inside a session (below) |
| Release signing fails in a worktree (`sign<Variant>Bundle`/`validateSigning<Variant>`) because the signing material lives only in the main checkout | Not the unit's red. The hook names the gate task that stops before signing |

**Gradle under a session's sandbox.** `./gradlew` writes outside the worktree before any task
runs, so a sandbox that grants only the worktree stops it. The walls, in the order a build meets
them: the wrapper's lock and distribution download in `~/.gradle`; `~/.android` (analytics, the
debug keystore); the Kotlin compile daemon's directory; Robolectric's download lock in the home
directory; and any agent that self-attaches to the test JVM (Paparazzi, inline mocking) through the
HotSpot attach socket. A repository clears them inside the sandbox, not by widening it: a private
`GRADLE_USER_HOME` seeded from the machine's dependency cache and run `--offline`, `ANDROID_USER_HOME`
beside it, the Kotlin compiler in-process, Robolectric's offline mode, and the agent passed as
`-javaagent` at test-JVM start. Two widenings look cheaper and are not. Granting `~/.gradle` or
`~/.m2` lets a session leave an init script or a swapped jar that unsandboxed builds run
later. Running Gradle outside the sandbox behind a fixed task list runs the
session-editable build scripts with no sandbox at all.

## 4. Device model

Two environments, and the hook says which a unit's checks use:

- **Paparazzi — the default, unattended.** A JVM screenshot-testing loop with no device or
  emulator: it renders a view in-process and compares it to a checked-in golden PNG. Fastest, and
  the loop agents prefer.
- **A real device or emulator — the exception.** Install the debug build, launch the target
  activity, and read the tree with `uiautomator dump`. The hook names the AVD or device profile
  and whether its debug build shares the release build's application id.

**The Paparazzi/Robolectric ceiling.** Neither is a phone. Haptics, keyboard behavior, gesture
handling, screen-reader behavior, and max font scale combined with max display size are **not
reachable** from Paparazzi or Robolectric — they belong to a physical-device pass. A hook that
has run its own Paparazzi/Robolectric suite against a case this list omits corrects it there,
not here. A unit whose row touches any of these is
`unverified` on this toolchain's default environment, not a pass; flag it explicitly rather than
implying Paparazzi or Robolectric covered it.

## 5. `device: {}` schema

None on this platform. Paparazzi and Robolectric need no leased device; the hook names its own
`run.json` fields where a unit drives a real device or emulator.

## 6. Lock name and liveness rule

None on this platform. Unlike a pinned iOS simulator, an Android build or Paparazzi run does not
contend with other sessions on the same machine the same way; a repository whose hook builds
Android on a shared, pinned emulator names its own lock.

## 7. Kind → check table

| Kind | Check | Rule it enforces |
|---|---|---|
| `tests` | The `load-bearing-tests` loop over the scoped suite: prove the baseline green first, write the predicted kill set before mutating, mutate until every new test has been reddened by at least one, restore, `git status --short` clean after. The hook may also run a repo-owned static guard suite — a checked-in test that greps real sources for contracts the compiler cannot see (an import that should never appear, a pattern retired for a reason) — those guards are the hook's own named rules, not this plugin's | Every new test is proven by a kill or declared a guard; a static guard suite polices whatever rules the hook names, never rules this plugin invents |
| `behavior` | The spec tests owe the `tests` row; a change that reaches a screen also owes the `ui` row | As `tests`, plus `ui` |
| `ui` | The check of → 4 on each screen the unit row lists, on whichever environment the hook names (a Paparazzi golden, read as an image; or a `uiautomator` tree on a real device or emulator, walked): the hook's predicates as the assertion, a screenshot or golden as the record, the oracle written before the check | A predicate is the check; a row the toolchain's ceiling (→ 4) cannot reach is `unverified`, not a pass |
| `refactor` | None on this platform. The hook names a move-equivalence check where it has one | — |
| `docs` | None on this platform | — |

## 8. Sweep method

**Golden-PNG comparison, blocking.** Re-render the changed screens through Paparazzi and read
every changed golden PNG: a golden that moved in a way nobody can explain is a **finding, never a
re-record** — the same rule iOS's snapshot matrix follows, and the only cover for a plausible
image of a screen caught mid-layout. A change meant to move pixels is re-recorded and the new
goldens committed with the code; the goldens are the review surface for anyone not running the
app. The hook names the task that re-records them.
