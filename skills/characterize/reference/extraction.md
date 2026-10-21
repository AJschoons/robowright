# Extraction — finding the events, the states, the outcomes, and the rows

Contents: where events hide · where outcomes hide · naming product states · the field sweep · the
state grid · the decision grid · beyond the branch · the altitude test · reading against name bias

## Where events hide

An event is anything that makes the code under migration run. Enumerate with `grep -n`, not by
reading top to bottom — the ones you miss are the ones nobody calls by hand.

| Kind | Look for |
|---|---|
| User actions | `@IBAction`, `addTarget`, `UIAction`, gesture recognizers, `Button {`, `.onTapGesture`, `.onSubmit`, `.refreshable`, swipe and context-menu actions |
| Lifecycle | `viewDidLoad`, `viewWillAppear` / `DidAppear` / `WillDisappear`, `viewDidLayoutSubviews`, `.onAppear`, `.task`, `.onDisappear`, `deinit`, `prepareForReuse` |
| System | `NotificationCenter` observers, scene / app foreground and background, trait and size-class changes, keyboard, memory warning, `UIAccessibility` status changes |
| Delegates and data sources | Every protocol conformance in an extension; each method is an event |
| Reactive | Combine `sink` / `assign`, `didSet` / `willSet`, KVO, `@Published` and `@Observable` reads that drive work, `onChange(of:)` |
| Time | `Timer`, `asyncAfter`, `Task.sleep`, debounce and throttle, animation completions |
| Other types | Every non-private method: who calls it (`grep` the callers), and in what state |

For each, note **whether it can arrive more than once and in what order relative to the
others** — that is where the second-call and ordering rows come from.

## Where outcomes hide

| Kind | Look for |
|---|---|
| What the user sees | Text, visibility, enabled state, selection, images, colors that carry meaning, layout that changes with state, animation that conveys state |
| What the user feels or hears | Haptics, sounds, VoiceOver announcements and labels, focus moves |
| Navigation | Push, present, dismiss, pop, deep-link handling, tab changes, alerts and sheets |
| Network | Requests started and cancelled, with their parameters |
| Persistence | Core Data / SwiftData / `UserDefaults` / keychain / file writes |
| Analytics and logging | Event names and **payloads** — a key renamed in migration breaks a dashboard silently |
| Calls to collaborators | Delegate callbacks fired, closures invoked, notifications posted — the code's own outgoing events |
| Time | `asyncAfter`, `Task.sleep`, timers, debounce — the delay itself is an outcome (the user waits 0.3 s) and a port the new shape needs a clock seam for |

Port calls are straight-line statements as often as they are inside a branch. The trace in step
3 walks every one of them for that reason.

## Naming product states

Legacy code keeps its state machine in booleans and optionals. List every stored property the
code reads in a condition, then ask which **combinations** a user could tell apart:

```
isSyncing = true                          → "a sync is in flight"
isSyncing = false, lastError = nil        → "idle"
lastError != nil, didDismissError = false → "a failure is showing"
lastError != nil, didDismissError = true  → "a failure was dismissed"
```

- Name states in the user's terms; keep the flag mapping beside each. The mapping is what the
  refuter checks and what the new view model's state will be reviewed against.
- A combination the flags permit but no event sequence reaches is `unreachable` — prove it with
  the writes (`grep` every assignment), do not assume it.
- A flag that is set and never cleared is a state with no exit. That is a row, and usually a
  `suspect`.
- **States with no flag.** Anything pending is a state even though no property says so: a
  closure scheduled with `asyncAfter`, a request in flight, a running timer, an animation whose
  completion does work. So is state parked in a control — a button's `isEnabled` standing in
  for an `isSubmitting` flag, a text field's contents used as the model. Find them under
  "Hops" below, then come back and add them here; the grid is wrong without them.

## The field sweep — finding what is not there

The trace walks code that exists. It cannot see the line nobody wrote. For every stored field,
fill in:

| Field | Written by | Read by (outcomes) | Skipped by |
|---|---|---|---|
| `draft.includesArchived` | Show-archived switch changed | Apply (delegate payload) | **Reset** ("clears every option") · **option count** · **analytics payload** |

"Skipped by" is the column that finds things: for each event or computation whose name, doc
comment, or sibling handling says it covers the whole — reset, clear, apply, a count *of the
filters*, a payload *of the state* — list the fields it does not touch. Each entry is a row,
and usually a `suspect`.

## The state grid

Product states down the side, events across the top. Every cell is one of:

- an **outcome** → becomes a row;
- **nothing happens** → a row too, when a user could reasonably expect something ("retry while
  a sync is in flight starts nothing and tracks nothing");
- **unreachable** → say what prevents it (the control is hidden, the observer is not registered
  in that state). Check the prevention is *synchronous* — a button hidden by a callback that
  arrives later is reachable by a fast second tap.

|  | Sync starts | Finishes ok | Finishes with error | Dismiss tapped | Retry tapped |
|---|---|---|---|---|---|
| Idle | Progress | — | — | Unreachable: no banner | Unreachable: retry hidden |
| Sync in flight | — | Clears | Failure shows | **Progress stays, outcome muted** | Nothing happens |
| Failure showing | Progress | — | — | Hides | Starts a sync |
| Failure dismissed | Progress | — | — | Unreachable | Unreachable |
| *Sync in flight, after a dismissal* | — | Clears | **Nothing shows** | No change | Nothing happens |

The last row did not exist until the grid was drawn: filling "failure dismissed × sync starts"
forced the question of what state that leads to, and the answer — the dismissal flag is never
cleared — is a state the code has and nobody named. The two bold cells are rows nobody would
have written from reading top to bottom, and both turned out to be `suspect`.

## The decision grid

For logic that is combinational rather than stateful — formatting, eligibility, pricing,
which-variant-to-show — list the conditions, then one column per combination that produces a
distinct outcome:

| Free space after download | ≥ floor | ≥ floor | < floor |
|---|---|---|---|
| On cellular and over the threshold | No | Yes | — |
| **Outcome** | Allowed | Ask first | Declined, with the shortfall |

- A `—` means the condition does not matter in that column. Merging columns this way is how
  eight branches become three rules — that is the lift from source language to behavior
  language, done visibly.
- A column you cannot fill from the code is a question about precedence; trace it.
- Boundaries get their own rows when extracted: at the value, one below, one above.

## Beyond the branch

A row-by-row read of conditions cannot see these, and they are where migrations break. Answer
every heading for the unit, even with "none":

- **Order of effects** — when one event produces several outcomes, in what order, and does any
  reader depend on it (state written before or after the delegate is told)?
- **Hops** — which outcomes happen synchronously with the event, and which after a queue hop,
  an `await`, a completion handler, an animation? A view model that makes a synchronous path
  async changes what a fast second event sees.
- **Second call** — what happens when the same event arrives twice: idempotent, doubled, or
  ignored? Is the guard against it set synchronously?
- **Once-only** — flags that make something happen the first time only, and what (if anything)
  resets them.
- **Defaults and fallbacks** — every `??`, default argument, `default:` case, and initial
  property value that a user can end up seeing.
- **Lifetime** — what is observed or scheduled, when it is torn down, and what still fires
  after the screen is gone. Weak vs strong captures that decide whether work completes.
- **Cancellation and failure** — what the user sees when work is cancelled, times out, or
  throws; whether partial state is rolled back.
- **Every outgoing call made once, with the same arguments** — the analytics and delegate
  calls, counted.
- **Traps** — implicitly unwrapped optionals that are read, `!`, array subscripts computed from
  input, `fatalError`, unowned captures. A crash is a behavior, and a new shape that cannot
  crash there (a non-optional injected dependency, a safe index) changes it. Usually welcome;
  still a row, still declared.

## The altitude test

A row is at the right height when **all three** hold:

1. It would read the same about the new view model and about a port to another platform.
2. Someone who has never seen the code could check it against the running app, or against a
   collaborator's recorded calls.
3. It carries the exact observable values — the string, the number, the payload key.

| Too low (source language) | Too high (cannot be checked) | Right |
|---|---|---|
| "when `isSyncing` is false and `lastError` is non-nil and `didDismissError` is false, `bannerLabel.isHidden = false`" | "shows errors appropriately" | "after a sync fails with a server error, the banner says 'Sync failed' and offers retry" |
| "`refreshBanner()` is called from `syncDidFinish`" | "keeps the banner up to date" | "when a sync finishes cleanly the banner disappears" |

Exact values are not "too low". "Shows a short preview" is a worse row than "the preview is the
first 140 characters, or 280 when the note is pinned".

## Reading against name bias

Models describe what identifiers and comments *suggest*, and the effect is large when the two
disagree. Countermeasures while extracting:

- Trace a **concrete value** through every line of the path; write the intermediate values down.
- Treat every comment and doc comment as a claim to verify, never as a source for a Then.
- For each helper the path calls, read its body — do not infer it from its name.
- When a name and the behavior disagree, that is worth a line in the report on its own: the
  migration is the moment to fix the name.
