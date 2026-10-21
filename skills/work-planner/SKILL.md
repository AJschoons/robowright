---
name: work-planner
description: The front door for a single ask — turns one task, idea, or dictated request into a work order a fresh-context agent can run with. Use when the Owner says "plan this", "scope this", or "write this up for an agent", or hands over an ask too loose to just do and too small for a project (`planner`).
---

# Work planner

One ask in, one **work order** out: a document that survives a **cold start**. An agent that has
never seen this conversation reads it and runs.

## 1. Name the destination

State the **destination** back in one or two lines: what exists when the work is done, and its
kind — build, fix, decide, write, investigate. The Owner may dictate; read through slips to the intent.

The destination sizes the ask:

- **Mechanical** — a rename, a move, a config tweak, a fix whose cause is known. Step 2 runs the
  inside report only.
- **A project** — more than one session can hold, or fog a single grilling will not clear. Say so,
  hand the Owner to `planner`, and end here.
- Everything else runs every step.

When two readings of the ask would send step 2 in different directions, ask that one question
first. Otherwise carry on; the destination goes out again as the first **Assumed** line of step 4.

## 2. Ground

Ask for the two reports in [GROUNDING.md](GROUNDING.md), about this ask.

Work step 3 while they run. Save both reports beside the work order as `<slug>-grounding.md`.

Done when every fact the plan leans on has a citation, or is marked as belief.

## 3. Translate

Invoke `domain-modeling`. Every noun in the ask resolves to a glossary term or the code's own
symbol (`SyncStore`, where the Owner dictated "sink store"). A noun that stays fuzzy or overloaded
becomes a question for step 4.

Then the patterns. Wherever the ask spends a sentence describing an approach, find the **leading
word** the model already holds for it ("one thin path end to end first" is a *tracer bullet*).
Read [LEADING-WORDS.md](LEADING-WORDS.md): use its word when one fits, and add a row when the
outside report names a better one. A word earns its place when it retires a sentence and changes
what an agent does by default.

Done when every concept in the draft has exactly one name, and that name is a glossary term, a
code symbol, or a leading word.

## 4. Grill

Invoke `grilling` on what is still open. The destination, the sizing call, and every term you
settled yourself open the round as **Assumed**. The dissenting view goes to the Owner as a question
whenever it would change the approach. The decision record lands in the work order.

Done when the frontier is empty.

## 5. Write the work order

Fill [WORK-ORDER-TEMPLATE.md](WORK-ORDER-TEMPLATE.md), applying `writing-for-agents`: completion
criteria that are checkable and exhaustive, targets phrased as the positive. It goes in the
project folder when the ask belongs to one, otherwise the inbox the profile → Paths names, as
`<YYYY-MM-DD>-<slug>.md`.

Then run the **cold start**: hand a fresh subagent the work order alone and ask what it would do
first and what it would have to ask. Each question it raises is a gap. Close the gaps in the work
order, once.

Done when the cold-start reader's questions are all answered by the document.

## 6. Hand over

Give the Owner the path, the destination line, and anything under **Still open**. Three ways on:

- **Here** — the work fits what is left of this session and they say go: carry it out from the work
  order (`bdd` first for a behavior change).
- **A fresh session** starts from the file. The work order is the whole hand-off.
- **Unattended, under Robowright's gates** — where `planner` is installed, a fresh Planner session
  turns the work order into a brief: `/planner order <path>`.
