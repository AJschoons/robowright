#!/usr/bin/env python3
"""Tests for role-start, written from BEHAVIORS.md before the script existed."""
import json, os, stat, subprocess, sys, tempfile, unittest
from pathlib import Path

SCRIPT = Path(__file__).resolve().parents[2] / "skills/robowright/scripts/role-start.py"
ROLES = {
    "projects_root": "~/Projects",
    "sessions_root": "~/Projects/sessions",
    "roles": {
        "planner": {"models_key": "planner", "model": "fable", "effort": "high", "name_prefix": "planner", "prompt": None},
        "lead": {"models_key": "lead", "model": "opus", "effort": "medium", "name_prefix": "lead", "prompt": "/loop /lead watch"},
    },
}
# A settings file from before the rename: every older template carried `delegation` and `models`.
OLD_SETTINGS = {"project": "old", "delegation": "planner", "models": {"lead": "opus"}, "planner_review": False, "review_guide": True}
# The keys an older settings file carried that robowright.json renamed, from the older template against ROBOWRIGHT-TEMPLATE.json.
RENAMED_KEYS = ("`planner_review` → `plan_review`", 'false → "off", true → "finish"', "`review_guide` → `owner_brief`")


class RoleStart(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        # $TMPDIR sits below a link on macOS, and no grant may (R8.5).
        self.home = Path(os.path.realpath(self.tmp.name))
        self.record = self.home / "claude-call.json"
        bin_dir = self.home / "bin"
        bin_dir.mkdir()
        fake = bin_dir / "claude"
        fake.write_text(
            "#!/usr/bin/env python3\nimport json, os, sys\n"
            f"json.dump({{'argv': sys.argv[1:], 'cwd': os.getcwd()}}, open({str(self.record)!r}, 'w'))\n"
        )
        fake.chmod(fake.stat().st_mode | stat.S_IEXEC)
        self.bin_dir = bin_dir
        # The working directory is a write grant, so a role started from the home directory is refused (R8.2).
        self.work = self.home / "work"
        self.work.mkdir()

    def tearDown(self):
        self.tmp.cleanup()

    def given_launch_config(self, config):
        path = self.home / ".claude/robowright/launch.json"
        path.parent.mkdir(parents=True, exist_ok=True)
        # Every install's launch.json carries `repos` (owner_git.py); the role launcher reads past it.
        path.write_text(json.dumps(dict({"repos": ["~/Code/sample"]}, **config) if isinstance(config, dict) else config))

    def given_project(self, name, robowright):
        folder = self.home / "Projects" / name
        folder.mkdir(parents=True)
        if robowright is not None:
            (folder / "robowright.json").write_text(json.dumps(robowright))
        return folder

    def run_script(self, *args, cwd=None):
        env = {"HOME": str(self.home), "PATH": f"{self.bin_dir}:/usr/bin:/bin"}
        return subprocess.run([sys.executable, str(SCRIPT), *args], env=env, cwd=cwd or self.work, capture_output=True, text=True)

    def call(self):
        return json.loads(self.record.read_text())

    def flag(self, argv, name):
        return argv[argv.index(name) + 1]

    def test_role_without_project_starts_at_role_defaults(self):
        """/// a bare lead start gets the design's model, effort, name and watch prompt — a Lead silently on the default model"""
        self.given_launch_config(ROLES)
        result = self.run_script("lead")
        self.assertEqual(result.returncode, 0, result.stderr)
        argv = self.call()["argv"]
        self.assertEqual(self.flag(argv, "--model"), "opus")
        self.assertEqual(self.flag(argv, "--effort"), "medium")
        self.assertEqual(self.flag(argv, "--name"), "lead")
        self.assertEqual(argv[-1], "/loop /lead watch")
        self.assertEqual(Path(self.call()["cwd"]).resolve(), self.work.resolve())

    def test_role_without_prompt_passes_none(self):
        """/// a promptless role ends on its name — a stray 'None' prompt sent to the Planner"""
        self.given_launch_config(ROLES)
        self.run_script("planner")
        argv = self.call()["argv"]
        self.assertEqual(argv[-2:], ["--name", "planner"])
        self.assertEqual(self.flag(argv, "--model"), "fable")
        self.assertEqual(self.flag(argv, "--effort"), "high")

    def test_project_settings_pick_the_model_name_and_cwd(self):
        """/// robowright.json's model wins and the session is named and rooted for the project — a per-project override ignored"""
        self.given_launch_config(ROLES)
        folder = self.given_project("sample", {"models": {"lead": "sonnet"}})
        self.run_script("lead", "sample")
        call = self.call()
        self.assertEqual(self.flag(call["argv"], "--model"), "sonnet")
        self.assertEqual(self.flag(call["argv"], "--name"), "lead-sample")
        self.assertEqual(Path(call["cwd"]).resolve(), folder.resolve())

    def test_settings_without_the_role_keep_the_default_and_say_so(self):
        """/// a robowright.json missing the role falls back loudly — a silent fallback nobody notices"""
        self.given_launch_config(ROLES)
        self.given_project("sample", {"models": {"planner": "fable"}})
        result = self.run_script("lead", "sample")
        self.assertEqual(self.flag(self.call()["argv"], "--model"), "opus")
        self.assertIn("models.lead", result.stderr)

    def test_project_without_settings_file_is_refused(self):
        """/// a mistyped project never launches on defaults — a Lead watching the wrong folder"""
        self.given_launch_config(ROLES)
        self.given_project("typo", None)
        result = self.run_script("lead", "typo")
        self.assertEqual(result.returncode, 4)
        self.assertIn("typo/robowright.json", result.stderr)
        self.assertFalse(self.record.exists())

    def test_project_with_settings_under_an_older_name_is_refused_naming_the_rename(self):
        """/// 021 B2.3 a folder whose settings sit under another file name is refused as before, and stderr names that file, the rename and the changed keys — the Owner told only that robowright.json is missing beside the file it was renamed from"""
        self.given_launch_config(ROLES)
        folder = self.given_project("old", None)
        (folder / "settings.json").write_text(json.dumps(OLD_SETTINGS))
        result = self.run_script("lead", "old")
        self.assertEqual(result.returncode, 4)
        self.assertIn("old/robowright.json", result.stderr)
        for named in (f"{folder}/settings.json", "rename it to robowright.json", *RENAMED_KEYS):
            self.assertIn(named, result.stderr)
        self.assertFalse(self.record.exists())

    def test_project_without_either_settings_file_names_no_rename(self):
        """/// 021 B2.4 a folder with no settings file under any name gets no rename hint — a hint naming no file sends the Owner looking for one"""
        self.given_launch_config(ROLES)
        self.given_project("typo", None)
        result = self.run_script("lead", "typo")
        self.assertEqual(result.returncode, 4)
        self.assertNotIn("rename it to robowright.json", result.stderr)

    def test_project_folder_it_cannot_list_is_refused_as_before(self):
        """/// 021 B2.7 a project folder that can be entered but not listed is refused exit 4 naming robowright.json, no traceback — the rename search must not change today's refusal"""
        self.given_launch_config(ROLES)
        folder = self.given_project("locked", None)
        folder.chmod(0o300)
        try:
            result = self.run_script("lead", "locked")
        finally:
            folder.chmod(0o755)
        self.assertEqual(result.returncode, 4, result.stderr)
        self.assertIn("locked/robowright.json", result.stderr)
        self.assertNotIn("Traceback", result.stderr)

    def test_effort_rides_on_settings_keyed_by_model_id(self):
        """/// the per-model effort key is set — settings.json's pinned per-model effort overriding --effort"""
        self.given_launch_config(ROLES)
        self.run_script("lead")
        settings = json.loads(self.flag(self.call()["argv"], "--settings"))
        effort = {key: settings[key] for key in ("effortLevel", "modelSettings")}
        self.assertEqual(effort, {"effortLevel": "medium", "modelSettings": {"claude-opus-5-5": {"effortLevel": "medium"}}})
        self.assertEqual(set(settings), {"effortLevel", "modelSettings", "permissions", "sandbox"})

    def model_settings_for(self, alias):
        self.given_launch_config(ROLES)
        self.given_project("sample", {"models": {"lead": alias}})
        self.run_script("lead", "sample")
        return json.loads(self.flag(self.call()["argv"], "--settings"))["modelSettings"]

    def test_sonnet_effort_is_keyed_by_the_current_sonnet_id(self):
        """/// sonnet keys claude-sonnet-5-5 — a stale id whose effort no Sonnet session reads"""
        self.assertEqual(self.model_settings_for("sonnet"), {"claude-sonnet-5-5": {"effortLevel": "medium"}})

    def test_haiku_effort_is_keyed_by_the_current_haiku_id(self):
        """/// haiku keys claude-haiku-5-5 — a stale id whose effort no Haiku session reads"""
        self.assertEqual(self.model_settings_for("haiku"), {"claude-haiku-5-5": {"effortLevel": "medium"}})

    def test_unknown_alias_is_used_as_written(self):
        """/// a full model id passes through — a new model id mangled or dropped"""
        self.given_launch_config(ROLES)
        self.given_project("sample", {"models": {"lead": "claude-x-9"}})
        self.run_script("lead", "sample")
        argv = self.call()["argv"]
        self.assertEqual(self.flag(argv, "--model"), "claude-x-9")
        self.assertEqual(list(json.loads(self.flag(argv, "--settings"))["modelSettings"]), ["claude-x-9"])

    def test_unknown_role_is_a_usage_error(self):
        """/// an unknown role stops with the valid ones listed — launching an unconfigured session"""
        self.given_launch_config(ROLES)
        result = self.run_script("boss")
        self.assertEqual(result.returncode, 2)
        self.assertIn("lead", result.stderr)
        self.assertIn("planner", result.stderr)
        self.assertFalse(self.record.exists())

    def test_dry_run_prints_and_does_not_launch(self):
        """/// --dry-run shows the command and starts nothing — a preview that launches a session"""
        self.given_launch_config(ROLES)
        result = self.run_script("lead", "--dry-run")
        self.assertEqual(result.returncode, 0)
        self.assertIn("claude --model opus --effort medium", result.stdout)
        self.assertFalse(self.record.exists())

    def test_launch_config_without_roles_is_missing_config(self):
        """/// no roles block stops with the file named — a crash or a bare claude start"""
        self.given_launch_config({"schema": 1})
        result = self.run_script("lead")
        self.assertEqual(result.returncode, 4)
        self.assertIn("launch.json", result.stderr)
        self.assertFalse(self.record.exists())


    def test_a_model_outside_the_model_shape_is_refused_by_name(self):
        """/// SI-3 a robowright.json model that closes a JSON string or reads as a flag is refused naming the file, and claude is never called — the value is the session's --model"""
        self.given_launch_config(ROLES)
        for number, model in enumerate(('claude-x","z":{"a', "-x", "opus ")):
            with self.subTest(model=model):
                name = f"p{number}"
                self.given_project(name, {"models": {"planner": model}})
                result = self.run_script("planner", name)
                self.assertNotEqual(result.returncode, 0)
                self.assertIn("robowright.json", result.stderr)
                self.assertIn("model", result.stderr)
                self.assertFalse(self.record.exists())

    def test_the_model_ids_come_from_the_shared_model_definition(self):
        """/// SI-4 role-start keys effort by the id skills/robowright/models.json gives the alias — two copies of the alias map drift, and the launcher reads the same file"""
        shared = json.loads((SCRIPT.parents[1] / "models.json").read_text())
        self.assertEqual(set(shared), {"form", "ids"})
        self.given_launch_config(ROLES)
        self.run_script("lead")
        settings = json.loads(self.flag(self.call()["argv"], "--settings"))
        self.assertEqual(list(settings["modelSettings"]), [shared["ids"]["opus"]])


    # ------------------------------------------------------------ write scope (R8)

    def given_repo(self, relative):
        repo = self.home / relative
        subprocess.run(["git", "init", "-q", str(repo)], check=True, capture_output=True)
        return Path(os.path.realpath(repo))

    def scoped_config(self, **keys):
        return dict(ROLES, repos=["~/Code/sample"], **keys)

    def test_a_role_is_granted_the_three_roots_and_denied_the_repos_git_config(self):
        """/// R8.1: the Lead writes plans, session ledgers and accounting records (ledger C16, C17); a grant wider than those, or a repo's config left open, is a blanket grant over the clones' parent"""
        repo = self.given_repo("Code/sample")
        self.given_launch_config(self.scoped_config())
        self.given_project("sample", {"models": {}})
        result = self.run_script("lead", "sample")
        self.assertEqual(result.returncode, 0, result.stderr)
        settings = json.loads(self.flag(self.call()["argv"], "--settings"))
        home = Path(os.path.realpath(self.home))
        self.assertEqual(settings["permissions"]["additionalDirectories"],
                         [str(home / "Projects"), str(home / "Projects/sessions"), str(home / "Projects/accounting")])
        # The repo's whole git directory (U46: a session writes git only through rw-git).
        git_dir = str(repo / ".git")
        # Each folder Claude Code loads project settings from: the projects root, each folder in it, and one made later.
        projects = home / "Projects"
        folders = [projects] + sorted(c for c in projects.iterdir() if c.is_dir() and not c.name.startswith("."))
        configs = [str(f / n) for f in folders for n in (".claude", ".mcp.json")] + [str(projects / "**/.claude"), str(projects / "**/.mcp.json")]
        # A leaf deny on each granted root: every .git under it, file or folder, at any depth (U46 bound 3).
        leaves = [f"{root}/**/.git" for root in settings["permissions"]["additionalDirectories"]]
        self.assertEqual(settings["sandbox"], {"filesystem": {"denyWrite": [git_dir] + configs + leaves}})
        self.assertEqual(settings["permissions"]["deny"], [f"Edit(/{git_dir}/**)"]
                         + [f"Edit(/{c}/**)" if c.endswith("/.claude") else f"Edit(/{c})" for c in configs]
                         + [rule for leaf in leaves for rule in (f"Edit(/{leaf})", f"Edit(/{leaf}/**)")])

    def test_a_projects_root_over_a_repo_or_home_is_refused(self):
        """/// R8.2: a projects root that holds a configured repo grants the code the Owner runs unsandboxed — the session starts anyway"""
        self.given_repo("Code/sample")
        for root in ("~/Code", "~/"):
            with self.subTest(projects_root=root):
                self.given_launch_config(self.scoped_config(projects_root=root))
                result = self.run_script("lead")
                self.assertEqual(result.returncode, 5, result.stderr)
                self.assertIn("projects root", result.stderr)
                self.assertFalse(self.record.exists())
        with self.subTest(cwd="the home directory, no projects root on disk"):
            self.given_launch_config(self.scoped_config(projects_root="~/Projects"))
            result = self.run_script("lead", cwd=self.home)
            self.assertEqual(result.returncode, 5, result.stderr)
            self.assertIn("working directory", result.stderr)
            self.assertFalse(self.record.exists())
        with self.subTest(cwd="a folder inside the configured repo, no projects root on disk"):
            (self.home / "Code/sample/sub").mkdir(parents=True, exist_ok=True)
            result = self.run_script("lead", cwd=self.home / "Code/sample/sub")
            self.assertEqual(result.returncode, 5, result.stderr)
            self.assertIn("inside the repository", result.stderr)
            self.assertFalse(self.record.exists())

    def test_a_working_directory_or_root_through_a_link_or_dot_dot_is_refused(self):
        """/// R8.5: a link the Lead can plant in the projects root, or `..` after one, makes the working directory, a write grant, whatever it points at — the session starts there"""
        self.given_repo("Code/sample")
        self.given_launch_config(self.scoped_config())
        self.given_project("sample", {"models": {}})
        (self.home / "outside").mkdir()
        (self.home / "outside/robowright.json").write_text(json.dumps({"models": {}}))
        (self.home / "Projects/evil").symlink_to(self.home / "outside")
        (self.home / "Projects/a").mkdir()
        (self.home / "Real/projects/sample").mkdir(parents=True)
        (self.home / "Real/projects/sample/robowright.json").write_text(json.dumps({"models": {}}))
        (self.home / "Up").symlink_to(self.home / "Real")
        cases = {"a project through a link in the projects root": ({}, "evil", str(self.home / "Projects/evil") + " is a link"),
                 "a project spelled with `..`": ({}, "a/../sample", "`..`"),
                 "a projects root below a link": ({"projects_root": "~/Up/projects"}, "sample", str(self.home / "Up") + " is a link")}
        for what, (keys, project, named) in cases.items():
            with self.subTest(what):
                self.given_launch_config(self.scoped_config(**keys))
                result = self.run_script("lead", project)
                self.assertEqual(result.returncode, 5, result.stderr)
                self.assertIn(named, result.stderr)
                self.assertFalse(self.record.exists())

    def test_a_project_swapped_for_a_link_after_the_check_never_starts_there(self):
        """/// R8.6: the Lead is granted the projects root and can swap a folder in it for a link between the check and the start (review 5 F1) — the session would start inside the repository"""
        repo = self.given_repo("Code/sample")
        (repo / "sample").mkdir()
        (repo / "sample/robowright.json").write_text(json.dumps({"models": {}}))
        self.given_launch_config(self.scoped_config())
        folder = self.home / "Projects/a"
        (folder / "sample").mkdir(parents=True)
        (folder / "sample/robowright.json").write_text(json.dumps({"models": {}}))
        # role-start as it runs, but with the swap made once the grant check has passed and robowright.json is read.
        driver = self.home / "swap-after-check.py"
        driver.write_text(
            "import os, runpy, sys\n"
            f"sys.path.insert(0, {str(SCRIPT.parent)!r})\n"
            "import owner_git\n"
            "checked = owner_git.read_unlinked\n"
            "def swapping(path):\n"
            "    result = checked(path)\n"
            f"    os.rename({str(folder)!r}, {str(folder) + '.checked'!r})\n"
            f"    os.symlink({str(repo)!r}, {str(folder)!r})\n"
            "    return result\n"
            "owner_git.read_unlinked = swapping\n"
            f"sys.argv = [{str(SCRIPT)!r}] + sys.argv[1:]\n"
            f"runpy.run_path({str(SCRIPT)!r}, run_name='__main__')\n")
        env = {"HOME": str(self.home), "PATH": f"{self.bin_dir}:/usr/bin:/bin"}
        result = subprocess.run([sys.executable, str(driver), "lead", "a/sample"], env=env, cwd=self.work, capture_output=True, text=True)
        self.assertEqual(result.returncode, 5, result.stderr)
        self.assertIn("changed after it was checked", result.stderr)
        self.assertFalse(self.record.exists())

    def test_with_no_project_the_session_starts_in_the_projects_root(self):
        """/// R8.3: the working directory is a write grant too — a Lead started from the home directory could write all of it"""
        self.given_launch_config(self.scoped_config())
        (self.home / "Projects").mkdir(parents=True)
        result = self.run_script("lead")
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(Path(self.call()["cwd"]).resolve(), (self.home / "Projects").resolve())

    def test_a_role_with_no_well_formed_repos_is_refused(self):
        """/// R8.4: with no `repos`, nothing is denied and nothing marks a clone protected — a Lead granted a projects root over every clone"""
        config = {k: v for k, v in ROLES.items()}
        path = self.home / ".claude/robowright/launch.json"
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(config))
        result = self.run_script("lead")
        self.assertEqual(result.returncode, 5, result.stderr)
        self.assertIn("repos", result.stderr)
        self.assertFalse(self.record.exists())

if __name__ == "__main__":
    unittest.main()
