---
paths:
  - "tools/robowright-dash.py"
  - "tests/dash/**"
---

# Dashboard

`tools/robowright-dash.py` renders session-written text: slugs, stop details, ledger lines,
handoffs, `run.json` fields. It serves that text to a browser on the Owner's machine.

- **Escape every dynamic value for where it lands.**
  - HTML text or a quoted attribute: `e()`.
  - A URL path segment: `quote(name, safe='')`, as `project_link` does.
  - An `id` or `#` fragment: `anchor()`.
  - The JSON endpoint: `json.dumps`.

  A value is dynamic unless it is a literal or a module constant. A helper that returns HTML builds
  it the same way; one that returns text leaves the escaping to its caller.
- **Escape a response body even when it holds no markup.** Every response but the JSON endpoint
  is served as `text/html`, so an error message that echoes the path or a name is HTML too.
- **Keep the Host check** at the top of `Handler.do_GET`: anything but `127.0.0.1:<port>` or
  `localhost:<port>` gets 403. It is what stops a rebinding page from reading the dashboard.
- **Keep the bind on `127.0.0.1`** in `serve`.
- **Keep it GET-only and read-only.** Add no `do_POST`, `do_PUT` or other handler. Never let a
  request run a command or write a file.
- **Treat numbers from `run.json` as untrusted.** Read them through `count()`, which returns
  `None` for anything but a finite number.

`tests/conventions/` flags any f-string, `%` or `.format` HTML interpolation it cannot trace to
`e()`, a number, a constant, or a module function whose returns are themselves safe. When a
helper's parameter reaches HTML unescaped, the lint flags each call that passes it data. It cannot
see a string with no markup served as HTML; that one is the reviewer's. A site
that is safe for a reason the lint cannot see gets a line in `tests/conventions/allowlist.txt`
saying why.
