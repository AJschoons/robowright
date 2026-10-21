#!/usr/bin/env python3
"""
The conventions lint: finds the sites `.claude/rules/session-inputs.md` and `dashboard.md` forbid.

    lint.py [--root=<dir>] [--allowlist=<file>]

Reads the files in the session-inputs scope under <root> (default: this clone). Prints one
`conventions: <check> <path>:<line>: <source line>` per finding and one `conventions: stale allowlist
line <n>: <check> <path>` per entry that matches nothing, exit 1; else `conventions: clean`, exit 0.
An allowlist line it cannot read is refused on stderr, exit 2.

Allowlist lines are `<check>\t<path>\t<reason>\t<source line, trimmed>`; `#` lines and blank lines
are skipped. An entry clears one finding of that check in that file whose trimmed line is the source
it names; identical lines need one entry each. It finds sites; it never rewrites one.

It is a tripwire for the usual ways of writing each forbidden thing: shell is read as words, Python as
an AST. The rules in `.claude/rules/` and the reviewer are the check. Known limits:
- a JSON object split over several lines, in a heredoc body or a printf format, and JSON arrays;
- a `$( )` in a heredoc body that runs past the end of its line, and a `case` arm's `)` inside `$( )`;
- a command built in a variable and run as `$cmd`;
- arithmetic and eval found by pattern, so an unusual spelling of either;
- values that reach HTML through containers, attributes, or a helper passed as a value (`map(dot, …)`);
- text served as HTML from a string with no markup in it;
- in Python, `shell` passed in a `**{...}` dict, `os` reached through an alias, `getattr` or `__import__`, and a
  shell named by a local variable;
- in shell, a shell named by a variable (`"$SHELL" -c`), and hook arithmetic spelled `declare -i`, `$[ ]` or an
  array subscript (`${a[$v]}`);
- a write to a session's folder anywhere but a hook or the launcher, a redirect inside a heredoc body or a
  double-quoted `$( )`, `>|` and `>& file`, a write by `tee`, `cp`, `mv`, `dd` or `sed -i`, and Python's `open()`
  for writing; a quoted `"/dev/null"` reads as a file.
"""
import argparse, ast, os, re, sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
OWNER_SIDE = {"skills/lead/scripts/accept.sh", "skills/robowright/scripts/run-launch.sh", "tools/robowright-dash.py",
              "skills/worker/scripts/run-cost.py", "skills/robowright/scripts/session-state.py"}
DASHBOARD = "tools/robowright-dash.py"
SHELLS = {"sh", "bash", "zsh", "dash", "ksh"}
LAUNCHER = "skills/robowright/scripts/run-launch.sh"
CHECKS = {"shell-true", "os-system", "eval", "sh-c", "json-shell", "hook-arithmetic", "raw-git", "dash-unescaped",
          "session-write"}

# Shell, one physical line at a time; a `#` line is skipped.
SH_EVAL = re.compile(r"(^|[\s;&|(])eval(\s|$)")
# `-c` may sit in an option group (`-lc`) or after other options (`--norc -c`).
SH_C = re.compile(r"(^|[\s;&|(])(\S*/)?(ba|z|da|k)?sh\s+(--?[\w-]+\s+)*-[A-Za-z]*c[A-Za-z]*\s+(\"[^\"]*\$|\$)")
# A JSON key: `{"key":`, or `{\"key\":` inside double quotes.
JSON_KEY = re.compile(r"\{\s*\\?\"[A-Za-z_][\w-]*\\?\"\s*:")
PRINTF_JSON = re.compile(r"\b(printf|echo)\b.*\{\s*\"[A-Za-z_][\w-]*\"\s*:")
JQ = re.compile(r"(^|[\s;&|(])jq\s")
JQ_TWO_ARGS = {"--arg", "--argjson", "--slurpfile", "--rawfile"}
# A `>` or `>>` to a file: not a descriptor (`>&2`), a process substitution or a comparison (`>=`).
REDIRECT = re.compile(r"(?<![<>&|=-])(?:&|\d)?>>?(?![>&=(|])\s*([^\s;&|)]+)")
NOT_A_FILE = {"/dev/null", "/dev/stderr", "/dev/stdout", "/dev/tty"}
TESTS = re.compile(r"\(\(.*?\)\)|\[\[.*?\]\]")
ARITH = [re.compile(r"\$\(\((.*?)\)\)"), re.compile(r"(?<!\$)\(\((.*?)\)\)"), re.compile(r"(?:^|[\s;&|])let\s+(.*)"),
         re.compile(r"\[\[(.*?\s-(?:eq|ne|lt|le|gt|ge)\s.*?)\]\]")]


def scoped(rel: str) -> bool:
    parts = rel.split("/")
    if rel == "install.sh" or parts[0] == "tools":
        return True
    return parts[0] == "skills" and any(p in ("scripts", "hooks") for p in parts[1:-1])


def language(path: Path) -> str:
    if path.suffix == ".py":
        return "python"
    if path.suffix == ".sh":
        return "shell"
    try:
        first = path.read_text(errors="replace").split("\n", 1)[0]
    except OSError:
        return ""
    if first.startswith("#!") and "python" in first:
        return "python"
    if first.startswith("#!") and re.search(r"\b(ba)?sh\b", first):
        return "shell"
    return ""


def tree_files(root: Path):
    for dirpath, dirnames, filenames in os.walk(root):
        dirnames[:] = sorted(d for d in dirnames if d not in (".git", "__pycache__") and not (Path(dirpath) / d).is_symlink())
        for name in sorted(filenames):
            path = Path(dirpath) / name
            rel = path.relative_to(root).as_posix()
            if scoped(rel) and not path.is_symlink():
                lang = language(path)
                if lang:
                    yield rel, path, lang


# ---- shell ----

def jq_filter(rest: str):
    """The first non-option word after `jq`, quotes kept, or None."""
    words, i = [], 0
    while i < len(rest) and len(words) < 12:
        while i < len(rest) and rest[i] in " \t":
            i += 1
        if i >= len(rest) or rest[i] in "|);&<>":
            break
        start = i
        if rest[i] in "'\"":
            quote, i = rest[i], i + 1
            while i < len(rest) and not (rest[i] == quote and (quote == "'" or rest[i - 1] != "\\")):
                i += 1
            i += 1
        else:
            while i < len(rest) and rest[i] not in " \t|);&<>":
                i += 1
        words.append(rest[start:i])
    skip = 0
    for word in words:
        if skip:
            skip -= 1
        elif word in JQ_TWO_ARGS:
            skip = 2
        elif word == "--indent":
            skip = 1
        elif not word.startswith("-"):
            return word
    return None


def backtick_end(text: str, i: int) -> int:
    """The index just past the backtick that closes the one at `i`, or the text's end."""
    j = i + 1
    while j < len(text) and text[j] != "`":
        j += 2 if text[j] == "\\" else 1
    return min(j + 1, len(text))


HEREDOC = re.compile(r"<<-?[ \t]*(['\"]?)([A-Za-z_][\w-]*)\1")
# The same, never the tail of a `<<<` here-string.
OPENER = re.compile(r"(?<!<)" + HEREDOC.pattern)


def heredoc_body(text: str, i: int, delimiter: str):
    """(body lines, index just past the delimiter line) for a heredoc whose body starts at `i`; None when the
    delimiter never comes, and the body is then read as code."""
    lines, j = [], i
    while j < len(text):
        newline = text.find("\n", j)
        end = len(text) if newline < 0 else newline
        if text[j:end].strip() == delimiter:
            return lines, min(end + 1, len(text))
        lines.append(text[j:end])
        j = end + 1
    return None


def body_words(lines: list, line: int) -> list:
    """The words of an expanding heredoc body: each line as one word, and the words of each `$( )` and backtick
    command in it, read line by line."""
    words = []
    for number, text in enumerate(lines, start=line):
        words.append((number, text, bool(re.search(r"(?<!\\)\$", text))))
        j = 0
        while j < len(text):
            if text[j] == "\\":
                j += 2
            elif text[j] == "$" and text[j + 1:j + 2] == "(" and text[j + 2:j + 3] != "(":
                inner, j, _ = read_shell(text, j + 2, number, True)
                words.extend(inner)
            elif text[j] == "`":
                end = backtick_end(text, j)
                words.extend(shell_words(text[j + 1:end - 1], number))
                j = end
            else:
                j += 1
    return words


def shell_words(text: str, line: int = 1) -> list:
    """(line, word, expands) for each shell word in a script, read as a whole so a quoted string may span lines, and
    for each word of every `$( )` and backtick command in it. The word keeps its quotes; `expands` says a `$` sits
    outside single quotes, unescaped. A `#` that starts a word runs to the end of its line. A heredoc body is not
    shell: an expanding one gives each line as a word, and the words of the commands in it; a quoted one gives
    nothing."""
    return read_shell(text, 0, line, False)[0]


def read_shell(text: str, i: int, line: int, inside: bool):
    """(words, index, line) read from `i`. Inside a `$( )` it stops just past the unquoted `)` that closes it."""
    words, word, start, expands, quote, pending, depth = [], "", line, False, "", [], 0

    def close():
        nonlocal word, expands
        if word:
            words.append((start, word, expands))
        word, expands = "", False

    while i < len(text):
        c = text[i]
        if not word:
            start = line
        if quote == "'":
            quote = "" if c == "'" else quote
        elif c == "\\" and text[i + 1:i + 2] == "\n" and not quote:
            close()
            line, i = line + 1, i + 2
            continue
        elif c == "\\" and i + 1 < len(text):
            line += text[i + 1] == "\n"
            word, i = word + text[i:i + 2], i + 2
            continue
        elif c == "$" and text[i + 1:i + 2] == "(" and text[i + 2:i + 3] != "(":
            inner, i, line = read_shell(text, i + 2, line, True)
            words.extend(inner)
            word, expands = word + "$()", True
            continue
        elif c == "`":
            end = backtick_end(text, i)
            words.extend(shell_words(text[i + 1:end - 1], line))
            line += text.count("\n", i, end)
            word, expands, i = word + "$()", True, end
            continue
        elif quote == '"':
            quote = "" if c == '"' else quote
            expands = expands or c == "$"
        elif c in "'\"":
            quote = c
        elif c == "#" and not word:
            newline = text.find("\n", i)
            i = len(text) if newline < 0 else newline
            continue
        elif c == "<" and text[i:i + 3] != "<<<" and (opened := HEREDOC.match(text, i)) and text[i - 1:i] != "<":
            close()
            pending.append((opened.group(2), not opened.group(1)))
            i = opened.end()
            continue
        elif c == "\n" and pending:
            close()
            line, i = line + 1, i + 1
            for delimiter, expanding in pending:
                body = heredoc_body(text, i, delimiter)
                if body is None:
                    break
                lines, i = body
                if expanding:
                    words.extend(body_words(lines, line))
                line += len(lines) + 1
            pending = []
            continue
        elif c == ")" and inside and depth == 0:
            close()
            return words, i + 1, line
        elif c in " \t\n;|&<>()":
            close()
            depth += (c == "(") - (c == ")")
            line, i = line + (c == "\n"), i + 1
            continue
        else:
            expands = expands or c == "$"
        line += c == "\n"
        word, i = word + c, i + 1
    close()
    return words, i, line


def heredoc_lines(text: str) -> set:
    """Line numbers of every heredoc body: data, not commands."""
    body, delimiter = set(), None
    for number, line in enumerate(text.split("\n"), 1):
        if delimiter is not None:
            if line.strip() == delimiter:
                delimiter = None
            else:
                body.add(number)
            continue
        opened = OPENER.search(line)
        if opened:
            delimiter = opened.group(2)
    return body


def unquoted_lines(text: str) -> list:
    """The script's lines with heredoc bodies emptied and every quoted string's and comment's text blanked, read as a
    whole so a string may span lines."""
    bodies = heredoc_lines(text)
    code = "\n".join("" if n in bodies else line for n, line in enumerate(text.split("\n"), 1))
    out, quote, i = [], "", 0
    while i < len(code):
        c = code[i]
        if quote == "'":
            quote = "" if c == "'" else quote
            out.append(c if c in "'\n" else "_")
        elif quote == '"':
            if c == "\\" and i + 1 < len(code):
                out.append("_" + ("\n" if code[i + 1] == "\n" else "_"))
                i += 2
                continue
            quote = "" if c == '"' else quote
            out.append(c if c in '"\n' else "_")
        elif c == "\\" and i + 1 < len(code):
            out.append(code[i:i + 2])
            i += 2
            continue
        elif c in "'\"":
            quote = c
            out.append(c)
        elif c == "#" and (i == 0 or code[i - 1] in " \t\n;"):
            newline = code.find("\n", i)
            newline = len(code) if newline < 0 else newline
            out.append("_" * (newline - i))
            i = newline
            continue
        else:
            out.append(c)
        i += 1
    return "".join(out).split("\n")


def writes_a_file(line: str) -> bool:
    return any(m.group(1) not in NOT_A_FILE for m in REDIRECT.finditer(TESTS.sub("", line)))


def shell_findings(rel: str, text: str, is_hook: bool):
    by_line = {}
    for number, word, expands in shell_words(text):
        by_line.setdefault(number, []).append((word, expands))
    writers = is_hook or rel == LAUNCHER
    masked = unquoted_lines(text) if writers else []
    for number, line in enumerate(text.split("\n"), 1):
        if line.lstrip().startswith("#"):
            continue
        if writers and writes_a_file(masked[number - 1]):
            yield "session-write", number
        words = by_line.get(number, [])
        unquoted = re.sub(r"'[^']*'", "''", line)
        if SH_EVAL.search(unquoted):
            yield "eval", number
        if SH_C.search(line):
            yield "sh-c", number
        if PRINTF_JSON.search(line) or any(JSON_KEY.search(word) and expands for word, expands in words) or any(
                (word := jq_filter(line[m.end():])) and word.startswith('"') and re.search(r"(?<!\\)\$", word)
                for m in JQ.finditer(line)):
            yield "json-shell", number
        if is_hook and any(re.search(r"[A-Za-z_$]", m.group(1)) for pattern in ARITH for m in pattern.finditer(unquoted)):
            yield "hook-arithmetic", number
        # Any bare `git` word: command position takes too many forms (`command`, `exec`, a case arm) to list.
        if rel in OWNER_SIDE and any(word == "git" or word.endswith("/git") for word, _ in words):
            yield "raw-git", number


# ---- python ----

def is_shell_word(node) -> bool:
    if isinstance(node, ast.Constant) and isinstance(node.value, str):
        return os.path.basename(node.value) in SHELLS
    return isinstance(node, ast.Name) and node.id.lower() in SHELLS


def command_word(node, constants) -> str:
    """The basename of an argv element: a string, or a module constant naming one; "" otherwise."""
    if isinstance(node, ast.Name):
        node = constants.get(node.id)
    if isinstance(node, ast.Constant) and isinstance(node.value, str):
        return os.path.basename(node.value)
    return ""


def module_constants(tree) -> dict:
    return {t.id: n.value for n in tree.body if isinstance(n, ast.Assign) and isinstance(n.value, ast.Constant)
            for t in n.targets if isinstance(t, ast.Name)}


def python_findings(rel: str, tree):
    constants = module_constants(tree)
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom) and node.module == "os" and any(a.name in ("system", "popen") for a in node.names):
            yield "os-system", node.lineno
        if isinstance(node, ast.Call):
            if any(k.arg == "shell" and not (isinstance(k.value, ast.Constant) and not k.value.value) for k in node.keywords):
                yield "shell-true", node.lineno
            func = node.func
            if isinstance(func, ast.Attribute) and isinstance(func.value, ast.Name) and (
                    (func.value.id == "os" and func.attr in ("system", "popen"))
                    or (func.value.id == "subprocess" and func.attr in ("getoutput", "getstatusoutput"))):
                yield "os-system", node.lineno
            if isinstance(func, ast.Name) and func.id == "eval":
                yield "eval", node.lineno
        if isinstance(node, (ast.List, ast.Tuple)) and node.elts:
            elts = node.elts
            if command_word(elts[0], constants) == "env":
                elts = elts[1:] or elts
            if is_shell_word(elts[0]):
                for i, elt in enumerate(elts[:-1]):
                    nxt = elts[i + 1]
                    if isinstance(elt, ast.Constant) and isinstance(elt.value, str) \
                            and re.fullmatch(r"-[A-Za-z]*c[A-Za-z]*", elt.value) and not (
                            isinstance(nxt, ast.Constant) and isinstance(nxt.value, str)):
                        yield "sh-c", node.lineno
            if rel in OWNER_SIDE and command_word(elts[0], constants) == "git":
                yield "raw-git", node.lineno
    if rel == DASHBOARD:
        yield from Dashboard(tree).findings()


class Dashboard:
    """Every HTML-building f-string, `%` and `.format` in the dashboard, each interpolated value traced to `e()`,
    a number, a constant, a module constant table, or a module function whose every return is itself safe.
    A value that is safe once its function's parameters are makes those parameters raw, and every call that
    passes a raw parameter is then a site of its own."""

    SAFE_CALLS = {"e", "quote", "len", "int", "sum", "float"}
    SAFE_IF_ARGS = {"round", "min", "max", "abs"}
    TEXT_METHODS = {"title", "upper", "lower", "strip", "removeprefix", "removesuffix"}

    def __init__(self, tree):
        self.tree = tree
        self.functions = {n.name: n for n in tree.body if isinstance(n, ast.FunctionDef)}
        self.parents = {child: parent for parent in ast.walk(tree) for child in ast.iter_child_nodes(parent)}
        self.constants = module_constants(tree)
        self.returns_memo = {}
        self.names_seen = set()
        self.raw = {}  # function name → its raw parameters
        self.called = {n.func.id for n in ast.walk(tree) if isinstance(n, ast.Call) and isinstance(n.func, ast.Name)}

    @staticmethod
    def is_html(text: str) -> bool:
        return "<" in text or ">" in text or '="' in text

    def loop_bound(self, node) -> frozenset:
        """Names the comprehensions around a site bind: `name` over a constant table, `!name` over anything else."""
        names = set()
        while node in self.parents:
            node = self.parents[node]
            if isinstance(node, (ast.ListComp, ast.GeneratorExp, ast.SetComp, ast.DictComp)):
                names |= {t.id if self.constant_table(g.iter) else f"!{t.id}" for g in node.generators
                          for t in ast.walk(g.target) if isinstance(t, ast.Name)}
            if isinstance(node, (ast.FunctionDef, ast.Lambda)):
                break
        return frozenset(names)

    def enclosing(self, node):
        while node in self.parents:
            node = self.parents[node]
            if isinstance(node, (ast.FunctionDef, ast.Lambda)):
                return node
        return None

    def findings(self):
        while True:
            before = {k: set(v) for k, v in self.raw.items()}
            found = sorted(set(self.sites()))
            if self.raw == before:
                return found

    @staticmethod
    def params(fn) -> frozenset:
        args = fn.args
        return frozenset(a.arg for a in [*args.posonlyargs, *args.args, *args.kwonlyargs, args.vararg, args.kwarg] if a)

    def check_value(self, value, site):
        """A finding's line, or None; a value safe only once its function's parameters are marks them raw."""
        fn, bound = self.enclosing(site), self.loop_bound(site)
        if self.safe(value, fn, bound):
            return None
        # A function nothing here calls has no caller to check its parameters at.
        if isinstance(fn, ast.FunctionDef) and self.functions.get(fn.name) is fn and fn.name in self.called:
            params = self.params(fn)
            if self.safe(value, fn, bound | params):
                self.raw.setdefault(fn.name, set()).update(
                    p for p in params if not self.safe(value, fn, bound | (params - {p})))
                return None
        return value.lineno

    def call_values(self, node) -> list:
        """The arguments a call to a module function passes to that function's raw parameters."""
        if not (isinstance(node.func, ast.Name) and node.func.id in self.raw):
            return []
        fn = self.functions[node.func.id]
        positional = [a.arg for a in [*fn.args.posonlyargs, *fn.args.args]]
        named = set(positional) | {a.arg for a in fn.args.kwonlyargs}
        raw = self.raw[node.func.id]
        star = fn.args.vararg is not None and fn.args.vararg.arg in raw
        double_star = fn.args.kwarg is not None and fn.args.kwarg.arg in raw
        values = []
        for i, a in enumerate(node.args):
            # A starred argument can fill any parameter.
            if isinstance(a, ast.Starred) or (positional[i] in raw if i < len(positional) else star):
                values.append(a.value if isinstance(a, ast.Starred) else a)
        for k in node.keywords:
            if k.arg is None or k.arg in raw or (k.arg not in named and double_star):
                values.append(k.value)
        return values

    def sites(self):
        for node in ast.walk(self.tree):
            values = []
            if isinstance(node, ast.JoinedStr) and self.is_html(self.literal(node)):
                values = [v.value for v in node.values if isinstance(v, ast.FormattedValue) and not self.numeric(v)]
            elif isinstance(node, ast.BinOp) and isinstance(node.op, ast.Mod) and self.html_constant(node.left):
                values = node.right.elts if isinstance(node.right, ast.Tuple) else [node.right]
            elif isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute) and node.func.attr == "format" \
                    and self.html_constant(node.func.value):
                values = [*node.args, *(k.value for k in node.keywords)]
            elif isinstance(node, ast.Call):
                values = self.call_values(node)
            for value in values:
                line = self.check_value(value, node)
                if line is not None:
                    yield "dash-unescaped", line

    @staticmethod
    def literal(node: ast.JoinedStr) -> str:
        return "".join(v.value for v in node.values if isinstance(v, ast.Constant))

    def html_constant(self, node) -> bool:
        if isinstance(node, ast.Name):
            node = self.constants.get(node.id)
        return isinstance(node, ast.Constant) and isinstance(node.value, str) and self.is_html(node.value)

    @staticmethod
    def numeric(value: ast.FormattedValue) -> bool:
        spec = value.format_spec
        text = "".join(v.value for v in spec.values if isinstance(v, ast.Constant)) if spec else ""
        return bool(re.search(r"[,_]|[dfeEgG%]$", text))

    def safe(self, node, fn, bound) -> bool:
        if isinstance(node, ast.Constant):
            return True
        if isinstance(node, ast.JoinedStr):
            # An HTML f-string is a site of its own, its values checked where they sit.
            return self.is_html(self.literal(node)) or all(self.numeric(v) or self.safe(v.value, fn, bound) for v in node.values if isinstance(v, ast.FormattedValue))
        if isinstance(node, ast.IfExp):
            return self.safe(node.body, fn, bound) and self.safe(node.orelse, fn, bound)
        if isinstance(node, ast.BoolOp):
            return all(self.safe(v, fn, bound) for v in node.values)
        if isinstance(node, ast.BinOp):
            # `+` joins and `%` formats text; the other operators only take numbers.
            return not isinstance(node.op, (ast.Add, ast.Mod)) or (
                self.safe(node.left, fn, bound) and self.safe(node.right, fn, bound))
        if isinstance(node, (ast.List, ast.Tuple)):
            return all(self.safe(v, fn, bound) for v in node.elts)
        if isinstance(node, ast.Dict):
            return all(self.safe(v, fn, bound) for v in node.values)
        if isinstance(node, ast.DictComp):
            return self.safe(ast.GeneratorExp(elt=node.value, generators=node.generators), fn, bound)
        if isinstance(node, (ast.ListComp, ast.GeneratorExp)):
            inner = bound | {t.id for g in node.generators if self.constant_table(g.iter)
                             for t in ast.walk(g.target) if isinstance(t, ast.Name)}
            return self.safe(node.elt, fn, inner)
        if isinstance(node, ast.Name):
            if f"!{node.id}" in bound:
                return False
            return node.id in bound or node.id.isupper() or self.name_safe(node.id, fn, bound)
        if isinstance(node, ast.Subscript):
            return self.constant_table(node.value) or self.safe(node.value, fn, bound)
        if isinstance(node, ast.Call):
            return self.call_safe(node, fn, bound)
        return False

    def constant_table(self, node) -> bool:
        while isinstance(node, ast.Subscript) or (isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute)
                                                  and node.func.attr == "get" and all(map(self.literal_value, node.args[1:]))):
            node = node.value if isinstance(node, ast.Subscript) else node.func.value
        return (isinstance(node, ast.Name) and node.id.isupper()) or isinstance(node, (ast.Tuple, ast.List, ast.Constant))

    @staticmethod
    def literal_value(node) -> bool:
        return isinstance(node, ast.Constant) or (isinstance(node, ast.Tuple) and all(isinstance(v, ast.Constant) for v in node.elts))

    def call_safe(self, node, fn, bound) -> bool:
        func = node.func
        if isinstance(func, ast.Name) and func.id in self.SAFE_CALLS:
            return True
        if isinstance(func, ast.Name) and func.id in self.SAFE_IF_ARGS:
            return all(self.safe(a, fn, bound) for a in node.args)
        if isinstance(func, ast.Attribute) and func.attr == "join":
            return all(self.safe(a, fn, bound) for a in node.args)
        if isinstance(func, ast.Attribute) and func.attr == "format" and isinstance(func.value, (ast.Constant, ast.Name)):
            return all(self.safe(a, fn, bound) for a in [*node.args, *(k.value for k in node.keywords)])
        if isinstance(func, ast.Attribute) and func.attr in self.TEXT_METHODS:
            return self.safe(func.value, fn, bound)
        if isinstance(func, ast.Name) and func.id in self.functions:
            return self.returns_safe(func.id)
        return False

    def returns_safe(self, name: str) -> bool:
        if name not in self.returns_memo:
            self.returns_memo[name] = True  # a cycle reads as safe; each return is checked on its own pass
            fn = self.functions[name]
            self.returns_memo[name] = all(r.value is None or self.safe(r.value, fn, frozenset())
                                          for r in ast.walk(fn) if isinstance(r, ast.Return))
        return self.returns_memo[name]

    def name_safe(self, name: str, fn, bound) -> bool:
        """A local whose every binding is safe: assignments, `+=`, and `.append`/`.extend` arguments. A parameter or
        a loop variable over data is not."""
        if fn is None or (fn, name) in self.names_seen:
            return fn is not None
        args = fn.args
        if name in {a.arg for a in [*args.posonlyargs, *args.args, *args.kwonlyargs]} | \
                {a.arg for a in (args.vararg, args.kwarg) if a}:
            return False
        self.names_seen.add((fn, name))
        try:
            values, looped = [], False
            for node in ast.walk(fn):
                if isinstance(node, ast.Assign) and any(isinstance(t, ast.Name) and t.id == name for t in node.targets):
                    values.append(node.value)
                elif isinstance(node, (ast.AugAssign, ast.AnnAssign)) and isinstance(node.target, ast.Name) \
                        and node.target.id == name and node.value is not None:
                    values.append(node.value)
                elif isinstance(node, ast.Assign) and isinstance(node.value, ast.Tuple) and any(
                        isinstance(t, ast.Tuple) and len(t.elts) == len(node.value.elts) for t in node.targets):
                    values.extend(v for t in node.targets if isinstance(t, ast.Tuple)
                                  for n, v in zip(t.elts, node.value.elts) if isinstance(n, ast.Name) and n.id == name)
                elif isinstance(node, ast.For) and any(
                        isinstance(t, ast.Name) and t.id == name for t in ast.walk(node.target)):
                    if not self.constant_table(node.iter):
                        return False
                    looped = True
                elif isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute) \
                        and node.func.attr in ("append", "extend") and isinstance(node.func.value, ast.Name) \
                        and node.func.value.id == name:
                    values.extend(node.args)
            return (bool(values) or looped) and all(self.safe(v, fn, bound) for v in values)
        finally:
            self.names_seen.discard((fn, name))


# ---- allowlist and report ----

def read_allowlist(path: Path):
    entries = []
    for number, line in enumerate(path.read_text().split("\n"), 1):
        if not line.strip() or line.startswith("#"):
            continue
        fields = line.split("\t", 3)
        if len(fields) != 4:
            raise ValueError(f"allowlist line {number}: want check, path, reason and source line, tab-separated")
        check, rel, reason, source = fields
        if check not in CHECKS:
            raise ValueError(f"allowlist line {number}: unknown check '{check}'")
        if not reason.strip():
            raise ValueError(f"allowlist line {number}: no reason given; say why this site is safe")
        entries.append((number, check, rel, source.strip()))
    return entries


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", default=str(HERE.parents[1]))
    parser.add_argument("--allowlist", default=str(HERE / "allowlist.txt"))
    options = parser.parse_args()
    root = Path(options.root)
    try:
        entries = read_allowlist(Path(options.allowlist))
    except (OSError, ValueError) as error:
        print(f"conventions: {error}", file=sys.stderr)
        return 2

    findings = set()
    for rel, path, lang in tree_files(root):
        text = path.read_text(errors="replace")
        if lang == "python":
            try:
                found = list(python_findings(rel, ast.parse(text, filename=rel)))
            except SyntaxError as error:
                found = [("parse", error.lineno or 0)]
        else:
            found = shell_findings(rel, text, "hooks" in rel.split("/")[1:-1])
        lines = text.split("\n")
        findings |= {(check, rel, number, lines[number - 1].strip() if 0 < number <= len(lines) else "")
                     for check, number in found}

    # One entry clears one site: identical lines in one file need one entry each.
    used, report = set(), []
    for check, rel, number, source in sorted(findings, key=lambda f: (f[1], f[2], f[0])):
        match = [e for e in entries if (e[1], e[2], e[3]) == (check, rel, source) and e[0] not in used]
        if match:
            used.add(match[0][0])
        else:
            report.append(f"conventions: {check} {rel}:{number}: {source}")
    report += [f"conventions: stale allowlist line {e[0]}: {e[1]} {e[2]}" for e in entries if e[0] not in used]
    print("\n".join(report) if report else "conventions: clean")
    return 1 if report else 0


if __name__ == "__main__":
    sys.exit(main())
