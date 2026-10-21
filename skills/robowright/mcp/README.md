# The approved MCP list

The MCP servers a Robowright Session may start. A brief names its picks in `run.json.mcp`; the
launcher (`scripts/run-launch.sh`) builds the session's MCP config and allow rules from the
entries here and refuses any server with no file in this directory.

**Adding an entry, or loosening a pin, is the Owner's call.** It is a new dependency (profile →
Owner-only floor). A Planner or Worker that needs a server with no entry stops `one-way-door`.

## A brief's pick

```json
"mcp": [{"server": "xcodebuildmcp", "workflows": ["simulator", "ui-automation"], "allow": ["mcp__xcodebuildmcp__*"]}]
```

| Key | Means |
|---|---|
| `server` | The entry's file name without `.json`. Each server appears once |
| `workflows` | The tool groups to load, each one listed in the entry's `workflows` |
| `allow` | Optional. It replaces the entry's `allow` for this session. Every rule is `mcp__<server>` or starts `mcp__<server>__` for this server, and holds only letters, digits, `_`, `*` and `-` |

`mcp` absent, `null` or `[]` starts the session with no servers. `run.json.mcp_config` is retired:
the launcher refuses a non-null value.

## An entry

One file per server, `<server>.json`. Every key is required. Whenever a brief picks any server,
the launcher checks every file here, so one malformed entry refuses every brief that picks.

| Key | Means |
|---|---|
| `server` | The name, equal to the file name: lower-case letters, digits and hyphens, starting with a letter or digit. It becomes the `mcpServers` key and the `mcp__<server>` rule prefix |
| `install` | How the Owner installs it, as text. The launcher never runs it |
| `command` | The bare binary name: letters, digits and `. _ + -`, not starting with `.` or `-`. The launcher resolves it on its own `PATH` and writes the absolute path into the config, because a daemon-started session's `PATH` differs |
| `args` | Arguments to `command`, a list of strings |
| `env` | Environment for the server, an object of strings |
| `version_args` | The arguments that print the version, e.g. `["--version"]`: at least one, each letters, digits and `. _ = -` |
| `version_pin` | The accepted version, digits and dots, not starting with a dot: the printed version equals it or starts with it plus `.`. `"2.7"` accepts `2.7.0` and `2.7.12`, and refuses `2.8.0` and `2.70.0` |
| `workflows_env` | The variable that receives the chosen workflows, comma-joined: letters, digits and `_` |
| `workflows` | Every workflow a brief may pick: at least one, each letters, digits, `_` and `-` |
| `allow` | The default allow rules, passed as `--allowedTools`. Each follows the pick's `allow` rules |

## Why allow rules

Workers run in `auto` permission mode. An MCP call with no allow rule goes to the auto-mode
classifier, and a dialog leaves a `--bg` session `waiting` with nobody to answer. Allow rules
let the calls a brief chose run unprompted.

## Entries

| Server | Pinned | Notes |
|---|---|---|
| `xcodebuildmcp` | `2.7` | iOS build, test and simulator control. `session-management` is not in `xcodebuildmcp.json`'s `workflows` list. Two of its tools, `session_set_defaults` and `session_use_defaults_profile`, take `persist`, which writes `.xcodebuildmcp/config.yaml` into the worktree: a Worker leaves `persist` unset. How a Worker builds, tests and drives the simulator through it: `../plugins/ios.md` §1, §4 and §6 |
