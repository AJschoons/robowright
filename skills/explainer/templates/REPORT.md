# <Project name> — project report

<date> · <tracker item, if there is one> · written by `explainer-<project>` from the project record

> **Five-minute path (whoever is evaluating or inheriting the work):** §1, §2, §4 (table only), §5, §6.
> **Twenty-minute path (maintaining engineers):** §3, §4, §7, §8, §9, with §1–2 for orientation.

## 1. Summary

<three to five sentences: what shipped, for whom, what is different now>

## 2. Why

<the problem, the time box if there was one, the non-goals — from PROJECT.md>

## 3. What changed architecturally

<before/after component diagram — Mermaid flowchart, as-built per the Reviewer's read>

<C4 container view if more than one process or service is involved>

<sequence diagram only if operation order changed; say which flow>

## 4. Key decisions

Full record: `DECISIONS.md`. At most ten rows.

| ID | Decision | Status | Alternatives rejected | Consequence |
|---|---|---|---|---|

## 5. Trade-offs

<the two to four genuinely open calls and what each cost>

## 6. How it was built

<Robowright, the delegation level, how many Robowright Sessions, what a person reviewed and accepted, and the budget figures the profile's Budget section names if the Owner wants them shown>

## 7. What was verified, and how

<suites, mutation testing, sweeps, smoke passes — and the accepted-untested list with reasons>

## 8. Known gaps and follow-ups

<at most eight bullets, each with the follow-up item or the reason there is none>

## 9. How to operate and extend it

<entry points; flag and rollout state where the change ships behind a flag; what is structural (change with care) vs safe to change; where the tests that guard each live>

## 10. Links

<the published units, tracker items, owner briefs, exploration docs, runbooks>
