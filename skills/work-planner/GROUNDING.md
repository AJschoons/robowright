# Grounding reports

The two reports a plan is grounded in, whatever its scale: `work-planner` step 2 asks for them
about one ask, `planner` about a project and again about a unit. Launch both as background
subagents in one message. Each returns a cited report with a certainty level per claim (*the docs
say*, *I believe*, *unsure*), and the conclusions rather than the file dumps.

- **Inside** — prior art. Where this lives, the pattern its neighbours already follow, the seams a
  test can reach it through, the names the code uses for the ask's concepts, and anything in the
  code that contradicts the ask. Every claim carries `file:line`. For work with no codebase, the
  inside is the existing material: earlier versions, notes, the docs it must agree with.
- **Outside** — three things. **Primary sources** (official docs, source, specs) for every
  platform or library fact the work leans on. The **named pattern**: what practitioners call this
  shape of problem, who named it, and what they recommend. **One dissenting view**: the most
  credible argument for doing it another way. Every claim carries its link.

Grounded means every fact the plan leans on has a citation, or is marked as belief.
