# Manual smoke pass — <TICKET> <one-line change summary>

<!--
Fill every bracket. Delete nothing structural — an empty "deliberately not testing"
section is itself a claim, and it should be a true one.
Row ids match INVENTORY.md and evidence/ filenames.
-->

**If you do one thing:** <the single highest-value check, one sentence>

**Tier:** <Quick / Standard / Deep> — <budget> min. <One sentence on why this tier.>

**Ordered so you can stop anywhere.** Groups are risk-ordered; rows within a group are
ordered to keep you on one screen. Everything below where you stop is the least important.

## Setup

| | |
|---|---|
| Build / branch | <branch @ sha, or the .app path> |
| Device / OS | <device, OS version> |
| Account | <tier / state, or "signed out"> |
| Flags | <flag: on/off, one per line> |
| Seed state | <notes, attachments, anything to set up first> |
| Network | <normal / offline / throttled — only if a row needs it> |
| Reset first? | <yes: how — or no> |

## Already covered by the agent pass

<N> checks ran unattended: **<n> pass**, <n> fail, <n> pre-existing, <n> blocked, <n> infra,
<n> unverified. See [AGENT-PASS.md](AGENT-PASS.md). Rows below are the ones that need your
eyes, not a re-check of those.

<!-- If anything is fail / blocked / unverified, name it here in one line each. -->

## Deliberately not testing

- **<area>** — <why: covered by unit tests / no user-facing surface / out of the tier, priority P2 / needs hardware>
- **<area>** — <why>

## The pass

Tap one box per row. An unchecked row means **not reached** — that's why fail has its own box.

### Plan

<!-- Read-only index, no boxes. The whole pass and its budget at a glance. -->

| # | Area | ~min |
|---|---|---|
| 1 | <screen> | <n> |
| 2 | <screen> | <n> |

### Rows

<!--
FLAT task lists, never nested, never in a table. A checkbox is only tappable as a real list
item at block level; table cells parse inline, so `- [ ]` in a cell is literal text.
Nesting a task list under a task item after intervening paragraphs also drops the boxes in
Typora. Flat, at block level, always works.

`fail —` and `n/a —` keep the trailing dash: both owe a written reason, and the dash is the
prompt. Keep them separate boxes — collapsing them loses the n/a rate Phase 5 prunes with.

Keep `do`, `Expect` and `Why` to one line each. The full risk hypothesis lives in
INVENTORY.md under the row id in the header link.
-->

**1 · \<area\>** · \<n\> min · [S1](INVENTORY.md)
\<exact steps, one line\>
**Expect** \<one observable outcome\>
**Why** \<one clause, under 15 words\>

- [ ] pass
- [ ] fail —
- [ ] n/a —

**2 · \<area\>** · \<n\> min · [S2](INVENTORY.md)
\<exact steps, one line\>
**Expect** \<one observable outcome\>
**Why** \<one clause, under 15 words\>

- [ ] pass
- [ ] fail —
- [ ] n/a —

## Flag matrix

<!-- Only when a flag is involved; delete otherwise. Off rows are regression rows. -->

**F1 · \<area\>** · \<n\> min
\<exact steps, one line\>
**Expect — flag OFF** \<outcome\> · **flag ON** \<outcome\>
**Why** \<one clause\>

- [ ] off passes
- [ ] on passes
- [ ] fail —
- [ ] n/a —

## Charter — Deep tier only

<!-- Delete unless Deep. One time-boxed exploratory session, not more scripted rows. -->

> Explore **<target>** with **<specific inputs, states, or conditions>** to discover
> **<the class of problem you suspect>**.

**Time box:** <20–30> min. Notes, anything surprising, and where you actually spent the time:

-

## After

- Fails: <what happened, and what you want done about each>
- Rows that were N/A and why: <fold back into the inventory>
- Anything you looked at that isn't in the table: <opportunity findings>
