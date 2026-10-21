#!/usr/bin/env python3
"""
robowright-resolve — print the reading chain for a project folder or a worktree.

A role reads the machine profile, then the repository's project hook, then one platform plugin
per client the hook's section 1 lists, each base plugin ahead of the plugin that names it. The
path is a checkout (its git toplevel is the one repo) or a project folder, whose robowright.json
`repos` lists every repo as {name, path, origin}, `origin` null or absent for a checkout with its
own hook. For a project folder the profile is printed once, then each repo's hook and plugins in
list order; a path already printed is not repeated. The hook is the repo's own
.claude/robowright/project.md, else the one machine-local hook whose origin-match token matches
`git remote get-url origin`, so an entry whose checkout has no hook of its own needs `origin`. A
plugin, and a plugin's base, is the machine's private ~/.claude/robowright/plugins/<platform>.md
if that file exists, else the clone's ~/.claude/skills/robowright/plugins/<platform>.md; a
private file shadows the clone's silently, and the clone's is then never opened. Every stdout
line is an absolute path to a file that exists; anything that cannot be found is refused, never
skipped.

Exit codes:
    2  usage    not one argument, or the path is missing or neither a checkout nor a project folder
                (a folder holding settings under another `.json` name gets one rename line per file after it)
    4  missing  no profile, hook, or plugin, a hook or plugin that does not say what it is,
                a hook whose section 1 has no `## 1` or no `## 2` bound, a dangling hook or plugin
                symlink, a dangling projects/ or plugins/ directory symlink where it is read, or a
                robowright.json whose `repos` is absent, empty, or has an entry with a
                missing field, a non-slug or duplicate `name`, a `path` that is not absolute or
                `~/`-rooted, a `path` outside a checkout, an `origin` that is neither a non-empty
                string nor null, an `origin` that does not match the checkout's, or no `origin` for a
                checkout with no hook of its own. A robowright.json with only the old `repo`
                field is refused with the `repos` entry to paste, on a second stderr line

Usage:
    robowright-resolve.py <path>
"""

import json
import os
import re
import subprocess
import sys

PROFILE = os.path.expanduser("~/.claude/robowright/profile.md")
MACHINE_HOOKS = os.path.expanduser("~/.claude/robowright/projects")
MACHINE_PLUGINS = os.path.expanduser("~/.claude/robowright/plugins")
PLUGINS = os.path.expanduser("~/.claude/skills/robowright/plugins")
IN_REPO_HOOK = os.path.join(".claude", "robowright", "project.md")
PROJECT_SETTINGS = "robowright.json"

EXIT_USAGE = 2
EXIT_MISSING = 4

# Section 1 runs from `## 1 · Identity` or `## 1. Identity` to the section 2 heading.
SECTION_1 = re.compile(r"^##\s*1[.\s·].*?(?=^##\s*2[.\s·])", re.M | re.S)
SECTION_1_HEADING = re.compile(r"^##\s*1[.\s·]", re.M)
CLIENT_ROW = re.compile(r"^-\s+\*\*(?P<name>.+?)\*\*\s+—\s+`platform:\s*(?P<platform>\S+)`\s*$", re.M)
ORIGIN_TOKEN = re.compile(r"match on `(?P<token>[^`]+)`")
PLATFORM_LINE = re.compile(r"^platform:\s*(?P<id>\S+)\s*$")
BASE_LINE = re.compile(r"^base:\s*(?P<id>\S+)\s*$")
REPO_NAME = re.compile(r"^[a-z0-9][a-z0-9-]*$")
REPO_FIELDS = ("name", "path")
TEMPLATE = "ROBOWRIGHT-TEMPLATE.json"
# Every settings template, before and after the file's rename, carries both.
OLD_SETTINGS_KEYS = ("delegation", "models")
RENAMED_KEYS = ('`planner_review` → `plan_review` (false → "off", true → "finish", and the same for a boolean '
                '`plan_review`); `review_guide` → `owner_brief`')


def fail(code, message):
    print(f"robowright-resolve: {message}", file=sys.stderr)
    sys.exit(code)


def git(*args):
    result = subprocess.run(["git", *args], capture_output=True, text=True)
    if result.returncode != 0:
        return None
    return result.stdout.strip()


def checkout_toplevel(path):
    path = os.path.expanduser(path)
    return git("-C", path, "rev-parse", "--show-toplevel") if os.path.isdir(path) else None


# `~user/…` is not rooted: which home it names depends on the account running the resolver.
def is_rooted(path):
    return path.startswith("/") or path == "~" or path.startswith("~/")


def renamed_settings_hints(folder):
    """One line per top-level JSON file in folder that reads as project settings under an older file name."""
    hints = []
    try:
        names = sorted(os.listdir(folder))
    except OSError:
        return hints
    for name in names:
        candidate = os.path.join(folder, name)
        if not name.endswith(".json") or name == PROJECT_SETTINGS or not os.path.isfile(candidate):
            continue
        try:
            with open(candidate) as handle:
                settings = json.load(handle)
        except (OSError, ValueError):
            continue
        if isinstance(settings, dict) and all(key in settings for key in OLD_SETTINGS_KEYS):
            hints.append(f"{candidate} reads as this project's settings under an older name: rename it to "
                         f"{PROJECT_SETTINGS}. Keys renamed since: {RENAMED_KEYS}")
    return hints


def resolve_repos(path):
    if not os.path.exists(path):
        fail(EXIT_USAGE, f"{path} does not exist")
    toplevel = git("-C", path, "rev-parse", "--show-toplevel")
    if toplevel:
        return [toplevel]
    settings_path = os.path.join(path, PROJECT_SETTINGS)
    if not os.path.isfile(settings_path):
        print(f"robowright-resolve: {path} is neither a git checkout nor a project folder with {PROJECT_SETTINGS}",
              file=sys.stderr)
        for hint in renamed_settings_hints(path):
            print(f"robowright-resolve: {hint}", file=sys.stderr)
        sys.exit(EXIT_USAGE)
    try:
        with open(settings_path) as handle:
            settings = json.load(handle)
    except (OSError, ValueError) as error:
        fail(EXIT_MISSING, f"cannot read {settings_path}: {error}")
    if not isinstance(settings, dict):
        settings = {}
    if "repos" in settings:
        toplevels = validated_repos(settings_path, settings["repos"])
        if "repo" in settings:
            print(f"robowright-resolve: {settings_path} has both `repos` and the old `repo`; `repos` is used, "
                  f"delete `repo`", file=sys.stderr)
        return toplevels
    if "repo" in settings:
        refuse_old_repo(settings_path, settings["repo"])
    fail(EXIT_MISSING, f"{settings_path} has no `repos` field; add one as {TEMPLATE} shows")


def validated_repos(settings_path, repos):
    if not isinstance(repos, list) or not repos:
        fail(EXIT_MISSING, f"{settings_path}: `repos` must be a non-empty list of {{name, path, origin}} "
                           f"entries, `origin` null for a checkout with its own hook, as {TEMPLATE} shows")
    names = set()
    toplevels = []
    for index, entry in enumerate(repos):
        label = f"repos[{index}]"
        if not isinstance(entry, dict):
            fail(EXIT_MISSING, f"{settings_path}: {label} is not an object with `name`, `path` and `origin`, or "
                               f"`name` and `path` for a checkout with its own hook")
        if isinstance(entry.get("name"), str) and entry["name"]:
            label = f"{label} ({entry['name']})"
        for field in REPO_FIELDS:
            if not isinstance(entry.get(field), str) or not entry[field]:
                fail(EXIT_MISSING, f"{settings_path}: {label} has no `{field}`")
        name, origin = entry["name"], entry.get("origin")
        if origin is not None and (not isinstance(origin, str) or not origin):
            fail(EXIT_MISSING, f"{settings_path}: {label} `origin` must be a non-empty string, or null for a "
                               f"checkout with its own {IN_REPO_HOOK}")
        if not REPO_NAME.fullmatch(name):
            fail(EXIT_MISSING, f"{settings_path}: {label} `name` is not a slug matching {REPO_NAME.pattern}")
        if name in names:
            fail(EXIT_MISSING, f"{settings_path}: {label} `name` is already used by an earlier entry")
        names.add(name)
        if not is_rooted(entry["path"]):
            fail(EXIT_MISSING, f"{settings_path}: {label} `path` {entry['path']} is relative; "
                               f"write it absolute or `~/`-rooted")
        toplevel = checkout_toplevel(entry["path"])
        if not toplevel:
            fail(EXIT_MISSING, f"{settings_path}: {label} `path` {entry['path']} is not in a git checkout")
        if origin is None:
            refuse_dangling(os.path.join(toplevel, IN_REPO_HOOK))
            if not os.path.isfile(os.path.join(toplevel, IN_REPO_HOOK)):
                fail(EXIT_MISSING, f"{settings_path}: {label} has no `origin`, but {toplevel} has no {IN_REPO_HOOK}: "
                                   f"a hook for it can only be machine-local, found by matching origin")
            toplevels.append(toplevel)
            continue
        url = git("-C", toplevel, "remote", "get-url", "origin")
        if not url:
            fail(EXIT_MISSING, f"{settings_path}: {label} `origin` {origin} cannot be checked: "
                               f"{toplevel} has no origin remote")
        if not origin_matches(url, origin):
            fail(EXIT_MISSING, f"{settings_path}: {label} `origin` {origin} does not match "
                               f"{toplevel}'s origin {url}")
        toplevels.append(toplevel)
    return toplevels


def refuse_old_repo(settings_path, repo):
    toplevel = checkout_toplevel(repo) if isinstance(repo, str) and repo else None
    url = git("-C", toplevel, "remote", "get-url", "origin") if toplevel else None
    message = f"{settings_path} has only the old `repo` field; replace it with `repos`, as {TEMPLATE} shows"
    has_own_hook = bool(toplevel) and os.path.isfile(os.path.join(toplevel, IN_REPO_HOOK))
    if not url and not has_own_hook:
        fail(EXIT_MISSING, message)
    name = re.sub(r"[^a-z0-9-]+", "-", os.path.basename(toplevel).lower()).strip("-")
    if not name:
        fail(EXIT_MISSING, message)
    replacement = {"name": name, "path": repo if is_rooted(repo) else toplevel, "origin": url or None}
    print(f"robowright-resolve: {message}; this entry, in a list:", file=sys.stderr)
    print(json.dumps(replacement), file=sys.stderr)
    sys.exit(EXIT_MISSING)


def section_1(hook):
    text = read(hook)
    match = SECTION_1.search(text)
    if match:
        return match.group(0)
    if not SECTION_1_HEADING.search(text):
        fail(EXIT_MISSING, f"{hook} has no `## 1 · …` or `## 1. …` heading")
    fail(EXIT_MISSING, f"{hook} has a `## 1` heading but no `## 2 · …` or `## 2. …` heading after it to bound §1")


def read(path):
    with open(path) as handle:
        return handle.read()


def refuse_dangling(path):
    if os.path.islink(path) and not os.path.exists(path):
        fail(EXIT_MISSING, f"{path} is a dangling symlink to {os.readlink(path)}")


def origin_matches(url, token):
    for candidate in (url, url[:-len(".git")] if url.endswith(".git") else url):
        if candidate == token or candidate.endswith("/" + token) or candidate.endswith(":" + token):
            return True
    return False


def resolve_hook(repo):
    in_repo = os.path.join(repo, IN_REPO_HOOK)
    refuse_dangling(in_repo)
    if os.path.isfile(in_repo):
        return in_repo
    url = git("-C", repo, "remote", "get-url", "origin")
    if not url:
        fail(EXIT_MISSING, f"no hook at {in_repo}, and {repo} has no origin remote to match a machine-local hook")
    refuse_dangling(MACHINE_HOOKS)
    names = os.listdir(MACHINE_HOOKS) if os.path.isdir(MACHINE_HOOKS) else []
    candidates = sorted(os.path.join(MACHINE_HOOKS, name) for name in names
                        if name.endswith(".md") and not name.startswith("."))
    for candidate in candidates:
        refuse_dangling(candidate)
    considered = [candidate for candidate in candidates if os.path.isfile(candidate)]
    matches = []
    for hook in considered:
        token = ORIGIN_TOKEN.search(section_1(hook))
        if token and origin_matches(url, token.group("token")):
            matches.append(hook)
    if len(matches) == 1:
        return matches[0]
    if matches:
        fail(EXIT_MISSING, f"origin {url} matches more than one hook: {', '.join(matches)}")
    checked = ", ".join([in_repo, *considered]) if considered else f"{in_repo} (no {MACHINE_HOOKS}/*.md)"
    fail(EXIT_MISSING, f"no hook for origin {url}; checked {checked}")


def plugin_path(platform):
    """Return the machine's private plugin file if it has one, else the clone's, refusing a dangling link at either."""
    refuse_dangling(MACHINE_PLUGINS)
    private = os.path.join(MACHINE_PLUGINS, f"{platform}.md")
    refuse_dangling(private)
    if os.path.isfile(private):
        return private
    shipped = os.path.join(PLUGINS, f"{platform}.md")
    refuse_dangling(shipped)
    if not os.path.isfile(shipped):
        fail(EXIT_MISSING, f"no plugin for platform {platform} at {private} or {shipped}")
    return shipped


def plugin_identity(platform):
    """Return (path, base id or None) for a plugin, refusing one that is missing or misnamed."""
    path = plugin_path(platform)
    lines = [line.strip() for line in read(path).splitlines() if line.strip()]
    declared = PLATFORM_LINE.match(lines[0]) if lines else None
    if not declared or declared.group("id") != platform:
        first = lines[0] if lines else "an empty file"
        fail(EXIT_MISSING, f"{path} is plugin {platform} but its first line is {first!r}, not `platform: {platform}`")
    base = BASE_LINE.match(lines[1]) if len(lines) > 1 else None
    return path, base.group("id") if base else None


def plugin_chain(hook):
    chain = []
    for row in CLIENT_ROW.finditer(section_1(hook)):
        platform = row.group("platform")
        path, base = plugin_identity(platform)
        if base:
            base_path, base_of_base = plugin_identity(base)
            if base_of_base:
                fail(EXIT_MISSING, f"plugin {platform} has base {base}, which has base {base_of_base} of its own; "
                                   f"a base plugin carries no `base:`")
            if base_path not in chain:
                chain.append(base_path)
        if path not in chain:
            chain.append(path)
    return chain


def main():
    if len(sys.argv) != 2:
        fail(EXIT_USAGE, "usage: robowright-resolve.py <path>")
    repos = resolve_repos(sys.argv[1])
    if not os.path.isfile(PROFILE):
        fail(EXIT_MISSING, f"no machine profile at {PROFILE}")
    chain = [PROFILE]
    for repo in repos:
        hook = resolve_hook(repo)
        for path in [hook, *plugin_chain(hook)]:
            if path not in chain:
                chain.append(path)
    for path in chain:
        print(path)
    return 0


if __name__ == "__main__":
    sys.exit(main())
