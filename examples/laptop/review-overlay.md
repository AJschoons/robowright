# Review Overlay — project `sample`

A synthetic example of the shape `review-overlay` writes. Every check, reason and path below
is invented; a real overlay stays at a private path the Owner names.

## Posture

Read the diff for changes at a boundary — a page edge, a network call, a log line — before style.

### Findings-eligible

1. Every pagination cursor or offset the diff computes: a start at 1 or a `<=` against the page size.
   Why: a list endpoint in `example-org/sample-api` dropped the last row of every page.
   Cite: `file:line` of the cursor arithmetic and the page size it is compared with.
2. Every log, print or error-message line the diff adds that takes a token, password, key or header.
   Why: a debug line in `example-org/sample-worker` wrote an API token to shared logs.
   Cite: `file:line` of the log call and the argument that carries the secret.

### Notes

1. Every retry loop the diff adds or changes that has no growing delay or no cap on attempts.
   Why: a fixed-interval retry in `example-org/sample-sync` hammered a service already down.
   Cite: `file:line` of the loop, and the delay and cap it uses, or `none`.

## Output

```markdown
### Findings-eligible
- 1: `file:line` — <what fired>, or `none`
- 2: `file:line` — <what fired>, or `none`
### Notes
- 1: `file:line` — <what fired>, or `none`
```
