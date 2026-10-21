# role-start — behaviour table

Written before the code, 2026-09-21. Source of each expected value: the Owner's ask in chat ("planner
and lead sessions automatically start at their expected model/effort"), the machine profile's
by-hand launch lines (`cd <projects root>/<project>`, `claude --model … --name …`, then
`/loop /lead watch`), profile §7 Naming, `robowright.json`'s `models` map, and the launcher's
`effort_settings` (effort rides on `--effort` and on `--settings`, per-model key included, because
`settings.json` pins a per-model effort that outranks the bare one). `Assumed` rows are
defaults; each changes a Then if the Owner answers otherwise.

Machine facts come from `~/.claude/robowright/launch.json` → `roles`, so the script names no role.

| # | Rule | Given | When | Then | Expected value from |
|---|---|---|---|---|---|
| R1.1 | a role with no project starts at the role's defaults | role `lead`: model opus, effort medium, prefix `lead`, prompt `/loop /lead watch` | `role-start lead` | claude gets `--model opus --effort medium --name lead` and the prompt as its last argument; cwd unchanged when launch.json names no projects root (R8.3) | profile by-hand line; Lead effort medium is Assumed |
| R1.2 | a role with no prompt passes none | role `planner`: fable, high, no prompt | `role-start planner` | the last argument is the `--name` value | profile: the Planner is started bare |
| R2.1 | the project's settings file picks the model | `<root>/sample/robowright.json` models.lead = sonnet | `role-start lead sample` | `--model sonnet`, `--name lead-sample`, cwd is `<root>/sample` | robowright.json is the source for role models (planner handbook); naming §7 |
| R2.2 | a settings file without that role keeps the default, and says so | robowright.json has no models.lead | `role-start lead sample` | `--model opus`; stderr names the missing key | Assumed |
| R3.1 | a project with no settings file is refused | `<root>/typo/` has no robowright.json | `role-start lead typo` | exit 4, stderr names the path, claude not run | Assumed: a typo must not silently launch on defaults |
| R4.1 | effort rides on --settings too, keyed by the model's id | model opus, effort medium | `role-start lead` | `--settings` is JSON with effortLevel medium and modelSettings["claude-opus-5-5"].effortLevel medium | launcher `effort_settings` |
| R4.1a | sonnet and haiku key their current ids | models.lead = sonnet, then haiku | `role-start lead sample` | modelSettings key is `claude-sonnet-5-5`, then `claude-haiku-5-5` | Anthropic models overview, 2026-10-12 |
| R4.2 | an alias the map does not know is used as written | models.lead = `claude-x-9` | `role-start lead sample` | modelSettings key is `claude-x-9` | launcher `effort_settings` |
| R5.1 | an unknown role is a usage error | roles planner, lead | `role-start boss` | exit 2, stderr lists `lead` and `planner`, claude not run | Assumed |
| R6.1 | --dry-run prints and does not launch | any | `role-start lead --dry-run` | stdout has the command line; claude not run; exit 0 | launcher convention (dry-run first) |
| R7.1 | no roles in launch.json is a missing config | launch.json without `roles` | `role-start lead` | exit 4, stderr names launch.json | Assumed |

## Write scope (R8)

| # | Rule | Given | When | Then | Expected value from |
|---|---|---|---|---|---|
| R8.1 | a hand-started role is granted the projects root, the sessions root and the accounting root, and each repo's whole git directory and a leaf `**/.git` on each granted root are denied | `projects_root`, `sessions_root`, a real repo in `repos` | `role-start lead sample` | `--settings` holds `additionalDirectories` exactly those three, `denyWrite` the repo's git directory, then the projects' Claude settings (`.claude`, `.mcp.json` of the root and each folder, and the `**` wildcards), then `<root>/**/.git` for each of the three, `permissions.deny` the matching `Edit(//…)` rules | ledger C14, C16, C17; bound 2, 3; U46 bound 3 |
| R8.2 | a projects root, or a working directory, at or above a configured repository or the home directory, or inside the repository, is refused | `projects_root` `~/Code` holding the repo; then `~/`; then no projects root on disk, started from `~`; then no projects root on disk, started from a folder inside the repo | `role-start lead` | exit 5, stderr names the projects root, then the working directory, then `inside the repository`; claude not run | bound 7; review 1 F8; review 2 F2 |
| R8.3 | with no project the session starts in the projects root | `projects_root` set | `role-start lead` | cwd is the projects root, so the working directory grants nothing wider | ledger C16; the cwd is a write grant (sandboxing docs) |
| R8.4 | with no well-formed `repos`, nothing is granted | launch.json without `repos` | `role-start lead` | exit 5, stderr names `repos`; claude not run | review 1 F4 |
| R8.5 | a working directory or root through a link, or holding `..`, is refused | a project reached through a link in the projects root; then a project spelled `a/../sample`; then a projects root below a link | `role-start lead <project>` | exit 5, stderr names the link, then `..`, then the link; claude not run | the Owner's decision 2026-10-15 (A); review 3 F5; review 4 F1 |
| R8.6 | a project swapped for a link after the check never starts there | the Lead's projects root; `a/sample` a directory; the grant check returns and `a` is then made a link to a configured repository holding `sample/` | `role-start lead a/sample` | exit 5, "changed after it was checked"; claude never runs | review 5 F1 |
