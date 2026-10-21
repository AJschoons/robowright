#!/usr/bin/env python3
"""
role-start — start a hand-launched role session at the model and effort its role expects.

run-launch.sh covers every session a brief starts. The roles a person starts by hand are listed
in ~/.claude/robowright/launch.json under `roles`, each with its default model, effort,
session-name prefix, the `models` key it reads from a project's robowright.json, and an optional
first prompt. With a project, robowright.json's model wins and the session starts in the project
folder; a project with no robowright.json is refused rather than started on defaults, naming any file
that holds its settings under an older name. With no project it starts in the projects root, when that exists:
the working directory is a write grant too.

What the session may write rides in --settings beside the effort (role_grants.py): the projects root, the sessions
root and the accounting root, with every configured repository's git config, hooks and info denied.

Exit codes:
    2  usage    unknown role
    3  shape    a model outside the shape in ../models.json, which run-launch.sh reads too
    4  missing  no launch.json roles, or the project has no robowright.json
    5  grant    a write grant at or above a configured repository, the home directory or this clone

Usage:
    role-start.py <role> [project] [--dry-run]
"""

import argparse
import importlib.util
import json
import os
import re
import shlex
import sys

LAUNCH_CONFIG = os.path.expanduser("~/.claude/robowright/launch.json")
PROJECT_SETTINGS = "robowright.json"

EXIT_USAGE = 2
EXIT_SHAPE = 3
EXIT_MISSING = 4
EXIT_GRANT = 5

HERE = os.path.dirname(os.path.realpath(__file__))
RESOLVER = os.path.join(HERE, "robowright-resolve.py")
sys.path.insert(0, HERE)
import owner_git  # noqa: E402
import role_grants  # noqa: E402
# The model form and the alias ids settings.json pins effort under, shared with run-launch.sh.
MODELS = os.path.join(HERE, "..", "models.json")


def fail(code, message):
    print(f"role-start: {message}", file=sys.stderr)
    sys.exit(code)


def load_roles():
    try:
        with open(LAUNCH_CONFIG) as handle:
            config = json.load(handle)
    except (OSError, ValueError) as error:
        fail(EXIT_MISSING, f"cannot read {LAUNCH_CONFIG}: {error}")
    roles = config.get("roles")
    if not roles:
        fail(EXIT_MISSING, f"{LAUNCH_CONFIG} has no `roles`")
    return config, roles


def load_resolver():
    spec = importlib.util.spec_from_file_location("robowright_resolve", RESOLVER)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def project_model(project_dir, role):
    settings_path = os.path.join(project_dir, PROJECT_SETTINGS)
    try:
        settings = json.loads(owner_git.read_unlinked(settings_path))
    except FileNotFoundError as error:
        print(f"role-start: cannot read {settings_path}: {error}", file=sys.stderr)
        for hint in load_resolver().renamed_settings_hints(project_dir):
            print(f"role-start: {hint}", file=sys.stderr)
        sys.exit(EXIT_MISSING)
    except (OSError, ValueError, RecursionError, owner_git.Unreadable) as error:
        fail(EXIT_MISSING, f"cannot read {settings_path}: {error}")
    key = role["models_key"]
    model = (settings.get("models") or {}).get(key)
    if model:
        return model, f"{settings_path} models.{key}"
    print(f"role-start: {settings_path} has no models.{key}; using {role['model']}", file=sys.stderr)
    return role["model"], None


def load_models():
    with open(MODELS) as handle:
        return json.load(handle)


def check_model(models, model, source):
    # robowright.json is session-writable, and the model is passed as --model.
    if not (isinstance(model, str) and re.fullmatch(models["form"], model)):
        fail(EXIT_SHAPE, f"model from {source} must be opus, sonnet, haiku, fable, or a full claude-* model id of lowercase letters, digits, '.' and '-' (got {model!r})")


def session_settings(models, model, effort, grants):
    model_id = models["ids"].get(model, model)
    return json.dumps(dict({"effortLevel": effort, "modelSettings": {model_id: {"effortLevel": effort}}}, **grants))


def write_grants(cwd):
    try:
        return role_grants.document(with_accounting=True, cwd=cwd)
    except role_grants.Refused as refusal:
        fail(EXIT_GRANT, f"no write grant for this session: {refusal}")


def main():
    parser = argparse.ArgumentParser(prog="role-start")
    parser.add_argument("role")
    parser.add_argument("project", nargs="?")
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()

    config, roles = load_roles()
    role = roles.get(args.role)
    if role is None:
        fail(EXIT_USAGE, f"unknown role '{args.role}' (roles: {', '.join(sorted(roles))})")

    models = load_models()
    model = role["model"]
    source = f"{LAUNCH_CONFIG} roles.{args.role}"
    name = role["name_prefix"]
    project_dir = None
    projects_root = os.path.expanduser(config.get("projects_root") or "")
    if projects_root and os.path.isdir(projects_root):
        project_dir = projects_root
    if args.project:
        project_dir = os.path.join(projects_root, args.project)
    # Checked before anything reads it: the Lead is granted the projects root and can swap a folder in it for a link.
    grants = write_grants(project_dir or os.getcwd())
    if project_dir:
        # The spelling the check passed, which holds no `.` or `..`, with `//` and a trailing `/` dropped.
        project_dir = "/" + "/".join(part for part in project_dir.split("/") if part)
    if args.project:
        model, project_source = project_model(project_dir, role)
        source = project_source or source
        name = f"{role['name_prefix']}-{args.project}"
    check_model(models, model, source)

    effort = role["effort"]
    command = ["claude", "--model", model, "--effort", effort,
               "--settings", session_settings(models, model, effort, grants), "--name", name]
    if role.get("prompt"):
        command.append(role["prompt"])

    if args.dry_run:
        if project_dir:
            print(f"cd {shlex.quote(project_dir)}")
        print(shlex.join(command))
        return
    if project_dir:
        os.chdir(project_dir)
        # A folder above it may have been swapped for a link since the check; the process is in it now, whatever
        # its path names later.
        if os.getcwd() != project_dir:
            fail(EXIT_GRANT, f"{project_dir} changed after it was checked: it now leads to {os.getcwd()}; nothing started")
    os.execvp(command[0], command)


if __name__ == "__main__":
    main()
