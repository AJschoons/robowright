#!/usr/bin/env python3
"""Tests for robowright-resolve.py, written from evidence/U2-behaviors.md before the script existed.

    python3 skills/robowright/scripts/test_robowright_resolve.py

Each test builds a scratch HOME (profile, machine-local hooks, plugins) and real git repos, runs
the resolver as a subprocess, and asserts on stdout or stderr content and the exit code, never
the code alone. On success every stdout line is an absolute path to a file; on refusal stdout is
empty and stderr is one `robowright-resolve: ` line. Three exceptions: a `repo`-only robowright.json adds a
replacement JSON line, `repos` beside `repo` succeeds with one warning line, and a folder whose
settings sit under another file name adds a rename line.
"""

import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

HERE = Path(__file__).resolve().parent
SCRIPT = HERE / "robowright-resolve.py"

EXIT_USAGE = 2
EXIT_MISSING = 4

# Origin rows as BRIEF.md → Read first, item 6 gives them.
BETA_ORIGIN_ROW = "| origin | `example.com/example-org/beta` — match on `beta` |"
GAMMA_ORIGIN_ROW = "| `repo:` origin | `git@example.com-alt:example-org/gamma.git` — match on `example-org/gamma` (an `https://example.com/example-org/gamma` remote is the same repo) |"
ALPHA_TRACKED_ORIGIN_ROW = "| Origin | `git@example.com:example-org/alpha.git` — match on `example-org/alpha` |"
ALPHA_LIVE_ORIGIN_ROW = "| Origin | `git@example.com:example-org/alpha.git` — match on `example-org/alpha.git` |"

APP_ORIGIN = "git@github.com:example/app.git"
APP_ORIGIN_ROW = "| Origin | `git@github.com:example/app.git` — match on `example/app` |"
TABLE_HEAD = ("| | |", "|---|---|")
NO_CLIENTS = ("**Clients**", "", "None in this repository.")

# project-folder mode: robowright.json `repos[]` (robowright-platforms-015-multi-repo, evidence/U1-behaviors.md).
# The origins, and alpha-extra's origin row as its machine-local hook gives it. `alpha` is a prefix of `alpha-extra`.
ALPHA_ORIGIN = "git@example.com:example-org/alpha.git"
ALPHA_EXTRA_ORIGIN = "git@example.com:example-org/alpha-extra.git"
GAMMA_ORIGIN = "git@example.com-alt:example-org/gamma.git"
ALPHA_EXTRA_ORIGIN_ROW = "| Origin | `git@example.com:example-org/alpha-extra.git` — match on `example-org/alpha-extra` |"
SHOP_ORIGIN = "git@github.com:example/shop.git"
APP_ENTRY = {"name": "app", "path": "~/Dev/app", "origin": APP_ORIGIN}
IOS_CLIENT = "- **iOS** — `platform: ios`"
ANDROID_CLIENT = "- **Android** — `platform: android`"
WEB_CLIENT = "- **Web** — `platform: web`"
WATCH_CLIENT = "- **Watch** — `platform: watchos`"
# A settings file from before the rename: every older template carried `delegation` and `models`.
OLD_SETTINGS = {"project": "old", "delegation": "planner", "models": {"lead": "opus"}, "planner_review": False, "review_guide": True}
# The keys an older settings file carried that robowright.json renamed, from the older template against ROBOWRIGHT-TEMPLATE.json.
RENAMED_KEYS = ("`planner_review` → `plan_review`", 'false → "off", true → "finish"', "`review_guide` → `owner_brief`")


class RobowrightResolve(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(os.path.realpath(self.tmp.name))
        self.home = self.root / "home"
        self.home.mkdir()
        self.env = {"HOME": str(self.home), "PATH": "/usr/bin:/bin", "GIT_CONFIG_NOSYSTEM": "1"}
        self.profile = self.home / ".claude/robowright/profile.md"
        self.profile.parent.mkdir(parents=True)
        self.profile.write_text("# Machine profile\n")

    def tearDown(self):
        self.tmp.cleanup()

    # Given

    def git(self, *args):
        subprocess.run(["git", "-c", "user.name=Test", "-c", "user.email=test@example.com", *args],
                       env=self.env, cwd=self.home, check=True, capture_output=True, text=True)

    def given_repo(self, name="app", origin=APP_ORIGIN):
        repo = self.home / "Dev" / name
        repo.mkdir(parents=True)
        self.git("init", "-q", "-b", "main", str(repo))
        self.git("-C", str(repo), "remote", "add", "origin", origin)
        return repo

    def hook_text(self, *section_1, section_2=("None in this repository.",), heading=" ·"):
        return "\n".join(["# Project hook", "", f"## 1{heading} Identity", "", *section_1, "",
                          f"## 2{heading} Preflight extras", "", *section_2, "",
                          f"## 3{heading} Worktree", "", "None in this repository.", ""])

    def given_in_repo_hook(self, repo, text):
        hook = repo / ".claude/robowright/project.md"
        hook.parent.mkdir(parents=True, exist_ok=True)
        hook.write_text(text)
        return hook

    def given_machine_local_hook(self, name, text):
        hook = self.home / ".claude/robowright/projects" / f"{name}.md"
        hook.parent.mkdir(parents=True, exist_ok=True)
        hook.write_text(text)
        return hook

    def plugin_path(self, platform):
        return self.home / ".claude/skills/robowright/plugins" / f"{platform}.md"

    def given_plugin(self, platform, identity=None, base=None):
        plugin = self.plugin_path(platform)
        plugin.parent.mkdir(parents=True, exist_ok=True)
        lines = [identity or f"platform: {platform}"]
        if base:
            lines.append(f"base: {base}")
        plugin.write_text("\n".join([*lines, "", f"# {platform} plugin", ""]))
        return plugin

    def private_plugin_path(self, platform):
        return self.home / ".claude/robowright/plugins" / f"{platform}.md"

    def given_private_plugin(self, platform, identity=None, base=None):
        plugin = self.private_plugin_path(platform)
        plugin.parent.mkdir(parents=True, exist_ok=True)
        lines = [identity or f"platform: {platform}"]
        if base:
            lines.append(f"base: {base}")
        plugin.write_text("\n".join([*lines, "", f"# private {platform} plugin", ""]))
        return plugin

    def given_project_folder(self, settings):
        folder = self.root / "proj"
        folder.mkdir()
        (folder / "robowright.json").write_text(json.dumps(settings))
        return folder

    # When

    def resolve(self, *args):
        return subprocess.run([sys.executable, str(SCRIPT), *map(str, args)], env=self.env, cwd=self.home,
                              capture_output=True, text=True, timeout=30)

    # Then

    def assert_chain(self, result, *expected):
        self.assertEqual(result.returncode, 0, result.stderr)
        lines = result.stdout.splitlines()
        for line in lines:
            self.assertTrue(os.path.isabs(line) and os.path.isfile(line), f"not an absolute file path: {line!r}")
        self.assertEqual([os.path.realpath(line) for line in lines], [os.path.realpath(path) for path in expected])

    def assert_refused(self, result, code, *named):
        self.assertEqual(result.returncode, code, result.stdout + result.stderr)
        self.assertEqual(result.stdout, "")
        lines = result.stderr.splitlines()
        self.assertEqual(len(lines), 1, result.stderr)
        self.assertTrue(lines[0].startswith("robowright-resolve: "), lines[0])
        for name in named:
            self.assertIn(str(name), lines[0])

    # R1 · where the repo comes from

    def test_prints_profile_hook_and_plugin__for_a_checkout_with_one_client(self):
        """/// B1 a checkout's reading chain is profile, in-repo hook, its one plugin — a role starts without its hook or plugin"""
        repo = self.given_repo()
        hook = self.given_in_repo_hook(repo, self.hook_text(*TABLE_HEAD, APP_ORIGIN_ROW, "",
                                                            "**Clients**", "", "- **iOS** — `platform: ios`"))
        ios = self.given_plugin("ios")
        self.assert_chain(self.resolve(repo), self.profile, hook, ios)

    def test_resolves_the_linked_worktree__not_the_main_clone(self):
        """/// B2 a path inside a linked worktree reads that worktree's own hook — a session reads the main clone's stale copy"""
        repo = self.given_repo()
        self.given_in_repo_hook(repo, self.hook_text(*TABLE_HEAD, APP_ORIGIN_ROW, "",
                                                     "**Clients**", "", "- **iOS** — `platform: ios`"))
        self.git("-C", str(repo), "add", ".")
        self.git("-C", str(repo), "commit", "-q", "-m", "hook")
        worktree = self.home / "Dev/app-wt"
        self.git("-C", str(repo), "worktree", "add", "-q", "-b", "wt", str(worktree))
        (worktree / "src").mkdir()
        ios = self.given_plugin("ios")
        self.assert_chain(self.resolve(worktree / "src"),
                          self.profile, worktree / ".claude/robowright/project.md", ios)

    def test_prints_the_checkout_chain__for_a_project_folder_with_one_repos_entry(self):
        """/// B3 a project folder whose `repos` holds one entry prints exactly its checkout's chain, its `~` path expanded — the Planner, who starts in a project folder, gets nothing"""
        repo = self.given_repo()
        hook = self.given_in_repo_hook(repo, self.hook_text(*TABLE_HEAD, APP_ORIGIN_ROW, "",
                                                            "**Clients**", "", "- **iOS** — `platform: ios`"))
        ios = self.given_plugin("ios")
        folder = self.given_project_folder({"repos": [{"name": "app", "path": "~/Dev/app", "origin": APP_ORIGIN}]})
        self.assert_chain(self.resolve(folder), self.profile, hook, ios)

    def test_treats_a_robowright_json_inside_a_checkout_as_the_checkout(self):
        """/// B4 a path inside a git checkout resolves as that checkout even beside a robowright.json — the chain silently switches repos"""
        repo = self.given_repo()
        hook = self.given_in_repo_hook(repo, self.hook_text(*TABLE_HEAD, APP_ORIGIN_ROW, "",
                                                            "**Clients**", "", "- **iOS** — `platform: ios`"))
        other = self.given_repo("other", origin="git@github.com:example/other.git")
        self.given_in_repo_hook(other, self.hook_text(*NO_CLIENTS))
        (repo / "sub").mkdir()
        (repo / "sub/robowright.json").write_text(json.dumps({"repo": "~/Dev/other"}))
        ios = self.given_plugin("ios")
        self.assert_chain(self.resolve(repo / "sub"), self.profile, hook, ios)

    def test_refuses_naming_repos_and_the_template__when_robowright_json_has_neither_repos_nor_repo(self):
        """/// B5 a robowright.json with neither `repos` nor `repo` is exit 4 naming the file, `repos` and ROBOWRIGHT-TEMPLATE.json — a config written before `repos` existed is refused without saying what to write (assumed Q2, Q3)"""
        folder = self.given_project_folder({"delegation": "planner", "models": {"planner": "fable"}})
        self.assert_refused(self.resolve(folder), EXIT_MISSING, folder, "`repos`", "ROBOWRIGHT-TEMPLATE.json")

    def test_is_a_usage_error__for_a_directory_that_is_neither_checkout_nor_project_folder(self):
        """/// B6 a plain directory is exit 2 naming it — a chain printed for no repo at all (assumed Q7)"""
        plain = self.root / "plain"
        plain.mkdir()
        self.assert_refused(self.resolve(plain), EXIT_USAGE, plain)

    def test_names_the_rename_and_the_changed_keys__for_a_folder_whose_settings_sit_under_an_older_name(self):
        """/// 021 B2.1 a folder with no robowright.json but a settings file under another name is still exit 2, and stderr names that file, the rename and the changed keys — the Owner sees only "not a project folder" beside the file that makes it one"""
        folder = self.root / "old"
        folder.mkdir()
        (folder / "settings.json").write_text(json.dumps(OLD_SETTINGS))
        result = self.resolve(folder)
        self.assertEqual(result.returncode, EXIT_USAGE, result.stderr)
        self.assertEqual(result.stdout, "")
        first, *rest = result.stderr.splitlines()
        self.assertEqual(first, f"robowright-resolve: {folder} is neither a git checkout nor a project folder with robowright.json")
        hint = "\n".join(rest)
        for named in (f"{folder}/settings.json", "rename it to robowright.json", *RENAMED_KEYS):
            self.assertIn(named, hint)

    def test_names_no_rename__for_a_folder_whose_only_json_is_not_settings(self):
        """/// 021 B2.2 a folder holding a JSON file without `delegation` and `models` is the one-line usage error — a rename hint for a file that is not settings sends the Owner renaming the wrong thing"""
        folder = self.root / "other"
        folder.mkdir()
        (folder / "package.json").write_text(json.dumps({"name": "other", "models": {}}))
        self.assert_refused(self.resolve(folder), EXIT_USAGE, folder)

    def test_names_no_rename__for_a_folder_whose_only_json_has_delegation_but_no_models(self):
        """/// 021 B2.5 a JSON file with `delegation` and no `models` is not taken for settings — one key alone names a stranger's file as the project's settings"""
        folder = self.root / "other"
        folder.mkdir()
        (folder / "notes.json").write_text(json.dumps({"delegation": "planner"}))
        self.assert_refused(self.resolve(folder), EXIT_USAGE, folder)

    def test_is_a_usage_error__for_a_folder_it_cannot_list(self):
        """/// 021 B2.6 an unreadable folder is still the one-line usage error, exit 2 — the rename search must not turn today's refusal into a traceback"""
        folder = self.root / "locked"
        folder.mkdir()
        folder.chmod(0o000)
        try:
            result = self.resolve(folder)
        finally:
            folder.chmod(0o755)
        self.assert_refused(result, EXIT_USAGE, folder)

    def test_is_a_usage_error__for_a_path_that_does_not_exist(self):
        """/// B7 a missing path is exit 2 naming it — a traceback, or a chain for the cwd (assumed Q7)"""
        missing = self.root / "nowhere"
        self.assert_refused(self.resolve(missing), EXIT_USAGE, missing)

    # R2 · the profile comes first

    def test_refuses_naming_the_profile__before_looking_for_a_hook(self):
        """/// B8 no profile is exit 4 naming its path, ahead of any hook refusal — a role runs without the machine's facts (assumed Q2)"""
        repo = self.given_repo()
        self.profile.unlink()
        self.assert_refused(self.resolve(repo), EXIT_MISSING, self.profile)

    # R3 · which hook

    def test_prefers_the_in_repo_hook__over_a_matching_machine_local_one(self):
        """/// B9 the in-repo hook wins whenever it exists — a stale machine-local copy overrides the repo's own"""
        repo = self.given_repo()
        hook = self.given_in_repo_hook(repo, self.hook_text(*TABLE_HEAD, APP_ORIGIN_ROW, "", *NO_CLIENTS))
        self.given_machine_local_hook("app", self.hook_text(*TABLE_HEAD, APP_ORIGIN_ROW, "", *NO_CLIENTS))
        self.assert_chain(self.resolve(repo), self.profile, hook)

    def test_matches_the_tv_origin_row__through_a_machine_local_hook(self):
        """/// B10 a TV app's origin row matches an https-shaped origin and its `## 1.` section yields its client — the TV app has no chain"""
        repo = self.given_repo("beta", origin="https://example.com/example-org/beta")
        hook = self.given_machine_local_hook("beta", self.hook_text(
            *TABLE_HEAD, BETA_ORIGIN_ROW, "", "**Clients**", "", "- **TV app** — `platform: tv`",
            heading="."))
        tv = self.given_plugin("tv")
        self.assert_chain(self.resolve(repo), self.profile, hook, tv)

    def test_matches_the_gamma_origin_row__through_a_host_alias_origin(self):
        """/// B11 gamma's origin row matches its `example.com-alt:` scp origin — a host alias defeats the match"""
        repo = self.given_repo("gamma", origin=GAMMA_ORIGIN)
        hook = self.given_machine_local_hook("gamma", self.hook_text(*TABLE_HEAD, GAMMA_ORIGIN_ROW, "", *NO_CLIENTS))
        self.assert_chain(self.resolve(repo), self.profile, hook)

    def test_matches_the_tracked_alpha_token__without_dot_git(self):
        """/// B12 `match on example-org/alpha` matches the `.git` origin — the branch's own hook copy is never found"""
        repo = self.given_repo("alpha", origin=ALPHA_ORIGIN)
        hook = self.given_machine_local_hook("alpha", self.hook_text(*TABLE_HEAD, ALPHA_TRACKED_ORIGIN_ROW, "",
                                                                        *NO_CLIENTS))
        self.assert_chain(self.resolve(repo), self.profile, hook)

    def test_matches_the_live_alpha_token__with_dot_git(self):
        """/// B13 `match on example-org/alpha.git` matches the same origin — the live hook copy is never found"""
        repo = self.given_repo("alpha", origin=ALPHA_ORIGIN)
        hook = self.given_machine_local_hook("alpha", self.hook_text(*TABLE_HEAD, ALPHA_LIVE_ORIGIN_ROW, "",
                                                                        *NO_CLIENTS))
        self.assert_chain(self.resolve(repo), self.profile, hook)

    def test_ignores_a_hidden_file__beside_the_matching_machine_local_hook(self):
        """/// B28 a dot-file under projects/ is not a `*.md` candidate — an editor's `.alpha.md` makes the one real hook ambiguous"""
        repo = self.given_repo("alpha", origin=ALPHA_ORIGIN)
        text = self.hook_text(*TABLE_HEAD, ALPHA_TRACKED_ORIGIN_ROW, "", *NO_CLIENTS)
        hook = self.given_machine_local_hook("alpha", text)
        self.given_machine_local_hook(".alpha", text)
        self.assert_chain(self.resolve(repo), self.profile, hook)

    def test_refuses_naming_the_origin__when_there_is_no_machine_local_hooks_directory(self):
        """/// B29 no in-repo hook and no projects/ directory is exit 4 naming the URL — the resolver crashes with a traceback"""
        repo = self.given_repo()
        self.assert_refused(self.resolve(repo), EXIT_MISSING, APP_ORIGIN, repo / ".claude/robowright/project.md")

    def test_refuses_naming_every_location__when_no_alpha_token_matches_the_alpha_extra_origin(self):
        """/// B14 neither alpha token matches the alpha-extra origin, whose name only starts with alpha, so no hook is exit 4 naming URL and every location — alpha-extra runs on alpha's hook (assumed Q1, Q2, Q3, Q4)"""
        repo = self.given_repo("alpha-extra", origin=ALPHA_EXTRA_ORIGIN)
        tracked = self.given_machine_local_hook("alpha", self.hook_text(*TABLE_HEAD, ALPHA_TRACKED_ORIGIN_ROW, "",
                                                                           *NO_CLIENTS))
        live = self.given_machine_local_hook("alpha-live", self.hook_text(*TABLE_HEAD, ALPHA_LIVE_ORIGIN_ROW, "",
                                                                             *NO_CLIENTS))
        self.assert_refused(self.resolve(repo), EXIT_MISSING, ALPHA_EXTRA_ORIGIN,
                            repo / ".claude/robowright/project.md", tracked, live)

    def test_refuses_naming_both_candidates__when_two_machine_local_hooks_match(self):
        """/// B15 two matching machine-local hooks is exit 4 naming the URL and both — the resolver picks one by directory order (assumed Q1, Q2, Q4)"""
        repo = self.given_repo("alpha", origin=ALPHA_ORIGIN)
        tracked = self.given_machine_local_hook("alpha", self.hook_text(*TABLE_HEAD, ALPHA_TRACKED_ORIGIN_ROW, "",
                                                                           *NO_CLIENTS))
        live = self.given_machine_local_hook("alpha-live", self.hook_text(*TABLE_HEAD, ALPHA_LIVE_ORIGIN_ROW, "",
                                                                             *NO_CLIENTS))
        self.assert_refused(self.resolve(repo), EXIT_MISSING, ALPHA_ORIGIN, tracked, live)

    # R4 · which clients

    def test_prints_one_plugin_per_client__in_file_order(self):
        """/// B16 three clients print three plugins in the hook's order, not sorted — a three-client chain reordered or short"""
        repo = self.given_repo()
        hook = self.given_in_repo_hook(repo, self.hook_text(
            *TABLE_HEAD, APP_ORIGIN_ROW, "", "**Clients**", "",
            "- **iOS** — `platform: ios`", "- **Android** — `platform: android`", "- **Web** — `platform: web`"))
        ios, android, web = self.given_plugin("ios"), self.given_plugin("android"), self.given_plugin("web")
        self.assert_chain(self.resolve(repo), self.profile, hook, ios, android, web)

    def test_ends_the_chain_at_the_hook__when_clients_reads_none_in_this_repository(self):
        """/// B17 `None in this repository.` under **Clients** is profile and hook, exit 0 — a repo without a plugin cannot start"""
        repo = self.given_repo()
        hook = self.given_in_repo_hook(repo, self.hook_text(*TABLE_HEAD, APP_ORIGIN_ROW, "", *NO_CLIENTS))
        self.assert_chain(self.resolve(repo), self.profile, hook)

    def test_skips_a_client_row_missing_a_backtick__rather_than_mis_capturing_it(self):
        """/// B18 a row missing its closing backtick is no client at all — a plugin id with a stray character, or a crash"""
        repo = self.given_repo()
        hook = self.given_in_repo_hook(repo, self.hook_text(
            *TABLE_HEAD, APP_ORIGIN_ROW, "", "**Clients**", "",
            "- **iOS** — `platform: ios`", "- **Android** — `platform: android"))
        ios = self.given_plugin("ios")
        self.given_plugin("android")
        self.assert_chain(self.resolve(repo), self.profile, hook, ios)

    def test_ignores_a_client_row_after_the_dotted_section_2_heading(self):
        """/// B19 a `## 2.` heading ends section 1, so a client-shaped row below it is no client — later prose becomes a plugin"""
        repo = self.given_repo()
        hook = self.given_in_repo_hook(repo, self.hook_text(
            *TABLE_HEAD, APP_ORIGIN_ROW, "", "**Clients**", "", "- **iOS** — `platform: ios`",
            section_2=("- **Stray** — `platform: android`",), heading="."))
        ios = self.given_plugin("ios")
        self.given_plugin("android")
        self.assert_chain(self.resolve(repo), self.profile, hook, ios)

    def test_ignores_a_client_row_after_the_middot_section_2_heading(self):
        """/// B20 a `## 2 ·` heading ends section 1, so a client-shaped row below it is no client — later prose becomes a plugin"""
        repo = self.given_repo()
        hook = self.given_in_repo_hook(repo, self.hook_text(
            *TABLE_HEAD, APP_ORIGIN_ROW, "", "**Clients**", "", "- **iOS** — `platform: ios`",
            section_2=("- **Stray** — `platform: android`",)))
        ios = self.given_plugin("ios")
        self.given_plugin("android")
        self.assert_chain(self.resolve(repo), self.profile, hook, ios)

    # R5 · each client's plugin

    def test_refuses_naming_id_and_path__when_a_client_plugin_is_missing(self):
        """/// B21 a client with no plugin on disk is exit 4 naming the id and the path — a chain that silently omits a toolchain (assumed Q2)"""
        repo = self.given_repo()
        self.given_in_repo_hook(repo, self.hook_text(*TABLE_HEAD, APP_ORIGIN_ROW, "",
                                                     "**Clients**", "", "- **Watch** — `platform: watchos`"))
        self.assert_refused(self.resolve(repo), EXIT_MISSING, "watchos", self.plugin_path("watchos"))

    def test_refuses_naming_both_ids__when_a_plugin_declares_another_platform(self):
        """/// B22 ios.md whose first line is `platform: iphone` is exit 4 naming both — a renamed or copied plugin read as the wrong toolchain"""
        repo = self.given_repo()
        self.given_in_repo_hook(repo, self.hook_text(*TABLE_HEAD, APP_ORIGIN_ROW, "",
                                                     "**Clients**", "", "- **iOS** — `platform: ios`"))
        self.given_plugin("ios", identity="platform: iphone")
        self.assert_refused(self.resolve(repo), EXIT_MISSING, "ios", "iphone")

    # R6 · base: one level

    def test_prints_the_base_plugin_first__when_a_plugin_names_one(self):
        """/// B23 `base: ios` puts ios.md before watchos.md — the extension read without the file it adds to"""
        repo = self.given_repo()
        hook = self.given_in_repo_hook(repo, self.hook_text(*TABLE_HEAD, APP_ORIGIN_ROW, "",
                                                            "**Clients**", "", "- **Watch** — `platform: watchos`"))
        watchos = self.given_plugin("watchos", base="ios")
        ios = self.given_plugin("ios")
        self.assert_chain(self.resolve(repo), self.profile, hook, ios, watchos)

    def test_refuses_naming_the_base__when_the_base_plugin_is_missing(self):
        """/// B24 a `base:` with no file is exit 4 naming the base id and path — half an inherited toolchain (assumed Q2)"""
        repo = self.given_repo()
        self.given_in_repo_hook(repo, self.hook_text(*TABLE_HEAD, APP_ORIGIN_ROW, "",
                                                     "**Clients**", "", "- **Watch** — `platform: watchos`"))
        self.given_plugin("watchos", base="ios")
        self.assert_refused(self.resolve(repo), EXIT_MISSING, "ios", self.plugin_path("ios"))

    def test_refuses_naming_both_ids__when_the_base_has_a_base_of_its_own(self):
        """/// B25 a base carrying `base:` is exit 4 naming it and its own base — a two-level chain, or a loop (assumed Q5)"""
        repo = self.given_repo()
        self.given_in_repo_hook(repo, self.hook_text(*TABLE_HEAD, APP_ORIGIN_ROW, "",
                                                     "**Clients**", "", "- **Watch** — `platform: watchos`"))
        self.given_plugin("watchos", base="ios")
        self.given_plugin("ios", base="apple")
        self.given_plugin("apple")
        self.assert_refused(self.resolve(repo), EXIT_MISSING, "ios", "apple")

    # R7 · order and de-duplication

    def test_prints_a_shared_base_once__keeping_client_order(self):
        """/// B26 two clients on one base print it once, then each client in file order — duplicate reads, or a sorted chain"""
        repo = self.given_repo()
        hook = self.given_in_repo_hook(repo, self.hook_text(
            *TABLE_HEAD, APP_ORIGIN_ROW, "", "**Clients**", "",
            "- **Watch** — `platform: watchos`", "- **TV** — `platform: tvos`"))
        watchos = self.given_plugin("watchos", base="ios")
        tvos = self.given_plugin("tvos", base="ios")
        ios = self.given_plugin("ios")
        self.assert_chain(self.resolve(repo), self.profile, hook, ios, watchos, tvos)

    def test_prints_a_client_plugin_once__when_an_earlier_client_used_it_as_base(self):
        """/// B27 a client whose plugin was already printed as a base is not printed again — ios.md read twice"""
        repo = self.given_repo()
        hook = self.given_in_repo_hook(repo, self.hook_text(
            *TABLE_HEAD, APP_ORIGIN_ROW, "", "**Clients**", "",
            "- **Watch** — `platform: watchos`", "- **iOS** — `platform: ios`"))
        watchos = self.given_plugin("watchos", base="ios")
        ios = self.given_plugin("ios")
        self.assert_chain(self.resolve(repo), self.profile, hook, ios, watchos)


    # U1 · refusals: an unbounded §1, a dangling symlink (evidence/U1-behaviors.md)

    # Given · U1

    def hook_text_verbatim(self, *lines):
        return "\n".join([*lines, ""])

    def in_repo_hook_path(self, repo):
        return repo / ".claude/robowright/project.md"

    def machine_local_hook_path(self, file_name):
        return self.home / ".claude/robowright/projects" / file_name

    def given_dangling_symlink(self, link):
        target = self.root / "never-created" / link.name
        link.parent.mkdir(parents=True, exist_ok=True)
        os.symlink(target, link)
        return target

    def given_live_symlink(self, link, text):
        target = self.root / "elsewhere" / link.name
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(text)
        link.parent.mkdir(parents=True, exist_ok=True)
        os.symlink(target, link)
        return link

    # U1-R1 · a §1 with no `## 2` bound

    def test_refuses_naming_the_hook_and_the_missing_bound__when_section_1_has_no_section_2_heading(self):
        """/// B30 a `## 1 ·` hook with no `## 2` heading is exit 4 naming it and `## 2` — the whole file read as §1, or profile + hook with zero clients"""
        repo = self.given_repo()
        hook = self.given_in_repo_hook(repo, self.hook_text_verbatim(
            "# Project hook", "", "## 1 · Identity", "", *TABLE_HEAD, APP_ORIGIN_ROW, "", *NO_CLIENTS, "",
            "Preflight extras: none in this repository."))
        self.assert_refused(self.resolve(repo), EXIT_MISSING, hook, "## 2")

    def test_refuses_stating_the_accepted_forms__when_section_2_heading_uses_another_form(self):
        """/// B31 a `## 2:` heading does not bound a `## 1.` section, and the refusal states `## 2 ·` and `## 2.` — the author cannot tell why a hook is refused, or the regex widens silently (assumed Q3, Q4)"""
        repo = self.given_repo()
        hook = self.given_in_repo_hook(repo, self.hook_text_verbatim(
            "# Project hook", "", "## 1. Identity", "", *TABLE_HEAD, APP_ORIGIN_ROW, "", *NO_CLIENTS, "",
            "## 2: Preflight extras", "", "None in this repository.", "",
            "## 3: Worktree", "", "None in this repository."))
        result = self.resolve(repo)
        self.assert_refused(result, EXIT_MISSING, hook)
        self.assertIn("## 2 ·", result.stderr)
        self.assertIn("## 2.", result.stderr)

    def test_refuses_naming_the_missing_bound__when_the_only_section_2_heading_precedes_section_1(self):
        """/// B32 a `## 2 ·` heading above `## 1 ·` does not bound it, so the hook is exit 4 naming it and `## 2` — sections out of order read as an empty §1"""
        repo = self.given_repo()
        hook = self.given_in_repo_hook(repo, self.hook_text_verbatim(
            "# Project hook", "", "## 2 · Preflight extras", "", "None in this repository.", "",
            "## 1 · Identity", "", *TABLE_HEAD, APP_ORIGIN_ROW, "", "**Clients**", "", "- **iOS** — `platform: ios`"))
        self.given_plugin("ios")
        self.assert_refused(self.resolve(repo), EXIT_MISSING, hook, "## 2")

    def test_refuses_naming_the_unbounded_candidate__even_beside_a_matching_machine_local_hook(self):
        """/// B34 a machine-local candidate with no `## 2` bound is exit 4 naming it, though another hook matches — a broken hook's origin token silently vanishes (assumed Q1)"""
        repo = self.given_repo()
        self.given_machine_local_hook("app", self.hook_text(*TABLE_HEAD, APP_ORIGIN_ROW, "", *NO_CLIENTS))
        other = self.given_machine_local_hook("other", self.hook_text_verbatim(
            "# Project hook", "", "## 1 · Identity", "", *TABLE_HEAD,
            "| Origin | `git@github.com:example/other.git` — match on `example/other` |", "", *NO_CLIENTS))
        self.assert_refused(self.resolve(repo), EXIT_MISSING, other, "## 2")

    # U1-R2 · no `## 1` heading

    def test_refuses_naming_the_hook_and_the_missing_heading__when_it_has_no_section_1_heading(self):
        """/// B33 a hook whose identity heading is `### 1 ·` has no `## 1` and is exit 4 naming it and `## 1` — profile + hook with zero clients"""
        repo = self.given_repo()
        hook = self.given_in_repo_hook(repo, self.hook_text_verbatim(
            "# Project hook", "", "### 1 · Identity", "", *TABLE_HEAD, APP_ORIGIN_ROW, "", *NO_CLIENTS, "",
            "## 2 · Preflight extras", "", "None in this repository.", "",
            "## 3 · Worktree", "", "None in this repository."))
        result = self.resolve(repo)
        self.assert_refused(result, EXIT_MISSING, hook, "## 1")
        self.assertNotIn("## 2", result.stderr)

    def test_refuses_naming_the_candidate_without_section_1__even_beside_a_matching_machine_local_hook(self):
        """/// B35 a machine-local `*.md` with no `## 1` heading is exit 4 naming it, though another hook matches — a malformed hook is silently skipped (assumed Q1)"""
        repo = self.given_repo()
        self.given_machine_local_hook("app", self.hook_text(*TABLE_HEAD, APP_ORIGIN_ROW, "", *NO_CLIENTS))
        notes = self.given_machine_local_hook("notes", self.hook_text_verbatim(
            "# Notes", "", "Hooks for repos on this machine live beside this file."))
        result = self.resolve(repo)
        self.assert_refused(result, EXIT_MISSING, notes, "## 1")
        self.assertNotIn("## 2", result.stderr)

    # U1-R3 · a dangling in-repo hook

    def test_refuses_naming_link_and_target__when_the_in_repo_hook_is_a_dangling_symlink(self):
        """/// B36 a dangling in-repo project.md is exit 4 naming it and its target, not a fall-through — a machine-local copy silently replaces the repo's own hook"""
        repo = self.given_repo()
        self.given_machine_local_hook("app", self.hook_text(*TABLE_HEAD, APP_ORIGIN_ROW, "", *NO_CLIENTS))
        link = self.in_repo_hook_path(repo)
        target = self.given_dangling_symlink(link)
        self.assert_refused(self.resolve(repo), EXIT_MISSING, link, target)

    # U1-R4 · a dangling machine-local candidate

    def test_refuses_naming_the_link__when_a_machine_local_candidate_is_a_dangling_symlink(self):
        """/// B37 a dangling `*.md` under projects/ is exit 4 naming it, before the matching hook is chosen — a broken install link silently drops out of `considered`"""
        repo = self.given_repo()
        self.given_machine_local_hook("app", self.hook_text(*TABLE_HEAD, APP_ORIGIN_ROW, "", *NO_CLIENTS))
        stale = self.machine_local_hook_path("stale.md")
        self.given_dangling_symlink(stale)
        self.assert_refused(self.resolve(repo), EXIT_MISSING, stale)

    def test_ignores_a_hidden_dangling_symlink__beside_the_matching_machine_local_hook(self):
        """/// B38 a dangling `.app.md` under projects/ is not a `*.md` candidate — an editor's dot-file blocks every resolve"""
        repo = self.given_repo()
        hook = self.given_machine_local_hook("app", self.hook_text(*TABLE_HEAD, APP_ORIGIN_ROW, "", *NO_CLIENTS))
        self.given_dangling_symlink(self.machine_local_hook_path(".app.md"))
        self.assert_chain(self.resolve(repo), self.profile, hook)

    def test_ignores_a_dangling_non_markdown_symlink__beside_the_matching_machine_local_hook(self):
        """/// B39 a dangling `notes.txt` under projects/ is not a `*.md` candidate — a stray non-hook file blocks every resolve"""
        repo = self.given_repo()
        hook = self.given_machine_local_hook("app", self.hook_text(*TABLE_HEAD, APP_ORIGIN_ROW, "", *NO_CLIENTS))
        self.given_dangling_symlink(self.machine_local_hook_path("notes.txt"))
        self.assert_chain(self.resolve(repo), self.profile, hook)

    def test_prints_the_in_repo_chain__despite_a_dangling_machine_local_candidate(self):
        """/// B40 with an in-repo hook, a dangling projects/ link is never looked at — one broken machine-local link blocks every repo (assumed Q2)"""
        repo = self.given_repo()
        hook = self.given_in_repo_hook(repo, self.hook_text(*TABLE_HEAD, APP_ORIGIN_ROW, "", *NO_CLIENTS))
        self.given_dangling_symlink(self.machine_local_hook_path("stale.md"))
        self.assert_chain(self.resolve(repo), self.profile, hook)

    # U1-R5 · a dangling plugin

    def test_refuses_naming_link_and_target__when_a_client_plugin_is_a_dangling_symlink(self):
        """/// B41 a dangling plugins/ios.md is exit 4 naming it and its target, not "no plugin for platform" — a broken install link reads as a plugin never written"""
        repo = self.given_repo()
        self.given_in_repo_hook(repo, self.hook_text(*TABLE_HEAD, APP_ORIGIN_ROW, "",
                                                     "**Clients**", "", "- **iOS** — `platform: ios`"))
        link = self.plugin_path("ios")
        target = self.given_dangling_symlink(link)
        result = self.resolve(repo)
        self.assert_refused(result, EXIT_MISSING, link, target)
        self.assertNotIn("no plugin for platform", result.stderr)

    def test_refuses_naming_link_and_target__when_a_base_plugin_is_a_dangling_symlink(self):
        """/// B42 a dangling base plugin is exit 4 naming it and its target, not "no plugin for platform" — a broken base link reads as a missing base"""
        repo = self.given_repo()
        self.given_in_repo_hook(repo, self.hook_text(*TABLE_HEAD, APP_ORIGIN_ROW, "",
                                                     "**Clients**", "", "- **Watch** — `platform: watchos`"))
        self.given_plugin("watchos", base="ios")
        link = self.plugin_path("ios")
        target = self.given_dangling_symlink(link)
        result = self.resolve(repo)
        self.assert_refused(result, EXIT_MISSING, link, target)
        self.assertNotIn("no plugin for platform", result.stderr)

    # U1-R6 · a live symlink still resolves

    def test_prints_the_chain__when_the_in_repo_hook_is_a_live_symlink(self):
        """/// B43 an in-repo project.md linked to a real hook resolves to it — a live symlinked hook is refused as if it were dangling"""
        repo = self.given_repo()
        hook = self.given_live_symlink(self.in_repo_hook_path(repo),
                                       self.hook_text(*TABLE_HEAD, APP_ORIGIN_ROW, "", *NO_CLIENTS))
        self.assert_chain(self.resolve(repo), self.profile, hook)

    def test_prints_the_chain__when_the_matching_machine_local_hook_is_a_live_symlink(self):
        """/// B44 an installed projects/app.md linked to a real hook still matches — every installed machine-local hook is refused or excluded"""
        repo = self.given_repo()
        hook = self.given_live_symlink(self.machine_local_hook_path("app.md"),
                                       self.hook_text(*TABLE_HEAD, APP_ORIGIN_ROW, "", *NO_CLIENTS))
        self.assert_chain(self.resolve(repo), self.profile, hook)

    def test_prints_the_chain__when_a_client_plugin_is_a_live_symlink(self):
        """/// B45 an installed plugins/ios.md linked to a real plugin still resolves — every installed plugin is refused"""
        repo = self.given_repo()
        hook = self.given_in_repo_hook(repo, self.hook_text(*TABLE_HEAD, APP_ORIGIN_ROW, "",
                                                            "**Clients**", "", "- **iOS** — `platform: ios`"))
        ios = self.given_live_symlink(self.plugin_path("ios"), "platform: ios\n\n# ios plugin\n")
        self.assert_chain(self.resolve(repo), self.profile, hook, ios)

    # 015 U1 · project-folder mode reads robowright.json `repos[]`
    # (robowright-platforms-015-multi-repo, evidence/U1-behaviors.md; B3 is R1.1, B5 is R6.1)

    # Given · 015 U1

    def given_checkout(self, name, origin, *clients):
        """A checkout at ~/Dev/<name> whose own hook lists `clients`, or none; returns the hook."""
        repo = self.given_repo(name, origin=origin)
        section_1 = ("**Clients**", "", *clients) if clients else NO_CLIENTS
        return self.given_in_repo_hook(repo, self.hook_text(*section_1))

    def given_checkout_without_origin(self, name):
        """A checkout at ~/Dev/<name> with its own hook and no origin remote."""
        repo = self.home / "Dev" / name
        repo.mkdir(parents=True)
        self.git("init", "-q", "-b", "main", str(repo))
        return self.given_in_repo_hook(repo, self.hook_text(*NO_CLIENTS))

    def settings_file(self, folder):
        return folder / "robowright.json"

    # Then · 015 U1

    def assert_refused_with_replacement(self, result, replacement):
        self.assertEqual(result.returncode, EXIT_MISSING, result.stdout + result.stderr)
        self.assertEqual(result.stdout, "")
        lines = result.stderr.splitlines()
        self.assertTrue(lines and lines[0].startswith("robowright-resolve: "), result.stderr)
        self.assertIn("`repos`", result.stderr)
        self.assertIn("ROBOWRIGHT-TEMPLATE.json", result.stderr)
        self.assertIn(replacement, lines)

    def assert_one_warning(self, result, *named):
        lines = result.stderr.splitlines()
        self.assertEqual(len(lines), 1, result.stderr)
        self.assertTrue(lines[0].startswith("robowright-resolve: "), lines[0])
        for name in named:
            self.assertIn(str(name), lines[0])

    # 015 U1-R1 · one entry prints what checkout mode prints

    def test_resolves_the_enclosing_checkout__when_a_repos_path_is_inside_one(self):
        """/// B46 an absolute `repos` path below a checkout's toplevel resolves that checkout — a path inside a checkout is refused as not one"""
        repo = self.given_repo()
        hook = self.given_in_repo_hook(repo, self.hook_text("**Clients**", "", IOS_CLIENT))
        ios = self.given_plugin("ios")
        (repo / "src").mkdir()
        folder = self.given_project_folder({"repos": [{"name": "app", "path": str(repo / "src"), "origin": APP_ORIGIN}]})
        self.assert_chain(self.resolve(folder), self.profile, hook, ios)

    # 015 U1-R2 · several entries: profile once, then each repo's hook and plugins in list order

    def test_prints_seven_paths_in_list_order__for_three_repos(self):
        """/// B47 alpha, alpha-extra, gamma print the profile, three hooks, then ios, android, web — a Planner reads one repo of the three"""
        self.given_repo("alpha", origin=ALPHA_ORIGIN)
        self.given_repo("alpha-extra", origin=ALPHA_EXTRA_ORIGIN)
        alpha = self.given_machine_local_hook("alpha", self.hook_text(*TABLE_HEAD, ALPHA_LIVE_ORIGIN_ROW, "",
                                                                        *NO_CLIENTS))
        alpha_extra = self.given_machine_local_hook("alpha-extra", self.hook_text(
            *TABLE_HEAD, ALPHA_EXTRA_ORIGIN_ROW, "", *NO_CLIENTS))
        gamma = self.given_checkout("gamma", GAMMA_ORIGIN, IOS_CLIENT, ANDROID_CLIENT, WEB_CLIENT)
        ios, android, web = self.given_plugin("ios"), self.given_plugin("android"), self.given_plugin("web")
        folder = self.given_project_folder({"repos": [
            {"name": "alpha", "path": "~/Dev/alpha", "origin": ALPHA_ORIGIN},
            {"name": "alpha-extra", "path": "~/Dev/alpha-extra", "origin": ALPHA_EXTRA_ORIGIN},
            {"name": "gamma", "path": "~/Dev/gamma", "origin": GAMMA_ORIGIN},
        ]})
        self.assert_chain(self.resolve(folder), self.profile, alpha, alpha_extra, gamma, ios, android, web)

    def test_keeps_list_order__when_it_is_not_alphabetical(self):
        """/// B48 gamma listed before alpha prints gamma's group first — a chain sorted by name or path reorders the project's reading"""
        gamma = self.given_checkout("gamma", GAMMA_ORIGIN, IOS_CLIENT, ANDROID_CLIENT, WEB_CLIENT)
        alpha = self.given_checkout("alpha", ALPHA_ORIGIN)
        ios, android, web = self.given_plugin("ios"), self.given_plugin("android"), self.given_plugin("web")
        folder = self.given_project_folder({"repos": [
            {"name": "gamma", "path": "~/Dev/gamma", "origin": GAMMA_ORIGIN},
            {"name": "alpha", "path": "~/Dev/alpha", "origin": ALPHA_ORIGIN},
        ]})
        self.assert_chain(self.resolve(folder), self.profile, gamma, ios, android, web, alpha)

    def test_prints_a_plugin_two_repos_share_once__at_its_first_position(self):
        """/// B49 ios.md named by both repos prints once, in the first repo's group — a role reads a plugin twice, or late"""
        app = self.given_checkout("app", APP_ORIGIN, IOS_CLIENT)
        shop = self.given_checkout("shop", SHOP_ORIGIN, IOS_CLIENT, ANDROID_CLIENT)
        ios, android = self.given_plugin("ios"), self.given_plugin("android")
        folder = self.given_project_folder({"repos": [
            APP_ENTRY, {"name": "shop", "path": "~/Dev/shop", "origin": SHOP_ORIGIN}]})
        self.assert_chain(self.resolve(folder), self.profile, app, ios, shop, android)

    def test_prints_a_base_first_reached_in_repo_2__ahead_of_the_plugin_naming_it(self):
        """/// B50 repo 2's watchos is preceded by its base ios, inside repo 2's group — the base is hoisted, dropped, or printed after watchos"""
        app = self.given_checkout("app", APP_ORIGIN, WEB_CLIENT)
        shop = self.given_checkout("shop", SHOP_ORIGIN, WATCH_CLIENT)
        web = self.given_plugin("web")
        watchos = self.given_plugin("watchos", base="ios")
        ios = self.given_plugin("ios")
        folder = self.given_project_folder({"repos": [
            APP_ENTRY, {"name": "shop", "path": "~/Dev/shop", "origin": SHOP_ORIGIN}]})
        self.assert_chain(self.resolve(folder), self.profile, app, web, shop, ios, watchos)

    def test_prints_no_plugin__for_a_repo_2_client_already_printed_as_repo_1s_base(self):
        """/// B51 repo 2's iOS client adds nothing once repo 1 printed ios.md as watchos's base — ios.md read twice across repos"""
        app = self.given_checkout("app", APP_ORIGIN, WATCH_CLIENT)
        shop = self.given_checkout("shop", SHOP_ORIGIN, IOS_CLIENT)
        watchos = self.given_plugin("watchos", base="ios")
        ios = self.given_plugin("ios")
        folder = self.given_project_folder({"repos": [
            APP_ENTRY, {"name": "shop", "path": "~/Dev/shop", "origin": SHOP_ORIGIN}]})
        self.assert_chain(self.resolve(folder), self.profile, app, ios, watchos, shop)

    def test_refuses_naming_the_profile__before_resolving_any_repos_hook(self):
        """/// B52 no profile is exit 4 naming it, though neither repo has a hook either — a hook refusal hides that the machine's facts are missing"""
        self.given_repo("app", origin=APP_ORIGIN)
        self.given_repo("shop", origin=SHOP_ORIGIN)
        self.profile.unlink()
        folder = self.given_project_folder({"repos": [
            APP_ENTRY, {"name": "shop", "path": "~/Dev/shop", "origin": SHOP_ORIGIN}]})
        self.assert_refused(self.resolve(folder), EXIT_MISSING, self.profile)

    # 015 U1-R8 · a refusal in any repo refuses the whole chain

    def test_prints_nothing__when_repo_2_has_no_hook(self):
        """/// B53 repo 2 without a hook is exit 4 naming its origin, with stdout empty — a role reads repo 1's partial chain as the whole (assumed Q6)"""
        self.given_checkout("app", APP_ORIGIN, IOS_CLIENT)
        self.given_plugin("ios")
        self.given_repo("shop", origin=SHOP_ORIGIN)
        folder = self.given_project_folder({"repos": [
            APP_ENTRY, {"name": "shop", "path": "~/Dev/shop", "origin": SHOP_ORIGIN}]})
        self.assert_refused(self.resolve(folder), EXIT_MISSING, SHOP_ORIGIN)

    # 015 U1-R3 · `repos` is a non-empty list of objects

    def test_refuses_naming_the_file_and_repos__when_repos_is_empty(self):
        """/// B54 `"repos": []` is exit 4 naming the file and `repos` — a chain of the profile alone (assumed Q2, Q3)"""
        self.given_checkout("app", APP_ORIGIN)
        folder = self.given_project_folder({"repos": []})
        self.assert_refused(self.resolve(folder), EXIT_MISSING, self.settings_file(folder), "`repos`")

    def test_refuses_naming_the_file_and_repos__when_repos_is_one_object_not_a_list(self):
        """/// B55 `repos` written as a bare entry object is exit 4 naming the file and `repos` — the object's keys iterated as entries, or a traceback (assumed Q2, Q3)"""
        self.given_checkout("app", APP_ORIGIN)
        folder = self.given_project_folder({"repos": APP_ENTRY})
        self.assert_refused(self.resolve(folder), EXIT_MISSING, self.settings_file(folder), "`repos`")

    def test_refuses_naming_the_file_and_repos__when_repos_is_a_path_string(self):
        """/// B56 `repos` written as the old path string is exit 4 naming the file and `repos` — its characters iterated as entries, or a traceback (assumed Q2, Q3)"""
        self.given_checkout("app", APP_ORIGIN)
        folder = self.given_project_folder({"repos": "~/Dev/app"})
        self.assert_refused(self.resolve(folder), EXIT_MISSING, self.settings_file(folder), "`repos`")

    def test_refuses_naming_the_index__when_an_entry_is_a_bare_path(self):
        """/// B57 a list entry that is a path string, not an object, is exit 4 naming the file and repos[1] — a traceback on the second entry (assumed Q1, Q3, Q5)"""
        self.given_checkout("app", APP_ORIGIN)
        self.given_checkout("shop", SHOP_ORIGIN)
        folder = self.given_project_folder({"repos": [APP_ENTRY, "~/Dev/shop"]})
        self.assert_refused(self.resolve(folder), EXIT_MISSING, self.settings_file(folder), "repos[1]")

    # 015 U1-R3 · every entry has `name`, `path` and `origin`

    def test_refuses_naming_the_index_and_field__when_an_entry_has_no_name(self):
        """/// B58 a second entry without `name` is exit 4 naming the file, repos[1] and `name` — a repo no brief can name (assumed Q1, Q2)"""
        self.given_checkout("app", APP_ORIGIN)
        self.given_checkout("shop", SHOP_ORIGIN)
        folder = self.given_project_folder({"repos": [APP_ENTRY, {"path": "~/Dev/shop", "origin": SHOP_ORIGIN}]})
        self.assert_refused(self.resolve(folder), EXIT_MISSING, self.settings_file(folder), "repos[1]", "`name`")

    def test_refuses_naming_the_entry_and_field__when_an_entry_has_no_path(self):
        """/// B59 entry storefront without `path` is exit 4 naming the file, repos[1], storefront and `path` — a repo silently dropped from the chain (assumed Q1, Q2)"""
        self.given_checkout("app", APP_ORIGIN)
        self.given_checkout("shop", SHOP_ORIGIN)
        folder = self.given_project_folder({"repos": [APP_ENTRY, {"name": "storefront", "origin": SHOP_ORIGIN}]})
        self.assert_refused(self.resolve(folder), EXIT_MISSING, self.settings_file(folder),
                            "repos[1]", "storefront", "`path`")

    def test_prints_the_checkout_chain__when_an_entry_with_its_own_hook_has_no_origin_key(self):
        """/// B60 entry storefront with no `origin` key, whose checkout has its own hook and no remote, resolves — a never-pushed repo is refused for a check its hook does not need (054 O1)"""
        app = self.given_checkout("app", APP_ORIGIN)
        shop = self.given_checkout_without_origin("shop")
        folder = self.given_project_folder({"repos": [APP_ENTRY, {"name": "storefront", "path": "~/Dev/shop"}]})
        self.assert_chain(self.resolve(folder), self.profile, app, shop)

    # 015 U1-R3 · `name` is a slug, unique in the list

    def test_refuses_naming_the_name__when_it_has_an_uppercase_letter(self):
        """/// B61 name Gamma (a capitalised spelling) is exit 4 naming the file, repos[1], Gamma and `name` — briefs and run.json carry a name no slug check accepts (assumed Q1, Q2)"""
        self.given_checkout("app", APP_ORIGIN)
        self.given_checkout("gamma", GAMMA_ORIGIN)
        folder = self.given_project_folder({"repos": [
            APP_ENTRY, {"name": "Gamma", "path": "~/Dev/gamma", "origin": GAMMA_ORIGIN}]})
        self.assert_refused(self.resolve(folder), EXIT_MISSING, self.settings_file(folder), "repos[1]", "Gamma", "`name`")

    def test_refuses_naming_the_name__when_it_starts_with_a_hyphen(self):
        """/// B62 name -gamma is exit 4 naming the file, repos[1], -gamma and `name` — a name read as a command-line flag (assumed Q1, Q2)"""
        self.given_checkout("app", APP_ORIGIN)
        self.given_checkout("gamma", GAMMA_ORIGIN)
        folder = self.given_project_folder({"repos": [
            APP_ENTRY, {"name": "-gamma", "path": "~/Dev/gamma", "origin": GAMMA_ORIGIN}]})
        self.assert_refused(self.resolve(folder), EXIT_MISSING, self.settings_file(folder), "repos[1]", "-gamma", "`name`")

    def test_refuses_naming_the_name__when_it_has_an_underscore(self):
        """/// B63 name gamma_app is exit 4 naming the file, repos[1], gamma_app and `name` — the slug check only looks at case (assumed Q1, Q2)"""
        self.given_checkout("app", APP_ORIGIN)
        self.given_checkout("gamma", GAMMA_ORIGIN)
        folder = self.given_project_folder({"repos": [
            APP_ENTRY, {"name": "gamma_app", "path": "~/Dev/gamma", "origin": GAMMA_ORIGIN}]})
        self.assert_refused(self.resolve(folder), EXIT_MISSING, self.settings_file(folder),
                            "repos[1]", "gamma_app", "`name`")

    def test_refuses_naming_the_later_entry__when_two_entries_share_a_name(self):
        """/// B64 a second entry also named app is exit 4 naming the file, repos[1], app and `name` — the Lead branches from whichever app it finds first (assumed Q1, Q2, Q4)"""
        self.given_checkout("app", APP_ORIGIN)
        self.given_checkout("shop", SHOP_ORIGIN)
        folder = self.given_project_folder({"repos": [
            APP_ENTRY, {"name": "app", "path": "~/Dev/shop", "origin": SHOP_ORIGIN}]})
        self.assert_refused(self.resolve(folder), EXIT_MISSING, self.settings_file(folder), "repos[1]", "app", "`name`")

    # 015 U1-R3 · `path` is in a git checkout

    def test_refuses_naming_the_entry_and_path__when_path_is_a_plain_directory(self):
        """/// B65 a `path` that exists but is no checkout is exit 4 naming the file, repos[1], storefront and `path` — the chain silently omits a repo (assumed Q1, Q2)"""
        self.given_checkout("app", APP_ORIGIN)
        (self.home / "Dev/shop").mkdir(parents=True)
        folder = self.given_project_folder({"repos": [
            APP_ENTRY, {"name": "storefront", "path": "~/Dev/shop", "origin": SHOP_ORIGIN}]})
        self.assert_refused(self.resolve(folder), EXIT_MISSING, self.settings_file(folder),
                            "repos[1]", "storefront", "`path`")

    def test_refuses_as_missing_not_usage__when_path_does_not_exist(self):
        """/// B66 a `path` that does not exist on this Mac is exit 4, not 2, naming the file, repos[1], storefront and `path` — another machine's path reads as a bad argument (assumed Q1, Q2)"""
        self.given_checkout("app", APP_ORIGIN)
        folder = self.given_project_folder({"repos": [
            APP_ENTRY, {"name": "storefront", "path": "~/Dev/shop", "origin": SHOP_ORIGIN}]})
        self.assert_refused(self.resolve(folder), EXIT_MISSING, self.settings_file(folder),
                            "repos[1]", "storefront", "`path`")

    # 015 U1-R3 · `origin` matches the checkout's origin remote

    def test_refuses_quoting_both_origins__when_a_path_points_at_another_repo(self):
        """/// B67 alpha-extra pointed at ~/Dev/alpha is exit 4 naming the file, repos[1], `origin` and both origins — a swapped path resolves alpha's hook as alpha-extra's (assumed Q1, Q2)"""
        self.given_checkout("alpha", ALPHA_ORIGIN)
        self.given_checkout("alpha-extra", ALPHA_EXTRA_ORIGIN)
        folder = self.given_project_folder({"repos": [
            {"name": "alpha", "path": "~/Dev/alpha", "origin": ALPHA_ORIGIN},
            {"name": "alpha-extra", "path": "~/Dev/alpha", "origin": ALPHA_EXTRA_ORIGIN},
        ]})
        self.assert_refused(self.resolve(folder), EXIT_MISSING, self.settings_file(folder), "repos[1]",
                            "alpha-extra", "`origin`", ALPHA_EXTRA_ORIGIN, ALPHA_ORIGIN)

    def test_refuses_naming_the_written_origin__when_the_checkout_has_no_origin_remote(self):
        """/// B68 a checkout with its own hook and no origin remote is exit 4 naming the file, repos[1], storefront, `origin` and the written origin — an unverifiable checkout resolves unchecked (assumed Q1, Q2, Q9)"""
        self.given_checkout("app", APP_ORIGIN)
        self.given_checkout_without_origin("shop")
        folder = self.given_project_folder({"repos": [
            APP_ENTRY, {"name": "storefront", "path": "~/Dev/shop", "origin": SHOP_ORIGIN}]})
        self.assert_refused(self.resolve(folder), EXIT_MISSING, self.settings_file(folder),
                            "repos[1]", "storefront", "`origin`", SHOP_ORIGIN)

    def test_accepts_an_owner_name_origin_token__against_a_host_alias_remote(self):
        """/// B69 origin example-org/gamma matches the `example.com-alt:` remote — a URL-equality check refuses a host-alias entry"""
        gamma = self.given_checkout("gamma", GAMMA_ORIGIN, IOS_CLIENT)
        ios = self.given_plugin("ios")
        folder = self.given_project_folder({"repos": [{"name": "gamma", "path": "~/Dev/gamma", "origin": "example-org/gamma"}]})
        self.assert_chain(self.resolve(folder), self.profile, gamma, ios)

    # 054 · `origin` is optional for a checkout with its own hook (O1-O3)

    # Given · 054

    def given_checkout_with_machine_local_hook(self, name, origin=None):
        """A checkout at ~/Dev/<name> with no hook of its own, the remote `origin` or none, and a machine-local hook
        matching SHOP_ORIGIN."""
        repo = self.home / "Dev" / name
        repo.mkdir(parents=True)
        self.git("init", "-q", "-b", "main", str(repo))
        if origin:
            self.git("-C", str(repo), "remote", "add", "origin", origin)
        self.given_machine_local_hook(name, self.hook_text(
            *TABLE_HEAD, "| Origin | `git@github.com:example/shop.git` — match on `example/shop` |", "", *NO_CLIENTS))
        return repo

    def test_prints_the_checkout_chain__when_an_entry_with_its_own_hook_has_a_null_origin(self):
        """/// B113 `"origin": null` over a checkout with its own hook and no remote resolves, exit 0 — a local-only repo needs a placeholder remote to be part of a project (054 O1)"""
        shop = self.given_checkout_without_origin("shop")
        folder = self.given_project_folder({"repos": [{"name": "storefront", "path": "~/Dev/shop", "origin": None}]})
        self.assert_chain(self.resolve(folder), self.profile, shop)

    def test_refuses_saying_why_origin_is_needed__when_a_null_origin_checkout_has_a_machine_local_hook(self):
        """/// B114 `"origin": null` over a checkout with no hook of its own and no remote is exit 4 naming the file, repos[0], storefront and `origin` and saying its hook is machine-local — an entry whose hook is found by origin resolves unchecked, or the refusal does not say why origin is required (054 O3)"""
        self.given_checkout_with_machine_local_hook("shop")
        folder = self.given_project_folder({"repos": [{"name": "storefront", "path": "~/Dev/shop", "origin": None}]})
        result = self.resolve(folder)
        self.assert_refused(result, EXIT_MISSING, self.settings_file(folder), "repos[0]", "storefront", "`origin`",
                            "machine-local")

    def test_refuses_an_entry_with_no_origin__when_its_checkout_has_a_remote_but_no_hook_of_its_own(self):
        """/// B115 no `origin` key over a checkout with no hook of its own is exit 4 though its remote matches a machine-local hook — an entry with no origin is checked against nothing and resolves another repo's hook (054 O3, ledger assumption)"""
        self.given_checkout_with_machine_local_hook("shop", origin=SHOP_ORIGIN)
        folder = self.given_project_folder({"repos": [{"name": "storefront", "path": "~/Dev/shop"}]})
        self.assert_refused(self.resolve(folder), EXIT_MISSING, self.settings_file(folder), "repos[0]", "storefront",
                            "`origin`", "machine-local")

    def test_refuses_naming_the_dangling_link__when_a_null_origin_checkouts_own_hook_is_a_dangling_symlink(self):
        """/// B117 `"origin": null` over a checkout whose own hook is a dangling symlink is exit 4 naming the link as dangling — the refusal asks for an `origin` when the fault is the broken link (054 O1, reviews/gate.md F1)"""
        repo = self.home / "Dev/shop"
        repo.mkdir(parents=True)
        self.git("init", "-q", "-b", "main", str(repo))
        link = self.in_repo_hook_path(repo)
        self.given_dangling_symlink(link)
        folder = self.given_project_folder({"repos": [{"name": "storefront", "path": "~/Dev/shop", "origin": None}]})
        self.assert_refused(self.resolve(folder), EXIT_MISSING, link, "dangling")

    def test_refuses_naming_origin_and_null__when_origin_is_neither_a_string_nor_null(self):
        """/// B116 `origin` 7, "", ["x"], {} or false over a checkout with its own hook is exit 4 naming `origin` and saying null is allowed — a falsy or wrong-typed origin reads as null and skips the check (054 O2)"""
        self.given_checkout_without_origin("shop")
        for index, origin in enumerate((7, "", ["x"], {}, False)):
            with self.subTest(origin=origin):
                folder = self.root / f"proj-{index}"
                folder.mkdir()
                (folder / "robowright.json").write_text(json.dumps(
                    {"repos": [{"name": "storefront", "path": "~/Dev/shop", "origin": origin}]}))
                self.assert_refused(self.resolve(folder), EXIT_MISSING, self.settings_file(folder), "repos[0]",
                                    "storefront", "`origin`", "null")

    # 015 U1-R4 · `repo` alone is refused, with a replacement to paste

    def test_refuses_printing_the_replacement__for_todays_robowright_platforms_robowright_json(self):
        """/// B70 `"repo": "~/Dev/alpha"` alone is exit 4 printing the exact alpha entry to paste — the old field keeps working, or the Lead has to work out the new shape (assumed Q2)"""
        self.given_repo("alpha", origin=ALPHA_ORIGIN)
        self.given_machine_local_hook("alpha", self.hook_text(*TABLE_HEAD, ALPHA_LIVE_ORIGIN_ROW, "", *NO_CLIENTS))
        folder = self.given_project_folder({"project": "robowright-platforms", "repo": "~/Dev/alpha",
                                            "delegation": "planner"})
        self.assert_refused_with_replacement(
            self.resolve(folder),
            '{"name": "alpha", "path": "~/Dev/alpha", "origin": "git@example.com:example-org/alpha.git"}')

    def test_refuses_printing_a_lowercased_name__when_the_checkout_basename_is_capitalised(self):
        """/// B71 `"repo": "~/Dev/Gamma"` prints name gamma, the path as written and the host-alias origin — the pasted entry fails the slug check (assumed Q2)"""
        self.given_checkout("Gamma", GAMMA_ORIGIN)
        folder = self.given_project_folder({"repo": "~/Dev/Gamma"})
        self.assert_refused_with_replacement(
            self.resolve(folder),
            '{"name": "gamma", "path": "~/Dev/Gamma", "origin": "git@example.com-alt:example-org/gamma.git"}')

    def test_refuses_naming_repos_and_the_template__when_repo_alone_names_no_checkout(self):
        """/// B72 `repo` alone naming a missing directory is still the R4 refusal naming `repos` and ROBOWRIGHT-TEMPLATE.json — a traceback deriving an origin that is not there (assumed Q2, Q8)"""
        folder = self.given_project_folder({"repo": "~/Dev/gone"})
        result = self.resolve(folder)
        self.assertEqual(result.returncode, EXIT_MISSING, result.stdout + result.stderr)
        self.assertEqual(result.stdout, "")
        self.assertTrue(result.stderr.startswith("robowright-resolve: "), result.stderr)
        self.assertIn("`repos`", result.stderr)
        self.assertIn("ROBOWRIGHT-TEMPLATE.json", result.stderr)
        self.assertNotIn("Traceback", result.stderr)

    def test_refuses_printing_a_null_origin_replacement__when_repo_alone_names_a_remote_less_checkout_with_its_own_hook(self):
        """/// B118 `"repo": "~/Dev/shop"` alone over a checkout with its own hook and no remote is exit 4 printing `{name, path, origin: null}` — the entry 054 made valid is never offered, and the Lead has to work out the new shape (052a D1)"""
        self.given_checkout_without_origin("shop")
        folder = self.given_project_folder({"repo": "~/Dev/shop"})
        self.assert_refused_with_replacement(self.resolve(folder), '{"name": "shop", "path": "~/Dev/shop", "origin": null}')

    def test_refuses_printing_a_null_origin_replacement__when_repo_alone_names_a_checkout_with_its_own_hook_and_a_blank_origin(self):
        """/// B120 `"repo": "~/Dev/shop"` alone over a checkout with its own hook and an origin URL of one space is exit 4 printing `{name, path, origin: null}` — `"origin": ""` is refused when pasted back as `repos` (052a gate F1)"""
        self.given_checkout_without_origin("shop")
        self.git("-C", str(self.home / "Dev" / "shop"), "remote", "add", "origin", " ")
        folder = self.given_project_folder({"repo": "~/Dev/shop"})
        self.assert_refused_with_replacement(self.resolve(folder), '{"name": "shop", "path": "~/Dev/shop", "origin": null}')

    def test_refuses_printing_no_replacement__when_repo_alone_names_a_remote_less_checkout_with_no_hook_of_its_own(self):
        """/// B119 `"repo": "~/Dev/shop"` alone over a checkout with no hook of its own and no remote is exit 4 naming `repos` and the template, with no entry to paste — no `repos` entry would resolve for it, so a printed one is refused when pasted (052a D1)"""
        repo = self.home / "Dev" / "shop"
        repo.mkdir(parents=True)
        self.git("init", "-q", "-b", "main", str(repo))
        folder = self.given_project_folder({"repo": "~/Dev/shop"})
        result = self.resolve(folder)
        self.assertEqual(result.returncode, EXIT_MISSING, result.stdout + result.stderr)
        self.assertIn("`repos`", result.stderr)
        self.assertIn("ROBOWRIGHT-TEMPLATE.json", result.stderr)
        self.assertEqual([line for line in result.stderr.splitlines() if line.startswith("{")], [])

    # 015 U1-R5 · `repos` beside `repo`: `repos` wins, with a warning

    def test_prints_the_repos_chain_and_one_warning__when_repo_is_also_present(self):
        """/// B73 `repos` beside `repo` resolves `repos`, exit 0, with one line saying to delete `repo` — a migrated file resolves the old repo, or migration breaks it (assumed Q7)"""
        hook = self.given_checkout("app", APP_ORIGIN, IOS_CLIENT)
        ios = self.given_plugin("ios")
        self.given_checkout("other", "git@github.com:example/other.git")
        folder = self.given_project_folder({"repos": [APP_ENTRY], "repo": "~/Dev/other"})
        result = self.resolve(folder)
        self.assert_chain(result, self.profile, hook, ios)
        self.assert_one_warning(result, "`repo`")
        self.assertRegex(result.stderr, r"(?i)\bdelete\b")

    def test_refuses_without_falling_back_to_repo__when_repos_beside_it_is_empty(self):
        """/// B74 an empty `repos` beside a valid `repo` is exit 4 naming the file and `repos` — `repo` becomes a silent fallback reader (assumed Q2)"""
        self.given_checkout("app", APP_ORIGIN)
        folder = self.given_project_folder({"repos": [], "repo": "~/Dev/app"})
        result = self.resolve(folder)
        self.assertEqual(result.returncode, EXIT_MISSING, result.stdout + result.stderr)
        self.assertEqual(result.stdout, "")
        self.assertIn(str(self.settings_file(folder)), result.stderr)
        self.assertIn("`repos`", result.stderr)

    def test_refuses_naming_the_name__when_it_ends_in_a_newline(self):
        """/// B75 name "gamma\\n" is exit 4 naming the file, repos[1] and `name` — `$` without `re.M` matches before a trailing newline (reviews/U1-gate.md F1)"""
        self.given_checkout("app", APP_ORIGIN)
        self.given_checkout("gamma", GAMMA_ORIGIN)
        folder = self.given_project_folder({"repos": [
            APP_ENTRY, {"name": "gamma\n", "path": "~/Dev/gamma", "origin": GAMMA_ORIGIN}]})
        result = self.resolve(folder)
        self.assertEqual(result.returncode, EXIT_MISSING, result.stdout + result.stderr)
        self.assertEqual(result.stdout, "")
        self.assertIn(str(self.settings_file(folder)), result.stderr)
        self.assertIn("repos[1]", result.stderr)
        self.assertIn("`name`", result.stderr)

    # 020 U4 · the `repo` suggestion resolves as printed, and a relative `repos[].path` is refused
    # (robowright-platforms-020-review-fixes-2, evidence/U4-behaviors.md; BRIEF D8, D9)

    # When · 020 U4

    def resolve_from(self, cwd, *args):
        return subprocess.run([sys.executable, str(SCRIPT), *map(str, args)], env=self.env, cwd=cwd,
                              capture_output=True, text=True, timeout=30)

    # Then · 020 U4

    def printed_replacement(self, result):
        """The `repos` entry a `repo`-only refusal prints on its second stderr line, parsed."""
        lines = result.stderr.splitlines()
        self.assertEqual(len(lines), 2, result.stderr)
        return json.loads(lines[1])

    def assert_refused_suggesting(self, result, entry):
        self.assertEqual(result.returncode, EXIT_MISSING, result.stdout + result.stderr)
        self.assertEqual(result.stdout, "")
        lines = result.stderr.splitlines()
        self.assertTrue(lines and lines[0].startswith("robowright-resolve: "), result.stderr)
        self.assertIn("`repos`", lines[0])
        self.assertIn("ROBOWRIGHT-TEMPLATE.json", lines[0])
        self.assertEqual(self.printed_replacement(result), entry)

    def assert_refused_as_relative(self, result, settings, value):
        self.assert_refused(result, EXIT_MISSING, settings, "repos[1]", "storefront", value, "~/")
        self.assertRegex(result.stderr, r"(?i)\babsolute\b")

    # 020 U4-R1 · the suggested name is a slug of the checkout's basename

    def test_refuses_suggesting_a_slug_name__when_the_checkout_basename_has_a_dot(self):
        """/// B76 `"repo": "~/Dev/Gamma.iOS"` suggests name gamma-ios — the printed `gamma.ios` fails the slug check it is pasted into (D8 R1)"""
        self.given_checkout("Gamma.iOS", GAMMA_ORIGIN)
        folder = self.given_project_folder({"repo": "~/Dev/Gamma.iOS"})
        self.assert_refused_suggesting(self.resolve(folder),
                                       {"name": "gamma-ios", "path": "~/Dev/Gamma.iOS", "origin": GAMMA_ORIGIN})

    def test_refuses_suggesting_one_hyphen_per_run_and_no_edge_hyphens__when_the_basename_has_runs_and_underscored_ends(self):
        """/// B77 basename `_Gamma..iOS_` suggests name gamma-ios — a hyphen per character or at either end fails the slug check (D8 R1)"""
        self.given_checkout("_Gamma..iOS_", GAMMA_ORIGIN)
        folder = self.given_project_folder({"repo": "~/Dev/_Gamma..iOS_"})
        self.assert_refused_suggesting(self.resolve(folder),
                                       {"name": "gamma-ios", "path": "~/Dev/_Gamma..iOS_", "origin": GAMMA_ORIGIN})

    def test_refuses_without_a_replacement__when_the_basename_slugifies_to_nothing(self):
        """/// B78 basename `___` is the one-line refusal naming `repos` and ROBOWRIGHT-TEMPLATE.json, with no entry printed — a replacement whose name is empty or `___` fails when pasted (D8 R1)"""
        self.given_checkout("___", APP_ORIGIN)
        folder = self.given_project_folder({"repo": "~/Dev/___"})
        self.assert_refused(self.resolve(folder), EXIT_MISSING, self.settings_file(folder),
                            "`repos`", "ROBOWRIGHT-TEMPLATE.json")

    # 020 U4-R2 · the suggested path is as written when absolute or `~/`-rooted, else the toplevel

    def test_refuses_suggesting_the_toplevel_as_path__when_repo_is_relative(self):
        """/// B79 `"repo": "Dev/app"` suggests the checkout's absolute toplevel as `path` — the printed relative path is refused, or resolves against the wrong directory (D8 R2)"""
        repo = self.given_repo()
        folder = self.given_project_folder({"repo": "Dev/app"})
        self.assert_refused_suggesting(self.resolve(folder),
                                       {"name": "app", "path": str(repo), "origin": APP_ORIGIN})

    def test_refuses_suggesting_the_toplevel_not_the_subdirectory__when_a_relative_repo_is_inside_a_checkout(self):
        """/// B80 `"repo": "Dev/app/src"` suggests the toplevel, not src made absolute — the suggestion is not the resolved toplevel D8 R2 names (D8 R2)"""
        repo = self.given_repo()
        (repo / "src").mkdir()
        folder = self.given_project_folder({"repo": "Dev/app/src"})
        self.assert_refused_suggesting(self.resolve(folder),
                                       {"name": "app", "path": str(repo), "origin": APP_ORIGIN})

    def test_refuses_suggesting_the_path_as_written__when_repo_is_absolute_inside_a_checkout(self):
        """/// B81 an absolute `repo` below the toplevel is suggested as written — the Lead's own path is silently rewritten (D8 R2)"""
        repo = self.given_repo()
        (repo / "src").mkdir()
        folder = self.given_project_folder({"repo": str(repo / "src")})
        self.assert_refused_suggesting(self.resolve(folder),
                                       {"name": "app", "path": str(repo / "src"), "origin": APP_ORIGIN})

    def test_refuses_suggesting_the_toplevel__when_repo_is_rooted_at_another_users_home(self):
        """/// B82 `"repo": "~other/app"` suggests the toplevel, not `~other/app` — the printed entry is one D9 refuses (D8 R2, R3 with D9 R3)"""
        repo = self.given_repo("~other/app")
        folder = self.given_project_folder({"repo": "~other/app"})
        self.assert_refused_suggesting(self.resolve_from(self.home / "Dev", folder),
                                       {"name": "app", "path": str(repo), "origin": APP_ORIGIN})

    # 020 U4-R3 · the printed entry, pasted as the only `repos` entry, resolves

    def test_resolves_the_pasted_suggestion_from_the_project_folder__when_repo_was_relative(self):
        """/// B83 the entry printed for `"repo": "Dev/app"`, pasted as `repos`, is exit 0 from the project folder — following the resolver's own advice is refused (D8 R3, assumed Q5)"""
        hook = self.given_checkout("app", APP_ORIGIN)
        folder = self.given_project_folder({"repo": "Dev/app"})
        printed = self.printed_replacement(self.resolve(folder))
        self.settings_file(folder).write_text(json.dumps({"repos": [printed]}))
        self.assert_chain(self.resolve_from(folder, folder), self.profile, hook)

    def test_resolves_the_pasted_suggestion__when_the_checkout_basename_has_a_dot(self):
        """/// B84 the entry printed for `"repo": "~/Dev/Gamma.iOS"`, pasted as `repos`, is exit 0 from the project folder — the pasted name fails the slug check (D8 R3, assumed Q5)"""
        hook = self.given_checkout("Gamma.iOS", GAMMA_ORIGIN)
        folder = self.given_project_folder({"repo": "~/Dev/Gamma.iOS"})
        printed = self.printed_replacement(self.resolve(folder))
        self.settings_file(folder).write_text(json.dumps({"repos": [printed]}))
        self.assert_chain(self.resolve_from(folder, folder), self.profile, hook)

    # 020 U4-R4 · a relative `repos[].path` is refused, even when it names a checkout from the cwd

    def test_refuses_naming_the_entry_and_path__when_path_is_a_bare_relative_name(self):
        """/// B85 path `shop`, a checkout from the working directory, is exit 4 naming repos[1], storefront and the value, saying absolute or `~/` — the chain depends on where the resolver ran (D9 R1, assumed Q2)"""
        self.given_checkout("app", APP_ORIGIN)
        self.given_checkout("shop", SHOP_ORIGIN)
        folder = self.given_project_folder({"repos": [
            APP_ENTRY, {"name": "storefront", "path": "shop", "origin": SHOP_ORIGIN}]})
        self.assert_refused_as_relative(self.resolve_from(self.home / "Dev", folder),
                                        self.settings_file(folder), "shop")

    def test_refuses_naming_the_entry_and_path__when_path_starts_with_dot_slash(self):
        """/// B86 path `./shop` is exit 4 naming repos[1], storefront and the value, saying absolute or `~/` — the chain depends on where the resolver ran (D9 R1, assumed Q2)"""
        self.given_checkout("app", APP_ORIGIN)
        self.given_checkout("shop", SHOP_ORIGIN)
        folder = self.given_project_folder({"repos": [
            APP_ENTRY, {"name": "storefront", "path": "./shop", "origin": SHOP_ORIGIN}]})
        self.assert_refused_as_relative(self.resolve_from(self.home / "Dev", folder),
                                        self.settings_file(folder), "./shop")

    def test_refuses_naming_the_entry_and_path__when_path_starts_with_dot_dot(self):
        """/// B87 path `../Dev/shop` is exit 4 naming repos[1], storefront and the value, saying absolute or `~/` — the chain depends on where the resolver ran (D9 R1, assumed Q2)"""
        self.given_checkout("app", APP_ORIGIN)
        self.given_checkout("shop", SHOP_ORIGIN)
        folder = self.given_project_folder({"repos": [
            APP_ENTRY, {"name": "storefront", "path": "../Dev/shop", "origin": SHOP_ORIGIN}]})
        self.assert_refused_as_relative(self.resolve_from(self.home / "Dev", folder),
                                        self.settings_file(folder), "../Dev/shop")

    def test_refuses_naming_the_entry_and_path__when_path_is_rooted_at_another_users_home(self):
        """/// B88 path `~other/shop` is exit 4 naming repos[1], storefront and the value, saying absolute or `~/` — `~user` passes as `~/`-rooted and resolves per machine or per cwd (D9 R3, assumed Q2)"""
        self.given_checkout("app", APP_ORIGIN)
        self.given_checkout("~other/shop", SHOP_ORIGIN)
        folder = self.given_project_folder({"repos": [
            APP_ENTRY, {"name": "storefront", "path": "~other/shop", "origin": SHOP_ORIGIN}]})
        self.assert_refused_as_relative(self.resolve_from(self.home / "Dev", folder),
                                        self.settings_file(folder), "~other/shop")

    def test_refuses_as_relative_before_looking_for_a_checkout__when_a_relative_path_names_nothing(self):
        """/// B89 path `gone`, naming nothing, gets the relative-path refusal, not the not-a-checkout one — the Lead fixes the directory and is then refused for the path's form (D9 R2, assumed Q2)"""
        self.given_checkout("app", APP_ORIGIN)
        folder = self.given_project_folder({"repos": [
            APP_ENTRY, {"name": "storefront", "path": "gone", "origin": SHOP_ORIGIN}]})
        self.assert_refused_as_relative(self.resolve_from(self.home / "Dev", folder),
                                        self.settings_file(folder), "gone")

    # 020 U4-R6 · `~` passes the relative check (`/abs` is B46, `~/x` is B3)

    def test_resolves_a_path_of_bare_tilde__as_the_home_checkout(self):
        """/// B90 path `~`, with HOME a checkout, resolves exit 0 — the relative check refuses the one `~` form D9 allows (D9 R1)"""
        home_origin = "git@github.com:example/home.git"
        self.git("init", "-q", "-b", "main", str(self.home))
        self.git("-C", str(self.home), "remote", "add", "origin", home_origin)
        hook = self.given_in_repo_hook(self.home, self.hook_text(*NO_CLIENTS))
        folder = self.given_project_folder({"repos": [{"name": "home", "path": "~", "origin": home_origin}]})
        self.assert_chain(self.resolve(folder), self.profile, hook)

    # 025 U2 · a platform plugin is read from ~/.claude/robowright/plugins/ before the clone's
    # (025-public-trims, evidence/U2-behaviors.md; BRIEF U2 P1-P7, D5, D6). P6 — the private
    # directory absent — is every plugin test above: none of their givens creates it.

    # 025 U2-R1 · a private file is the plugin; the clone's is not opened

    def test_prints_the_private_plugin__when_the_clone_has_a_malformed_one(self):
        """/// B91 a private ios.md wins over a clone's ios.md that says `platform: iphone` — the clone's file is read first, or at all (P1)"""
        repo = self.given_repo()
        hook = self.given_in_repo_hook(repo, self.hook_text(*TABLE_HEAD, APP_ORIGIN_ROW, "",
                                                            "**Clients**", "", IOS_CLIENT))
        private_ios = self.given_private_plugin("ios")
        self.given_plugin("ios", identity="platform: iphone")
        self.assert_chain(self.resolve(repo), self.profile, hook, private_ios)

    def test_prints_the_private_plugin_and_no_warning__when_both_have_a_well_formed_one(self):
        """/// B92 with both ios.md files well-formed the private one is printed and stderr is silent — the clone's toolchain read, or a shadowing warning (P1, D5)"""
        repo = self.given_repo()
        hook = self.given_in_repo_hook(repo, self.hook_text(*TABLE_HEAD, APP_ORIGIN_ROW, "",
                                                            "**Clients**", "", IOS_CLIENT))
        private_ios = self.given_private_plugin("ios")
        self.given_plugin("ios")
        result = self.resolve(repo)
        self.assert_chain(result, self.profile, hook, private_ios)
        self.assertEqual(result.stderr, "")

    def test_prints_the_private_plugin__when_the_clones_is_a_dangling_symlink(self):
        """/// B93 a private ios.md wins over a dangling clone ios.md link — a broken clone link refuses a machine that never reads it (P1, assumed Q1)"""
        repo = self.given_repo()
        hook = self.given_in_repo_hook(repo, self.hook_text(*TABLE_HEAD, APP_ORIGIN_ROW, "",
                                                            "**Clients**", "", IOS_CLIENT))
        private_ios = self.given_private_plugin("ios")
        self.given_dangling_symlink(self.plugin_path("ios"))
        self.assert_chain(self.resolve(repo), self.profile, hook, private_ios)

    def test_prints_the_private_plugin__when_it_is_a_live_symlink(self):
        """/// B94 a linked private ios.md pointing at a real plugin resolves to the link — every linked private plugin is refused or skipped (P1, assumed Q2)"""
        repo = self.given_repo()
        hook = self.given_in_repo_hook(repo, self.hook_text(*TABLE_HEAD, APP_ORIGIN_ROW, "",
                                                            "**Clients**", "", IOS_CLIENT))
        private_ios = self.given_live_symlink(self.private_plugin_path("ios"), "platform: ios\n\n# ios plugin\n")
        self.assert_chain(self.resolve(repo), self.profile, hook, private_ios)

    # 025 U2-R2 · no private file → the clone's, exactly as today (P2; P6 is the suite above)

    def test_prints_the_clones_plugin__when_the_private_directory_is_empty(self):
        """/// B95 an empty ~/.claude/robowright/plugins/ leaves the clone's ios.md the plugin — the directory's existence alone refuses or empties the chain (P2)"""
        repo = self.given_repo()
        hook = self.given_in_repo_hook(repo, self.hook_text(*TABLE_HEAD, APP_ORIGIN_ROW, "",
                                                            "**Clients**", "", IOS_CLIENT))
        self.private_plugin_path("ios").parent.mkdir(parents=True)
        ios = self.given_plugin("ios")
        self.assert_chain(self.resolve(repo), self.profile, hook, ios)

    def test_prints_the_clones_plugin__when_the_private_directory_has_only_another_platform(self):
        """/// B96 a private android.md does not hide the clone's ios.md — one private plugin shadows the whole clone (P2)"""
        repo = self.given_repo()
        hook = self.given_in_repo_hook(repo, self.hook_text(*TABLE_HEAD, APP_ORIGIN_ROW, "",
                                                            "**Clients**", "", IOS_CLIENT))
        self.given_private_plugin("android")
        ios = self.given_plugin("ios")
        self.assert_chain(self.resolve(repo), self.profile, hook, ios)

    # 025 U2-R3 · neither → the refusal names both paths

    def test_refuses_naming_both_paths__when_neither_has_the_plugin(self):
        """/// B97 no ios.md at either path is exit 4 naming ios, the private path and the clone's — the user is told of one place to put it and not the other (P3, assumed Q4)"""
        repo = self.given_repo()
        self.given_in_repo_hook(repo, self.hook_text(*TABLE_HEAD, APP_ORIGIN_ROW, "",
                                                     "**Clients**", "", IOS_CLIENT))
        self.assert_refused(self.resolve(repo), EXIT_MISSING,
                            "ios", self.private_plugin_path("ios"), self.plugin_path("ios"))

    # 025 U2-R4 · a dangling private link is refused before the clone's is considered

    def test_refuses_naming_link_and_target__when_the_private_plugin_dangles_beside_a_good_clone_one(self):
        """/// B98 a dangling private ios.md is exit 4 naming it and its target though the clone's ios.md is good — a broken private link silently falls back to the clone's toolchain (P4)"""
        repo = self.given_repo()
        self.given_in_repo_hook(repo, self.hook_text(*TABLE_HEAD, APP_ORIGIN_ROW, "",
                                                     "**Clients**", "", IOS_CLIENT))
        link = self.private_plugin_path("ios")
        target = self.given_dangling_symlink(link)
        self.given_plugin("ios")
        self.assert_refused(self.resolve(repo), EXIT_MISSING, link, target)

    def test_refuses_naming_link_and_target_not_no_plugin__when_the_private_plugin_dangles_alone(self):
        """/// B99 a dangling private ios.md with no clone ios.md names the link and target, not "no plugin for platform" — a broken private link reads as a plugin never written (P4)"""
        repo = self.given_repo()
        self.given_in_repo_hook(repo, self.hook_text(*TABLE_HEAD, APP_ORIGIN_ROW, "",
                                                     "**Clients**", "", IOS_CLIENT))
        link = self.private_plugin_path("ios")
        target = self.given_dangling_symlink(link)
        result = self.resolve(repo)
        self.assert_refused(result, EXIT_MISSING, link, target)
        self.assertNotIn("no plugin for platform", result.stderr)

    # 025 U2-R5 · `base:` resolves through the same order

    def test_prints_the_clones_base_then_the_private_plugin__when_a_private_plugin_bases_on_ios(self):
        """/// B100 a private watchos.md with `base: ios` and only the clone's ios.md prints clone ios then private watchos — a private near-platform cannot build on the clone's base (P5)"""
        repo = self.given_repo()
        hook = self.given_in_repo_hook(repo, self.hook_text(*TABLE_HEAD, APP_ORIGIN_ROW, "",
                                                            "**Clients**", "", WATCH_CLIENT))
        private_watchos = self.given_private_plugin("watchos", base="ios")
        ios = self.given_plugin("ios")
        self.assert_chain(self.resolve(repo), self.profile, hook, ios, private_watchos)

    def test_prints_the_private_base__when_a_clone_plugin_bases_on_a_shadowed_ios(self):
        """/// B101 the clone's watchos.md with `base: ios` reads the private ios.md as its base — a client and its base resolve through different orders (P5, D5)"""
        repo = self.given_repo()
        hook = self.given_in_repo_hook(repo, self.hook_text(*TABLE_HEAD, APP_ORIGIN_ROW, "",
                                                            "**Clients**", "", WATCH_CLIENT))
        watchos = self.given_plugin("watchos", base="ios")
        private_ios = self.given_private_plugin("ios")
        self.given_plugin("ios")
        self.assert_chain(self.resolve(repo), self.profile, hook, private_ios, watchos)

    def test_refuses_naming_both_base_paths__when_neither_has_the_base(self):
        """/// B102 a private watchos.md whose base ios is at neither path is exit 4 naming ios and both its paths — a missing base names one place to put it (P5, P3)"""
        repo = self.given_repo()
        self.given_in_repo_hook(repo, self.hook_text(*TABLE_HEAD, APP_ORIGIN_ROW, "",
                                                     "**Clients**", "", WATCH_CLIENT))
        self.given_private_plugin("watchos", base="ios")
        self.assert_refused(self.resolve(repo), EXIT_MISSING,
                            "ios", self.private_plugin_path("ios"), self.plugin_path("ios"))

    def test_refuses_naming_link_and_target__when_a_private_base_dangles_beside_a_good_clone_one(self):
        """/// B103 a dangling private ios.md under a `base: ios` is exit 4 naming it and its target though the clone's ios.md is good — a broken private base link falls back to the clone's (P5, P4)"""
        repo = self.given_repo()
        self.given_in_repo_hook(repo, self.hook_text(*TABLE_HEAD, APP_ORIGIN_ROW, "",
                                                     "**Clients**", "", WATCH_CLIENT))
        self.given_plugin("watchos", base="ios")
        link = self.private_plugin_path("ios")
        target = self.given_dangling_symlink(link)
        self.given_plugin("ios")
        result = self.resolve(repo)
        self.assert_refused(result, EXIT_MISSING, link, target)
        self.assertNotIn("no plugin for platform", result.stderr)

    # 025 U2-R6 · a misnamed private plugin is refused naming the private path

    def test_refuses_naming_the_private_path_not_the_clones__when_the_private_plugin_is_misnamed(self):
        """/// B104 a private ios.md saying `platform: iphone` is exit 4 naming its own path, not the clone's, though the clone's ios.md is good — the user is sent to fix the wrong file, or the clone's is read instead (P7)"""
        repo = self.given_repo()
        self.given_in_repo_hook(repo, self.hook_text(*TABLE_HEAD, APP_ORIGIN_ROW, "",
                                                     "**Clients**", "", IOS_CLIENT))
        self.given_private_plugin("ios", identity="platform: iphone")
        self.given_plugin("ios")
        result = self.resolve(repo)
        self.assert_refused(result, EXIT_MISSING, self.private_plugin_path("ios"), "ios", "iphone")
        self.assertNotIn(str(self.plugin_path("ios")), result.stderr)

    # 027 U1 · a dangling ~/.claude/robowright/projects or plugins directory link is refused by
    # name where the resolver would read it; a live one is the directory it points at
    # (install-hardening, evidence/U1-behaviors.md; BRIEF U1 H3-H6, D2)

    # Given · 027 U1

    def machine_plugins_dir(self):
        return self.home / ".claude/robowright/plugins"

    def machine_hooks_dir(self):
        return self.home / ".claude/robowright/projects"

    def given_live_directory_link(self, link):
        """`link` made a symlink to an empty real directory elsewhere; returns that directory."""
        target = self.root / "elsewhere-dir" / link.name
        target.mkdir(parents=True)
        link.parent.mkdir(parents=True, exist_ok=True)
        os.symlink(target, link)
        return target

    # Then · 027 U1

    def assert_refused_as_dangling(self, result, link, target):
        self.assert_refused(result, EXIT_MISSING)
        self.assertEqual(result.stderr.splitlines()[0],
                         f"robowright-resolve: {link} is a dangling symlink to {target}")

    # 027 U1-R2 · a dangling plugins/ link is refused where a plugin is read

    def test_refuses_naming_link_and_target__when_the_plugins_directory_is_a_dangling_symlink(self):
        """/// B105 a dangling ~/.claude/robowright/plugins with an ios client is exit 4 naming the link and its target, the clone's good ios.md not printed — a broken private-plugins link silently falls back to the clone's toolchain (H3)"""
        repo = self.given_repo()
        self.given_in_repo_hook(repo, self.hook_text(*TABLE_HEAD, APP_ORIGIN_ROW, "",
                                                     "**Clients**", "", IOS_CLIENT))
        self.given_plugin("ios")
        link = self.machine_plugins_dir()
        target = self.given_dangling_symlink(link)

        self.assert_refused_as_dangling(self.resolve(repo), link, target)

    def test_refuses_naming_the_link_not_no_plugin__when_the_plugins_directory_dangles_and_the_clone_has_none(self):
        """/// B106 a dangling ~/.claude/robowright/plugins with no clone ios.md is exit 4 naming the link and its target, not "no plugin for platform" — a broken private-plugins link reads as a plugin never written (D2)"""
        repo = self.given_repo()
        self.given_in_repo_hook(repo, self.hook_text(*TABLE_HEAD, APP_ORIGIN_ROW, "",
                                                     "**Clients**", "", IOS_CLIENT))
        link = self.machine_plugins_dir()
        target = self.given_dangling_symlink(link)

        result = self.resolve(repo)

        self.assert_refused_as_dangling(result, link, target)
        self.assertNotIn("no plugin for platform", result.stderr)

    # 027 U1-R3 · a dangling projects/ link is refused where a machine-local hook is looked for

    def test_refuses_naming_link_and_target_not_no_hook__when_the_projects_directory_is_a_dangling_symlink(self):
        """/// B107 a dangling ~/.claude/robowright/projects, no in-repo hook and an origin is exit 4 naming the link and its target, not "no hook for origin" — a broken machine-local hooks link reads as a hook never written (H4)"""
        repo = self.given_repo()
        link = self.machine_hooks_dir()
        target = self.given_dangling_symlink(link)

        result = self.resolve(repo)

        self.assert_refused_as_dangling(result, link, target)
        self.assertNotIn("no hook for origin", result.stderr)

    # 027 U1-R4 · a dangling directory link is not looked at where the resolver never reads it

    def test_prints_the_in_repo_chain__despite_a_dangling_projects_directory_link(self):
        """/// B108 with an in-repo hook, a dangling ~/.claude/robowright/projects is never looked at and the chain is profile then hook — one broken machine-local link blocks every repo that carries its own hook (H5, B40's rule)"""
        repo = self.given_repo()
        hook = self.given_in_repo_hook(repo, self.hook_text(*TABLE_HEAD, APP_ORIGIN_ROW, "", *NO_CLIENTS))
        self.given_dangling_symlink(self.machine_hooks_dir())

        self.assert_chain(self.resolve(repo), self.profile, hook)

    def test_prints_the_chain__despite_a_dangling_plugins_directory_link_when_no_client_is_listed(self):
        """/// B109 a hook with no clients resolves profile then hook beside a dangling ~/.claude/robowright/plugins — a broken plugins link blocks repos that read no plugin (Goal, D2)"""
        repo = self.given_repo()
        hook = self.given_in_repo_hook(repo, self.hook_text(*TABLE_HEAD, APP_ORIGIN_ROW, "", *NO_CLIENTS))
        self.given_dangling_symlink(self.machine_plugins_dir())

        self.assert_chain(self.resolve(repo), self.profile, hook)

    def test_refuses_for_the_missing_origin_not_the_link__when_projects_dangles_and_the_repo_has_no_origin(self):
        """/// B110 no in-repo hook and no origin remote is still the no-origin refusal beside a dangling ~/.claude/robowright/projects — the directory is consulted before the resolver knows it needs it (D2)"""
        repo = self.home / "Dev" / "app"
        repo.mkdir(parents=True)
        self.git("init", "-q", "-b", "main", str(repo))
        self.given_dangling_symlink(self.machine_hooks_dir())

        result = self.resolve(repo)

        self.assert_refused(result, EXIT_MISSING, "no origin remote")
        self.assertNotIn("dangling symlink", result.stderr)

    # 027 U1-R5 · a live directory link is the directory it points at

    def test_prints_the_private_plugin__when_the_plugins_directory_is_a_live_symlink(self):
        """/// B111 a ~/.claude/robowright/plugins linked to a directory holding ios.md prints that ios.md over the clone's — a live private-plugins link is refused or skipped (H6, assumed Q2)"""
        repo = self.given_repo()
        hook = self.given_in_repo_hook(repo, self.hook_text(*TABLE_HEAD, APP_ORIGIN_ROW, "",
                                                            "**Clients**", "", IOS_CLIENT))
        self.given_plugin("ios")
        self.given_live_directory_link(self.machine_plugins_dir())
        private_ios = self.given_private_plugin("ios")

        self.assert_chain(self.resolve(repo), self.profile, hook, private_ios)

    def test_prints_the_matching_hook__when_the_projects_directory_is_a_live_symlink(self):
        """/// B112 a ~/.claude/robowright/projects linked to a directory holding the origin's hook resolves to that hook — a live machine-local hooks link is refused or reads as empty (H6)"""
        repo = self.given_repo()
        self.given_live_directory_link(self.machine_hooks_dir())
        hook = self.given_machine_local_hook("app", self.hook_text(*TABLE_HEAD, APP_ORIGIN_ROW, "", *NO_CLIENTS))

        self.assert_chain(self.resolve(repo), self.profile, hook)


if __name__ == "__main__":
    unittest.main()
