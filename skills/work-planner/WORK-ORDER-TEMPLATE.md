# Work order template

Skip a section that would be empty. Decisions and approach are written in domain terms and leading
words; `file:line` belongs to **Grounding**, pinned to a commit, because paths rot and terms hold.

```markdown
# <destination, as a title>

## Destination
<what exists when this is done, in one or two lines. Kind: build | fix | decide | write | investigate>

## Why
<the problem from the point of view of whoever has it, and what prompted the ask now>

## Language
<each glossary term and leading word this document uses, defined in a line. A reader with no
access to the glossary needs nothing else.>

## Grounding
As of `<repo>@<short sha>`. Full reports: `<slug>-grounding.md`.

**Inside**
- <fact> — `file:line`

**Outside**
- <fact> — <link> *(the docs say | I believe | unsure)*
- **Named pattern:** <name, who named it, what it recommends>
- **Dissent:** <the counter-argument> — <how it was answered, or "open: see Still open">

## Decisions
- <the call> — chose X over Y because <reason>. Costs: <what was given up>.

**Rejected:** <the approach, who killed it, the reason in their words>
**Assumed:** <calls made for the Owner that they did not object to>

## Approach
<the route in leading words. The first slice is the tracer bullet: the thinnest path through every
layer that can be verified on its own. Then what widens it. The seams tests reach it through.>

## Proof
<the evidence that shows the destination was reached: the behaviors, each with where its expected
value comes from; the commands to run and what they print; what to look at. Checkable and
exhaustive.>

## Out of scope
<ruled out of this effort, and where each was parked>

## Stop and ask
<the one-way doors on this route. Reaching one ends the run with the question.>

## Still open
<blocked on a fact or a person, with what unblocks it>
```
