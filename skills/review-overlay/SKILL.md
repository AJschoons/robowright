---
name: review-overlay
description: Grow a Review Overlay file two ways — mine the recurring catches in a corpus of the Owner's own reviewing (merged pull-request review threads, exported reviews, AI chat transcripts, or a source they describe), or add one rule at a time — as mechanical enumerations the two code Reviewers run. Use when the Owner asks to mine or add to a Review Overlay. Manual invocation only.
disable-model-invocation: true
---

# Review Overlay

A Review Overlay is a file of review enumerations that a `reviewer.overlay` duty row names; the
two code Reviewers apply it after their correctness findings
(`skills/robowright/PROFILE-CONTRACT.md` → Review Overlay). This skill writes one from the catches the Owner keeps making by hand.

It is optional: a profile with no `reviewer.overlay` row is complete, and every review then says
`no Review Overlay named`. The file grows two ways, and is the same file whichever way it grew:
**mine** reads a corpus of the Owner's past reviewing and proposes the catches that recur
(`## Mine`); **add** writes one check from one rule the Owner states (`## Add`). With no corpus
yet, or the work put off, **add** is the path, run now or later.

The file's content is the Owner's: their judgment, their repositories, their colleagues' code in
every quoted hunk. It lives at a private path the Owner names and never enters a public tree, this
one included — `examples/laptop/review-overlay.md` is a synthetic stand-in for that reason.

## Sources

Every source is read into one **record**, the one `threads.jsonl` holds: per comment, who wrote it
(`author`), its text (`body`), where it pointed (`path`, `diffHunk`, `url`) and when (`createdAt`),
one line per thread, each naming the pull request or conversation it came from (`pr`).

Ask for the source and the Owner's login. Four sources, any mix:

- **A repository**, as `owner/name`, read online with `gh` (authenticated, read access).
- **A directory of Markdown exports**, read offline: one file per pull request, holding that pull
  request's review threads, each comment with its author and the file it is on, and the diff
  hunk where the export has one. Each file counts as one pull request; keep the threads the
  Owner's login commented in, as the query below does.
  The exports stay outside every public tree.
- **A directory of AI chat transcripts**, Markdown or JSON exports of the Owner's conversations
  with an assistant, one file per conversation. The record holds the Owner's own turns, never the
  assistant's: keep a turn that names a defect in the assistant's code, says the same thing a
  second time, or says always or never, as a thread of one comment whose `pr` is the conversation
  file and whose `path` and `diffHunk` are the code it discusses, where the transcript shows it.
  The Owner confirms every cluster these turns form (`## Mine`, step 2). The transcripts stay
  outside every public tree.
- **A corpus the Owner describes**: one paragraph the Owner writes, saying where the records are
  and how to read one into the record above. Follow it as written. The records stay outside every
  public tree.

For a repository, every review thread the Owner commented in on every merged pull request, with
the whole thread, one JSON object per line:

```sh
gh api graphql --paginate -f owner=<owner> -f name=<name> -f query='
query($owner: String!, $name: String!, $endCursor: String) {
  repository(owner: $owner, name: $name) {
    pullRequests(states: MERGED, first: 25, after: $endCursor) {
      pageInfo { hasNextPage endCursor }
      nodes {
        url
        reviewThreads(first: 100) {
          totalCount
          nodes {
            comments(first: 100) {
              totalCount
              nodes { author { login } body path diffHunk url createdAt outdated }
            }
          }
        }
      }
    }
  }
}' --jq '.data.repository.pullRequests.nodes[] | .url as $pr
  | (select(.reviewThreads.totalCount > 100 or any(.reviewThreads.nodes[]; .comments.totalCount > 100))
     | {pr: $pr, capped: true}),
    (.reviewThreads.nodes[] | select(any(.comments.nodes[]; .author.login == "<login>"))
     | {pr: $pr, comments: .comments.nodes})' > threads.jsonl
```

- `first: 25` keeps the request under GitHub's 500,000-node limit; `first: 100` on pull requests
  is refused. `--paginate` needs the variable to be named `$endCursor`. `-f` sends the owner and
  name as strings; `-F` would turn an all-digit name into a number the query refuses.
- A pull request with more than 100 threads, or a thread with more than 100 comments, is cut at
  100, and gets one `{"pr": …, "capped": true}` line whether or not the Owner commented in what
  was fetched: their comments past the cut are missing.
- `reviews(states:, author:)` reaches the same comments grouped by review; it drops the thread
  structure this pass reads, so it is not used here.

## Mine

### 1 · Collect the comments

Read every source the Owner named into the one `threads.jsonl`, each as `## Sources` gives it.
Write `threads.jsonl` to a scratch directory outside every repository. Done when the file has
one line per thread the Owner commented in, the count of distinct `pr` values is reported to the
Owner, and every pull request with a `capped` line is named.

### 2 · Cluster into recurring catches

Read every comment of the Owner's with its `diffHunk` and the replies around it, and group
comments that ask for the same change, whatever their wording: one cluster is one **catch**. Praise, questions answered in the thread, and
one-off preferences join no cluster.

A catch is kept when it recurs across at least **N distinct pull requests**. N is the Owner's
call; suggest five. Many comments in one pull request count once. A conversation counts as a
pull request does. Each catch that passes N is a **candidate**: show it to the Owner with its count
and evidence, and keep it only when the Owner confirms it.

Done when every comment of the Owner's is in a cluster or set aside, and each kept catch lists its pull-request
count and two or three comment `url`s as evidence — the file and turn, for a turn with no `url`.

### 3 · Write each catch as a check

Each kept catch becomes one numbered check in exactly three lines:

1. **What to look for** — a mechanical enumeration a Reviewer can run over a diff: a pattern to
   find, a list to compare, a count to check. "Every X in the diff that has no Y."
2. **Why it has bitten before** — the failure the catch prevented, in one line, naming no person
   and no pull request.
3. **How to cite** — what the Reviewer quotes when it fires: `file:line` and the offending text.

Then classify it:

- **Findings-eligible** when a reader can verify it from `file:line` alone. It may make a Reviewer
  `HOLD` only when it is one of the classes the review prompt names
  (`skills/worker/prompts/REVIEW-GATE.md` and `ADVERSARIAL-REVIEW.md`, under Output); outside
  those, a Reviewer treats it as a note, whatever the file says.
- **Note** otherwise: taste, a judgment call, anything needing context the diff does not hold.

Done when every kept catch has a three-line check and a classification of findings-eligible or
note.

## Add

One rule the Owner states becomes one check: typed, pasted from a piece of feedback they received,
or dictated. No clustering and no N: the Owner's choice to write the rule down stands in for the
count.

1. Read the rule back as the three lines of `## Mine` step 3, the second in the Owner's own words
   for why it has bitten, and have the Owner confirm them before anything is written. For a
   dictated rule, read through the slips — misheard words, missing punctuation, a name spelled by
   ear — to the intent, and ask only where the intent stays unclear.
2. Classify it by step 3's test: findings-eligible when a reader can verify it from `file:line`
   alone, else a note.
3. Write it as `## Write the file` says: with a file already at the path, append this one check
   to it and change no existing check; with no file at the path yet, a new file in the template shape
   holding this one check.

Done when the Owner has confirmed the three lines and the class, and the check is in the file.

## Write the file

The shape the Reviewers read, and nothing more; the `## Output` block stays fenced in the file,
as `examples/laptop/review-overlay.md` shows, and starts at `### Findings-eligible`: the review
supplies the one `## Review Overlay` heading and the file's path line above it.

~~~markdown
# Review Overlay — <scope>

## Posture
<optional: one paragraph on how the Owner reads a diff>

### Findings-eligible
1. <what to look for>
   <why it has bitten before>
   <how to cite>

### Notes
1. …

## Output

```markdown
### Findings-eligible
- <check number>: `file:line` — <what fired>, or `none`
### Notes
- <check number>: `file:line` — <what fired>, or `none`
```
~~~

A file already at the path is appended to, as the next paragraph says, never written over.
Write it at the absolute path the Owner names. The path resolves outside every public tree: a
directory under `~/.claude/` can be a symlink into the public clone, so the path is judged by
what it resolves to. Delete the scratch `threads.jsonl`.

When the file exists, both paths append and neither renumbers, since reviews cite checks by
number: a new check takes the next number under its heading, and this skill never renumbers,
rewords or deletes an existing check — deleting one is the Owner's, by hand. A **mine** candidate
whose first line says what an existing check's first line says is reported as a duplicate and
skipped. Then rewrite the `## Output` block with one line per check number, as the example does.

Done when every kept or added check is in the file under its heading, no existing check changed,
and the `## Output` block lists every check number the file holds.

## Hand back

Print the duty row to add, and where:

```
| Reviewer | `reviewer.overlay` | `<the path from Write the file>` |
```

The machine profile's §7 applies it to every repository on the machine; a project hook's §14
applies it to one. The Owner adds the row. Report the kept catches with their pull-request
counts, the number set aside, and any truncation from step 1.
Also report the duplicates skipped, each described source's paragraph, quoted, and, for **add**,
the check's heading and number; when a row already names the path, say the row is unchanged.
