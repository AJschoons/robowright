#!/usr/bin/env python3
"""Tests for install.sh, the one install step: it links every directory under skills/ and every
*.md directly in agents/ into $HOME/.claude, is silent and changes nothing on a second run,
refuses to replace anything that is not a symlink or a live link that resolves outside this clone and every
earlier robowright clone, and `--uninstall` removes only its own links.
Each test's docstring starts with its row in the unit's behaviour table (R1.1 …).

Every test runs `bash <clone>/install.sh` with HOME pointed at a scratch directory, so nothing
here reads or writes the real ~/.claude. The clone is this checkout. Where a row needs a
controlled clone, a synthetic one is built beside the scratch HOME with install.sh copied into it.

    python3 tests/install/test_install.py
"""
import json
import os
import re
import shutil
import stat
import subprocess
import tempfile
import unittest
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
INSTALLER = REPO / "install.sh"
# macOS /bin/bash is 3.2, which is what the repo's shell scripts are written for.
BASH = "/bin/bash" if Path("/bin/bash").exists() else "bash"

# The program a session runs outside its sandbox, linked onto the Owner's PATH (U46 bound 6).
RW_GIT_SOURCE = "skills/robowright/scripts/rw_git.py"
RW_GIT_NOTE = ("rw-git: written into {bin}. Sessions run rw-git outside their sandbox, so no session may write {bin}, "
               "or any folder before it on PATH")

# The synthetic clone's link sources. The decoys beside them are in `make_clone`.
SKILLS = ["drafting", "linting", "reviewing"]
AGENTS = ["checker.md", "summarizer.md"]


def write(path, text):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text)


def links_in(directory):
    """name -> link text for every symlink directly in `directory`; {} when it does not exist."""
    if not os.path.isdir(directory):
        return {}
    return {entry.name: os.readlink(entry.path) for entry in os.scandir(directory) if entry.is_symlink()}


def symlinks_under(top):
    """Every symlink at any depth under `top`, relative to it, following none of them."""
    found = []
    for dirpath, dirnames, filenames in os.walk(top):
        for name in dirnames + filenames:
            path = os.path.join(dirpath, name)
            if os.path.islink(path):
                found.append(os.path.relpath(path, top))
    return sorted(found)


def tree(top):
    """relpath -> (kind, link text or file bytes, inode, lstat mtime_ns) for everything under
    `top`, following no link: equal snapshots mean nothing was made, removed, rewritten or
    re-created."""
    entries = {}
    for dirpath, dirnames, filenames in os.walk(top):
        for name in dirnames + filenames:
            path = os.path.join(dirpath, name)
            info = os.lstat(path)
            if stat.S_ISLNK(info.st_mode):
                kind, body = "link", os.readlink(path)
            elif stat.S_ISDIR(info.st_mode):
                kind, body = "dir", None
            elif stat.S_ISREG(info.st_mode):
                kind, body = "file", Path(path).read_bytes()
            else:
                kind, body = "other", None
            entries[os.path.relpath(path, top)] = (kind, body, info.st_ino, info.st_mtime_ns)
    return entries


def clone_skills(clone):
    """The rule's own definition over a real tree: every directory directly in skills/."""
    return sorted(p.name for p in (clone / "skills").iterdir() if p.is_dir())


def clone_agents(clone):
    """The rule's own definition over a real tree: every *.md file directly in agents/."""
    return sorted(p.name for p in (clone / "agents").iterdir() if p.is_file() and p.suffix == ".md")


class InstallCase(unittest.TestCase):
    """A scratch root, resolved so that the paths the script prints are the paths compared,
    holding HOME at <root>/home and any synthetic clone beside it."""

    def setUp(self):
        self.root = Path(os.path.realpath(tempfile.mkdtemp(prefix="install-test.")))
        # rmtree unlinks symlinks rather than following them, so links into the real clone are safe.
        self.addCleanup(shutil.rmtree, self.root)
        self.home = self.root / "home"
        self.home.mkdir()
        # Owner-only floor: the real HOME is never the one under test.
        self.assertNotEqual(os.path.realpath(self.home), os.path.realpath(os.path.expanduser("~")))
        self.claude = self.home / ".claude"
        self.skills_dir = self.claude / "skills"
        self.agents_dir = self.claude / "agents"
        self.bin_dir = self.home / ".local" / "bin"
        self.rw_git = self.bin_dir / "rw-git"

    def python3(self):
        done = subprocess.run(["python3", "-c", "import sys; print(sys.executable)"], capture_output=True, text=True,
                              env={**os.environ, "HOME": str(self.home)}, check=True)
        return done.stdout.strip()

    def make_clone(self, name="checkout"):
        clone = self.root / name
        for skill in SKILLS:
            write(clone / "skills" / skill / "SKILL.md", f"# {skill}\n")
        for agent in AGENTS:
            write(clone / "agents" / agent, f"# {agent}\n")
        # Decoys: none of these is a directory in skills/ or a *.md directly in agents/.
        write(clone / "skills/NOTES.txt", "notes\n")
        write(clone / "agents/roster.json", "{}\n")
        write(clone / "agents/drafts/draft.md", "# draft\n")
        write(clone / "README.md", "# readme\n")
        write(clone / "tools/helper/run.py", "")
        write(clone / "tests/suite/test_suite.py", "")
        write(clone / "examples/demo/README.md", "")
        write(clone / ".claude/settings.json", "{}\n")
        # Before the unit exists there is nothing to copy; bash then exits 127 and every Then fails.
        if INSTALLER.exists():
            shutil.copy2(INSTALLER, clone / "install.sh")
        return clone

    def run_installer(self, clone, *args, cwd=None, script=None, env=None):
        script = script if script is not None else clone / "install.sh"
        return subprocess.run(
            [BASH, str(script), *args],
            cwd=str(cwd if cwd is not None else clone),
            env={**os.environ, **(env or {}), "HOME": str(self.home)},
            capture_output=True,
            text=True,
            timeout=60,
        )

    def install_ok(self, clone):
        result = self.run_installer(clone)
        self.assertEqual(result.returncode, 0, f"precondition: install failed\n{result.stderr}")
        return result

    def uninstall_ok(self, clone):
        result = self.run_installer(clone, "--uninstall")
        self.assertEqual(result.returncode, 0, f"precondition: uninstall failed\n{result.stderr}")
        return result

    def assertNamesPath(self, path, stderr):
        """stderr names `path` itself, not only something under it."""
        self.assertRegex(stderr, re.escape(str(path)) + r"(?![/\w.-])")

    def synthetic_links(self, clone):
        return (
            {skill: str(clone / "skills" / skill) for skill in SKILLS},
            {agent: str(clone / "agents" / agent) for agent in AGENTS},
        )


class FreshInstall(InstallCase):
    """R1: on a fresh HOME, every skill directory and top-level agent file is linked."""

    def test_creates_skills_and_agents_as_real_directories__on_a_home_without_claude(self):
        """R1.1 install creates both link directories as real directories — nothing to link into, or links into a symlink."""
        result = self.run_installer(REPO)

        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertTrue(self.skills_dir.is_dir() and not self.skills_dir.is_symlink())
        self.assertTrue(self.agents_dir.is_dir() and not self.agents_dir.is_symlink())

    def test_links_every_skill_directory_and_agent_file__on_a_fresh_home(self):
        """R1.2 every skill directory and agent file is linked to the clone's copy — a skill or agent silently missing."""
        skills, agents = clone_skills(REPO), clone_agents(REPO)
        self.assertIn("robowright", skills, "the real clone's skills/ should hold the robowright skill")

        self.run_installer(REPO)

        self.assertEqual(sorted(links_in(self.skills_dir)), skills)
        self.assertEqual(sorted(links_in(self.agents_dir)), agents)
        self.assertEqual(
            {s: os.path.realpath(self.skills_dir / s) for s in skills},
            {s: os.path.realpath(REPO / "skills" / s) for s in skills},
        )
        self.assertEqual(
            {a: os.path.realpath(self.agents_dir / a) for a in agents},
            {a: os.path.realpath(REPO / "agents" / a) for a in agents},
        )

    def test_points_each_link_at_the_absolute_resolved_clone_path(self):
        """R1.3 each link's target is the clone path, absolute and resolved — links break when ~/.claude or the clone moves."""
        skills, agents = clone_skills(REPO), clone_agents(REPO)

        self.run_installer(REPO)

        self.assertEqual(
            links_in(self.skills_dir),
            {s: os.path.realpath(REPO / "skills" / s) for s in skills},
        )
        self.assertEqual(
            links_in(self.agents_dir),
            {a: os.path.realpath(REPO / "agents" / a) for a in agents},
        )

    def test_prints_one_linked_line_per_link_and_exits_zero(self):
        """R1.4 install reports each link it made, the wrapper it wrote and its interpreter, each on its own line — the user
        cannot see what was installed (assumed Q1)."""
        expected = sorted(
            [f"linked {self.skills_dir / s}" for s in clone_skills(REPO)]
            + [f"linked {self.agents_dir / a}" for a in clone_agents(REPO)]
            + [f"wrote {self.rw_git}", f"rw-git: interpreter {self.python3()}", RW_GIT_NOTE.format(bin=self.bin_dir)]
        )

        result = self.run_installer(REPO)

        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(sorted(result.stdout.splitlines()), expected)

    def test_creates_nothing_else_under_home(self):
        """R1.5 install creates only the two directories, the bin folder and the links — stray files left in the user's HOME."""
        expected = sorted(
            [".claude", ".claude/skills", ".claude/agents", ".local", ".local/bin", ".local/bin/rw-git"]
            + [f".claude/skills/{s}" for s in clone_skills(REPO)]
            + [f".claude/agents/{a}" for a in clone_agents(REPO)]
        )

        self.run_installer(REPO)

        self.assertEqual(sorted(tree(self.home)), expected)

    def test_links_only_skill_directories_and_top_level_agent_markdown__beside_decoys(self):
        """R1.6 files in skills/, non-.md or nested entries in agents/, and repo-only trees are not linked — the repo's internals leak into ~/.claude."""
        clone = self.make_clone()
        skills, agents = self.synthetic_links(clone)

        self.run_installer(clone)

        self.assertEqual(links_in(self.skills_dir), skills)
        self.assertEqual(links_in(self.agents_dir), agents)

    def test_links_into_existing_directories__when_skills_and_agents_already_exist(self):
        """R1.7 existing real skills/ and agents/ directories are used as they are — an install over an existing ~/.claude fails or replaces them."""
        clone = self.make_clone()
        self.skills_dir.mkdir(parents=True)
        self.agents_dir.mkdir()
        skills, agents = self.synthetic_links(clone)

        result = self.run_installer(clone)

        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertFalse(self.skills_dir.is_symlink())
        self.assertFalse(self.agents_dir.is_symlink())
        self.assertEqual(links_in(self.skills_dir), skills)
        self.assertEqual(links_in(self.agents_dir), agents)

    def test_leaves_the_users_own_entries_in_place__beside_the_clone_links(self):
        """R1.8 entries that are not targets are neither refused nor touched — the user's own skills and settings are lost or block the install."""
        clone = self.make_clone()
        write(self.skills_dir / "my-own/SKILL.md", "# my own skill\n")
        write(self.agents_dir / "mine.md", "# my agent\n")
        write(self.claude / "settings.json", '{"theme": "dark"}\n')

        result = self.run_installer(clone)

        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual((self.skills_dir / "my-own/SKILL.md").read_text(), "# my own skill\n")
        self.assertEqual((self.agents_dir / "mine.md").read_text(), "# my agent\n")
        self.assertEqual((self.claude / "settings.json").read_text(), '{"theme": "dark"}\n')
        self.assertEqual(sorted(links_in(self.skills_dir)), SKILLS)

    def test_writes_the_resolved_clone_path__when_run_through_a_symlinked_clone_path(self):
        """R1.9 links name the clone's resolved path, not the symlinked path it was run through — they break when that symlink goes."""
        clone = self.make_clone()
        via = self.root / "via-link"
        via.symlink_to(clone)
        skills, agents = self.synthetic_links(clone)

        self.run_installer(clone, script=via / "install.sh", cwd=via)

        self.assertEqual(links_in(self.skills_dir), skills)
        self.assertEqual(links_in(self.agents_dir), agents)

    def test_installs_through_a_symlinked_claude_directory(self):
        """R1.10 a ~/.claude that is itself a symlink is followed, not refused — a linked `~/.claude` cannot install otherwise (assumed Q6)."""
        clone = self.make_clone()
        linked = self.root / "linked-claude"
        linked.mkdir()
        self.claude.symlink_to(linked)

        result = self.run_installer(clone)

        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(sorted(links_in(linked / "skills")), SKILLS)


class SecondRun(InstallCase):
    """R2: a second run over a finished install prints nothing and changes nothing."""

    def setUp(self):
        super().setUp()
        self.install_ok(REPO)

    def test_prints_nothing_and_exits_zero__on_a_second_run(self):
        """R2.1 a rerun is silent — every rerun looks like a fresh install."""
        result = self.run_installer(REPO)

        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(result.stdout, "")

    def test_changes_nothing_under_home__on_a_second_run(self):
        """R2.2 a rerun re-creates no link and touches nothing — the install is not idempotent."""
        before = tree(self.home)

        self.run_installer(REPO)

        self.assertEqual(tree(self.home), before)


class RetargetsForeignLinks(InstallCase):
    """R3: a symlink at a target is retargeted when nothing is lost by it: it dangles, it resolves into this clone, or
    it resolves into an earlier robowright clone. Any other link that resolves outside this clone is refused."""

    def setUp(self):
        super().setUp()
        self.clone = self.make_clone()
        self.install_ok(self.clone)
        self.elsewhere = self.root / "elsewhere"
        write(self.elsewhere / "linting/SKILL.md", "other\n")
        write(self.elsewhere / "checker.md", "# other checker\n")
        self.earlier = self.make_earlier_clone("earlier")

    def make_earlier_clone(self, name, files=("install.sh", "skills/robowright/SKILL.md")):
        """A folder shaped like an earlier robowright clone: `files`, plus the linked skill and agent."""
        earlier = self.root / name
        for relpath in files:
            write(earlier / relpath, "# earlier\n")
        write(earlier / "skills/linting/SKILL.md", "earlier\n")
        write(earlier / "agents/checker.md", "# earlier checker\n")
        return earlier

    def relink(self, link, target):
        os.remove(link)
        os.symlink(target, link)

    def assertRefusedUnchanged(self, link, target, before, result):
        self.assertEqual(result.returncode, 1, result.stderr)
        self.assertEqual(len(result.stderr.splitlines()), 1, result.stderr)
        self.assertNamesPath(link, result.stderr)
        self.assertNamesPath(target, result.stderr)
        self.assertEqual(tree(self.home), before)

    def test_refuses_a_skill_link_into_a_folder_that_is_not_a_robowright_clone(self):
        """R3.1 a skill link into a folder that is not a robowright clone is refused, and no link is made — someone's own skill is silently replaced."""
        self.relink(self.skills_dir / "linting", self.elsewhere / "linting")
        before = tree(self.home)

        result = self.run_installer(self.clone)

        self.assertRefusedUnchanged(self.skills_dir / "linting", self.elsewhere / "linting", before, result)
        self.assertEqual((self.elsewhere / "linting/SKILL.md").read_text(), "other\n")

    def test_prints_linked_only_for_the_retargeted_link(self):
        """R3.2 only the retargeted link is reported — the output hides which link changed."""
        self.relink(self.skills_dir / "linting", self.earlier / "skills/linting")

        result = self.run_installer(self.clone)

        self.assertEqual(
            result.stdout.splitlines(),
            [f"linked {self.skills_dir / 'linting'} (was {self.earlier / 'skills/linting'})"],
        )

    def test_retargets_a_dangling_skill_link(self):
        """R3.3 a link to a path that no longer exists is retargeted, not mistaken for an empty slot — the install fails on "File exists"."""
        self.relink(self.skills_dir / "linting", self.root / "gone/linting")

        result = self.run_installer(self.clone)

        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(os.readlink(self.skills_dir / "linting"), str(self.clone / "skills/linting"))
        self.assertEqual(
            result.stdout.splitlines(), [f"linked {self.skills_dir / 'linting'} (was {self.root / 'gone/linting'})"]
        )

    def test_refuses_an_agent_link_into_a_folder_that_is_not_a_robowright_clone(self):
        """R3.4 an agent link into a folder that is not a robowright clone is refused, and no link is made — someone's own agent is silently replaced."""
        self.relink(self.agents_dir / "checker.md", self.elsewhere / "checker.md")
        before = tree(self.home)

        result = self.run_installer(self.clone)

        self.assertRefusedUnchanged(self.agents_dir / "checker.md", self.elsewhere / "checker.md", before, result)

    def test_leaves_the_old_target_intact__after_retargeting(self):
        """R3.5 retargeting replaces only the link, never what it pointed at — another checkout's files are deleted."""
        self.relink(self.skills_dir / "linting", self.earlier / "skills/linting")

        self.run_installer(self.clone)

        self.assertEqual((self.earlier / "skills/linting/SKILL.md").read_text(), "earlier\n")

    def test_rewrites_a_relative_link_into_the_clone_as_absolute(self):
        """R3.6 a relative link into the clone, as an older install left it, is rewritten as absolute — it breaks when ~/.claude moves (assumed Q3)."""
        self.relink(self.skills_dir / "linting", "../../../checkout/skills/linting")
        self.assertEqual(os.path.realpath(self.skills_dir / "linting"), str(self.clone / "skills/linting"))

        result = self.run_installer(self.clone)

        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(os.readlink(self.skills_dir / "linting"), str(self.clone / "skills/linting"))
        self.assertEqual(
            result.stdout.splitlines(),
            [f"linked {self.skills_dir / 'linting'} (was ../../../checkout/skills/linting)"],
        )

    def test_retargets_a_skill_link_into_an_earlier_robowright_clone(self):
        """R3.7 a skill link into an earlier robowright clone is pointed at this clone — moving the clone strands every link."""
        self.relink(self.skills_dir / "linting", self.earlier / "skills/linting")

        result = self.run_installer(self.clone)

        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(os.readlink(self.skills_dir / "linting"), str(self.clone / "skills/linting"))

    def test_retargets_an_agent_link_into_an_earlier_robowright_clone(self):
        """R3.8 an agent link into an earlier robowright clone is pointed at this clone — moving the clone strands every link."""
        self.relink(self.agents_dir / "checker.md", self.earlier / "agents/checker.md")

        result = self.run_installer(self.clone)

        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(os.readlink(self.agents_dir / "checker.md"), str(self.clone / "agents/checker.md"))
        self.assertEqual(
            result.stdout.splitlines(),
            [f"linked {self.agents_dir / 'checker.md'} (was {self.earlier / 'agents/checker.md'})"],
        )

    def test_refuses_a_link_into_a_clone_shape_with_no_install_sh(self):
        """R3.9 a folder with `skills/<name>` and `skills/robowright/SKILL.md` but no `install.sh` is not an earlier clone — any skills folder passes."""
        partial = self.make_earlier_clone("partial", files=("skills/robowright/SKILL.md",))
        self.relink(self.skills_dir / "linting", partial / "skills/linting")
        before = tree(self.home)

        result = self.run_installer(self.clone)

        self.assertRefusedUnchanged(self.skills_dir / "linting", partial / "skills/linting", before, result)

    def test_refuses_a_link_into_a_clone_shape_with_no_robowright_skill(self):
        """R3.10 a folder with `install.sh` and `skills/<name>` but no `skills/robowright/SKILL.md` is not an earlier clone — any project with an installer passes."""
        partial = self.make_earlier_clone("partial", files=("install.sh",))
        self.relink(self.skills_dir / "linting", partial / "skills/linting")
        before = tree(self.home)

        result = self.run_installer(self.clone)

        self.assertRefusedUnchanged(self.skills_dir / "linting", partial / "skills/linting", before, result)

    def test_refuses_a_link_into_an_earlier_clone_under_another_name(self):
        """R3.11 a link into an earlier clone's skill of another name is refused — someone's own link that reuses robowright's files passes."""
        self.relink(self.skills_dir / "linting", self.earlier / "skills/robowright")
        before = tree(self.home)

        result = self.run_installer(self.clone)

        self.assertRefusedUnchanged(self.skills_dir / "linting", self.earlier / "skills/robowright", before, result)

    def test_refuses_an_agent_link_into_a_clone_shape_whose_skills_folder_is_a_link(self):
        """R3.12 an agent link into a folder whose `skills/` is a link to a real clone's is refused — linking a clone's skills into any folder makes it pass."""
        decoy = self.root / "decoy"
        write(decoy / "install.sh", "# decoy\n")
        write(decoy / "agents/checker.md", "# my checker\n")
        (decoy / "skills").symlink_to(self.earlier / "skills")
        self.relink(self.agents_dir / "checker.md", decoy / "agents/checker.md")
        before = tree(self.home)

        result = self.run_installer(self.clone)

        self.assertRefusedUnchanged(self.agents_dir / "checker.md", decoy / "agents/checker.md", before, result)

    def test_refuses_a_link_into_a_clone_shape_whose_install_sh_is_a_link(self):
        """R3.13 a folder whose `install.sh` is a link to a real clone's is not an earlier clone — linking one file into any folder makes it pass."""
        decoy = self.make_earlier_clone("decoy", files=("skills/robowright/SKILL.md",))
        (decoy / "install.sh").symlink_to(self.earlier / "install.sh")
        self.relink(self.skills_dir / "linting", decoy / "skills/linting")
        before = tree(self.home)

        result = self.run_installer(self.clone)

        self.assertRefusedUnchanged(self.skills_dir / "linting", decoy / "skills/linting", before, result)

    def test_names_the_earlier_clone_target_it_replaced(self):
        """R3.14 a link into an earlier robowright clone is repointed and the line names the link's text before the install — a folder shaped like a clone, by whoever can write it, takes over a link with no sign of what it pointed at."""
        old = self.earlier / "skills/linting"
        self.relink(self.skills_dir / "linting", old)

        result = self.run_installer(self.clone)

        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(os.readlink(self.skills_dir / "linting"), str(self.clone / "skills/linting"))
        self.assertEqual(result.stdout, f"linked {self.skills_dir / 'linting'} (was {old})\n")

    def test_names_the_dangling_target_it_replaced(self):
        """R3.15 a dangling link is repointed and the line names the link's text before the install — a link into an unmounted volume is repointed with no sign of what it pointed at."""
        old = self.root / "gone/linting"
        self.relink(self.skills_dir / "linting", old)

        result = self.run_installer(self.clone)

        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(os.readlink(self.skills_dir / "linting"), str(self.clone / "skills/linting"))
        self.assertEqual(result.stdout, f"linked {self.skills_dir / 'linting'} (was {old})\n")

    def test_escapes_control_bytes_in_the_target_it_replaced(self):
        """R3.16 a replaced link whose text holds an escape byte and a newline reaches stdout with neither raw — a link's text writes to the Owner's terminal."""
        self.relink(self.skills_dir / "linting", f"{self.root}/gone\x1b[31m\nlinting")

        result = self.run_installer(self.clone)

        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(os.readlink(self.skills_dir / "linting"), str(self.clone / "skills/linting"))
        self.assertNotIn("\x1b", result.stdout)
        self.assertEqual(len(result.stdout.splitlines()), 1, result.stdout)
        self.assertTrue(result.stdout.startswith(f"linked {self.skills_dir / 'linting'} (was "), result.stdout)


class RefusesNonLinks(InstallCase):
    """R4: anything at a target that is not a symlink, or a symlinked skills/ or agents/, stops
    the install before its first link."""

    def setUp(self):
        super().setUp()
        self.clone = self.make_clone()

    def test_refuses_a_regular_file_at_a_skill_target_and_makes_no_link(self):
        """R4.1 one real file among clean targets stops the install before any link — a half-made install (assumed Q2)."""
        write(self.skills_dir / "reviewing", "mine\n")

        result = self.run_installer(self.clone)

        self.assertEqual(result.returncode, 1, result.stderr)
        self.assertNamesPath(self.skills_dir / "reviewing", result.stderr)
        self.assertEqual(symlinks_under(self.home), [])

    def test_leaves_the_refused_file_as_it_was(self):
        """R4.2 a refused regular file is kept byte for byte — the install destroys the user's file."""
        write(self.skills_dir / "reviewing", "mine\n")

        self.run_installer(self.clone)

        self.assertFalse((self.skills_dir / "reviewing").is_symlink())
        self.assertEqual((self.skills_dir / "reviewing").read_text(), "mine\n")

    def test_refuses_a_real_directory_at_a_skill_target_and_makes_no_link(self):
        """R4.3 a real directory at a target is refused and kept — the user's own skill is replaced or a link lands inside it (assumed Q2)."""
        write(self.skills_dir / "reviewing/SKILL.md", "my own\n")

        result = self.run_installer(self.clone)

        self.assertEqual(result.returncode, 1, result.stderr)
        self.assertNamesPath(self.skills_dir / "reviewing", result.stderr)
        self.assertEqual(symlinks_under(self.home), [])
        self.assertEqual((self.skills_dir / "reviewing/SKILL.md").read_text(), "my own\n")

    def test_refuses_a_regular_file_at_an_agent_target_and_makes_no_link(self):
        """R4.4 a real file at the last agent target stops the install before any skill link — the check is not done up front (assumed Q2)."""
        write(self.agents_dir / "summarizer.md", "# my summarizer\n")

        result = self.run_installer(self.clone)

        self.assertEqual(result.returncode, 1, result.stderr)
        self.assertNamesPath(self.agents_dir / "summarizer.md", result.stderr)
        self.assertEqual(symlinks_under(self.home), [])

    def test_refuses_a_named_pipe_at_a_skill_target_and_makes_no_link(self):
        """R4.5 anything that is not a symlink is refused, not only files and directories — the install replaces an unexpected kind (assumed Q2)."""
        self.skills_dir.mkdir(parents=True)
        os.mkfifo(self.skills_dir / "linting")

        result = self.run_installer(self.clone)

        self.assertEqual(result.returncode, 1, result.stderr)
        self.assertNamesPath(self.skills_dir / "linting", result.stderr)
        self.assertEqual(symlinks_under(self.home), [])

    def test_refuses_a_symlinked_skills_directory_and_makes_no_link(self):
        """R4.6 a skills/ that is itself a symlink is refused before any link — links land inside another tree (assumed Q2)."""
        elsewhere = self.root / "elsewhere-skills"
        elsewhere.mkdir()
        self.claude.mkdir()
        self.skills_dir.symlink_to(elsewhere)

        result = self.run_installer(self.clone)

        self.assertEqual(result.returncode, 1, result.stderr)
        self.assertNamesPath(self.skills_dir, result.stderr)
        self.assertEqual(symlinks_under(self.home), [".claude/skills"])
        self.assertEqual(os.readlink(self.skills_dir), str(elsewhere))
        self.assertEqual(os.listdir(elsewhere), [])

    def test_refuses_a_symlinked_agents_directory_and_makes_no_link(self):
        """R4.7 an agents/ that is itself a symlink is refused before any link — links land inside another tree (assumed Q2)."""
        elsewhere = self.root / "elsewhere-agents"
        elsewhere.mkdir()
        self.claude.mkdir()
        self.agents_dir.symlink_to(elsewhere)

        result = self.run_installer(self.clone)

        self.assertEqual(result.returncode, 1, result.stderr)
        self.assertNamesPath(self.agents_dir, result.stderr)
        self.assertEqual(symlinks_under(self.home), [".claude/agents"])
        self.assertEqual(os.listdir(elsewhere), [])

    def test_changes_no_existing_link__when_one_target_is_refused(self):
        """R4.8 a refusal retargets no link that would otherwise be retargeted — a refused run still half-changes the install (assumed Q2)."""
        self.install_ok(self.clone)
        earlier = self.root / "earlier"
        write(earlier / "install.sh", "# earlier\n")
        write(earlier / "skills/robowright/SKILL.md", "# earlier\n")
        write(earlier / "skills/linting/SKILL.md", "earlier\n")
        os.remove(self.skills_dir / "linting")
        os.symlink(earlier / "skills/linting", self.skills_dir / "linting")
        os.remove(self.agents_dir / "summarizer.md")
        write(self.agents_dir / "summarizer.md", "# my summarizer\n")
        before = tree(self.home)

        result = self.run_installer(self.clone)

        self.assertEqual(result.returncode, 1, result.stderr)
        self.assertNamesPath(self.agents_dir / "summarizer.md", result.stderr)
        self.assertEqual(tree(self.home), before)


class Uninstall(InstallCase):
    """R5: --uninstall removes every link in skills/ and agents/ that resolves into this clone,
    and nothing else."""

    def setUp(self):
        super().setUp()
        self.clone = self.make_clone()

    def test_removes_every_link_it_made(self):
        """R5.1 uninstall removes every link the install made — the uninstall leaves skills installed."""
        self.install_ok(self.clone)

        result = self.run_installer(self.clone, "--uninstall")

        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(links_in(self.skills_dir), {})
        self.assertEqual(links_in(self.agents_dir), {})

    def test_prints_one_removed_line_per_link(self):
        """R5.2 uninstall reports each link it removed on its own line — the user cannot see what was removed (assumed Q1)."""
        self.install_ok(self.clone)
        expected = sorted(
            [f"removed {self.skills_dir / s}" for s in SKILLS]
            + [f"removed {self.agents_dir / a}" for a in AGENTS]
        )

        result = self.run_installer(self.clone, "--uninstall")

        self.assertEqual(sorted(result.stdout.splitlines()), expected)

    def test_keeps_a_link_outside_the_clone_and_a_planted_file(self):
        """R5.3 uninstall leaves links to elsewhere and regular files alone — it deletes other tools' links and the user's files."""
        self.install_ok(self.clone)
        other_tool = self.root / "elsewhere/other-tool"
        other_tool.mkdir(parents=True)
        os.symlink(other_tool, self.skills_dir / "other-tool")
        write(self.agents_dir / "notes.md", "notes\n")

        result = self.run_installer(self.clone, "--uninstall")

        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(os.readlink(self.skills_dir / "other-tool"), str(other_tool))
        self.assertEqual((self.agents_dir / "notes.md").read_text(), "notes\n")

    def test_keeps_a_link_into_a_sibling_whose_name_extends_the_clones(self):
        """R5.4 "inside this clone" is a path match, so a sibling checkout-old is not inside checkout — uninstall deletes another checkout's links."""
        self.install_ok(self.clone)
        neighbour = self.root / "checkout-old/skills/linting"
        neighbour.mkdir(parents=True)
        os.symlink(neighbour, self.skills_dir / "old-linting")

        self.run_installer(self.clone, "--uninstall")

        self.assertEqual(os.readlink(self.skills_dir / "old-linting"), str(neighbour))

    def test_keeps_a_link_whose_dot_dot_leaves_the_clone(self):
        """R5.11 a link to <clone>/.. or <clone>/skills/../.. points at the clone's parent, outside it — uninstall deletes it on a textual prefix match."""
        self.install_ok(self.clone)
        os.symlink(f"{self.clone}/..", self.skills_dir / "parent")
        os.symlink(f"{self.clone}/skills/../..", self.skills_dir / "grandparent-by-text")

        self.run_installer(self.clone, "--uninstall")

        self.assertEqual(os.readlink(self.skills_dir / "parent"), f"{self.clone}/..")
        self.assertEqual(os.readlink(self.skills_dir / "grandparent-by-text"), f"{self.clone}/skills/../..")

    def test_keeps_a_link_that_leaves_the_clone_through_a_symlinked_component(self):
        """R5.12 `..` after a symlinked component is resolved on disk, not as text — uninstall deletes a link that points outside the clone."""
        self.install_ok(self.clone)
        deep = self.root / "outside/a/b/c/d"
        deep.mkdir(parents=True)
        outside_target = self.root / "outside/checkout/skills/linting"
        outside_target.mkdir(parents=True)
        os.symlink(deep, self.skills_dir / "sym")
        # As text this is <root>/checkout/skills/linting, inside the clone; on disk sym/.. is outside/a/b/c.
        escaping = "sym/../../../../checkout/skills/linting"
        os.symlink(escaping, self.skills_dir / "escape")
        self.assertEqual(os.path.realpath(self.skills_dir / "escape"), str(outside_target))

        self.run_installer(self.clone, "--uninstall")

        self.assertEqual(os.readlink(self.skills_dir / "escape"), escaping)

    def test_removes_a_differently_named_link_into_the_clone(self):
        """R5.5 any link into the clone is removed, whatever its name — a link under an older name survives uninstall."""
        self.agents_dir.mkdir(parents=True)
        os.symlink(self.clone / "agents/checker.md", self.agents_dir / "checker-alias.md")

        result = self.run_installer(self.clone, "--uninstall")

        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertFalse(os.path.lexists(self.agents_dir / "checker-alias.md"))
        self.assertEqual(result.stdout.splitlines(), [f"removed {self.agents_dir / 'checker-alias.md'}"])

    def test_removes_a_relative_link_that_resolves_into_the_clone(self):
        """R5.6 a relative link into the clone, as an older install left it, is removed — an older install's links would survive uninstall."""
        self.skills_dir.mkdir(parents=True)
        os.symlink("../../../checkout/skills/linting", self.skills_dir / "linting")
        self.assertEqual(os.path.realpath(self.skills_dir / "linting"), str(self.clone / "skills/linting"))

        result = self.run_installer(self.clone, "--uninstall")

        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertFalse(os.path.lexists(self.skills_dir / "linting"))

    def test_removes_a_dangling_link_into_the_clone(self):
        """R5.7 a link to a skill since deleted from the clone is removed — a broken link is stranded in ~/.claude (assumed Q4)."""
        self.skills_dir.mkdir(parents=True)
        os.symlink(self.clone / "skills/retired", self.skills_dir / "retired")

        result = self.run_installer(self.clone, "--uninstall")

        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertFalse(os.path.lexists(self.skills_dir / "retired"))

    def test_prints_nothing_and_exits_zero__on_a_second_uninstall(self):
        """R5.8 a repeated uninstall is a silent success — scripts that uninstall twice fail."""
        self.install_ok(self.clone)
        self.uninstall_ok(self.clone)

        result = self.run_installer(self.clone, "--uninstall")

        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(result.stdout, "")

    def test_keeps_the_skills_and_agents_directories(self):
        """R5.9 uninstall removes links only, not the directories that hold them — the user's own entries go with them."""
        self.install_ok(self.clone)

        self.run_installer(self.clone, "--uninstall")

        self.assertTrue(self.skills_dir.is_dir() and not self.skills_dir.is_symlink())
        self.assertTrue(self.agents_dir.is_dir() and not self.agents_dir.is_symlink())

    def test_creates_nothing__when_uninstalling_from_a_home_without_claude(self):
        """R5.10 uninstall with nothing installed is a silent no-op — it errors or creates ~/.claude (assumed Q5)."""
        result = self.run_installer(self.clone, "--uninstall")

        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(result.stdout, "")
        self.assertFalse(os.path.lexists(self.claude))


class Arguments(InstallCase):
    """R6: any argument other than --uninstall is a usage error that does nothing."""

    def setUp(self):
        super().setUp()
        self.clone = self.make_clone()

    def test_exits_two_with_one_usage_line__on_an_unknown_flag(self):
        """R6.1 an unknown flag is exit 2 with one usage line — a typo installs, or fails without saying how to call it (assumed: the line says usage)."""
        result = self.run_installer(self.clone, "--frobnicate")

        self.assertEqual(result.returncode, 2, result.stderr)
        lines = [line for line in result.stderr.splitlines() if line.strip()]
        self.assertEqual(len(lines), 1, result.stderr)
        self.assertIn("usage", lines[0].lower())

    def test_makes_no_link__on_an_unknown_flag(self):
        """R6.2 an unknown flag makes no link — a mistyped uninstall installs instead."""
        self.run_installer(self.clone, "--frobnicate")

        self.assertEqual(symlinks_under(self.home), [])

    def test_refuses_a_target_flag_and_makes_no_link(self):
        """R6.3 there is no --target flag: HOME alone decides the target — links land somewhere the contract never names."""
        target = self.root / "target"
        target.mkdir()

        result = self.run_installer(self.clone, "--target", str(target))

        self.assertEqual(result.returncode, 2, result.stderr)
        self.assertEqual(symlinks_under(self.home), [])
        self.assertEqual(symlinks_under(target), [])

    def test_removes_nothing__when_uninstall_comes_with_an_unknown_flag(self):
        """R6.4 an extra argument beside --uninstall is a usage error that removes nothing — a mistyped command half-runs."""
        self.install_ok(self.clone)
        before = tree(self.home)

        result = self.run_installer(self.clone, "--uninstall", "--frobnicate")

        self.assertEqual(result.returncode, 2, result.stderr)
        self.assertEqual(tree(self.home), before)


class OtherWorkingDirectory(InstallCase):
    """R7: the clone is the script's own directory, whatever the cwd."""

    def test_links_the_scripts_own_clone__when_run_from_a_directory_with_its_own_skills(self):
        """R7.1 run from another project, install links its own clone, not the cwd's skills/ — the wrong tree is installed."""
        other = self.root / "other-project"
        write(other / "skills/decoy-skill/SKILL.md", "# decoy\n")
        write(other / "agents/decoy.md", "# decoy\n")

        result = self.run_installer(REPO, cwd=other)

        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(
            links_in(self.skills_dir),
            {s: os.path.realpath(REPO / "skills" / s) for s in clone_skills(REPO)},
        )
        self.assertEqual(
            links_in(self.agents_dir),
            {a: os.path.realpath(REPO / "agents" / a) for a in clone_agents(REPO)},
        )

    def test_writes_absolute_targets__when_invoked_by_a_relative_path(self):
        """R7.2 invoked as a relative path, install still writes absolute clone targets — every link dangles."""
        clone = self.make_clone()
        skills, agents = self.synthetic_links(clone)

        result = self.run_installer(clone, script=Path("checkout/install.sh"), cwd=self.root)

        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(links_in(self.skills_dir), skills)
        self.assertEqual(links_in(self.agents_dir), agents)


class PipeInClonePath(InstallCase):
    """R8: a clone whose absolute path contains `|` installs, reruns and uninstalls exactly as any
    other clone does. The clone is built at <root>/a|b/checkout with install.sh copied into it,
    and that copy is the script run."""

    def setUp(self):
        super().setUp()
        self.clone = self.make_clone("a|b/checkout")
        # Precondition: a fixture without the `|` tests nothing.
        self.assertIn("|", str(self.clone))

    def given_installed(self):
        """The state a finished install leaves (R1.3), built without running the installer: one
        absolute link per skill directory and agent file, each to its path in this clone."""
        self.skills_dir.mkdir(parents=True)
        self.agents_dir.mkdir()
        for skill in SKILLS:
            os.symlink(str(self.clone / "skills" / skill), self.skills_dir / skill)
        for agent in AGENTS:
            os.symlink(str(self.clone / "agents" / agent), self.agents_dir / agent)

    def test_prints_one_linked_line_per_link__when_the_clone_path_contains_a_pipe(self):
        """R8.1 install from a clone under a `|`-named directory exits 0 and reports one `linked` line per skill and agent — a `|` in the path splits each link into a wrong source and target and the install fails."""
        expected = sorted(
            [f"linked {self.skills_dir / s}" for s in SKILLS]
            + [f"linked {self.agents_dir / a}" for a in AGENTS]
        )

        result = self.run_installer(self.clone)

        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(sorted(result.stdout.splitlines()), expected)

    def test_links_resolve_into_that_clone__when_the_clone_path_contains_a_pipe(self):
        """R8.2 every link made from a clone under a `|`-named directory resolves to its own path in that clone — links land under a truncated path or point at the `|`-named parent."""
        result = self.run_installer(self.clone)

        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(sorted(links_in(self.skills_dir)), SKILLS)
        self.assertEqual(sorted(links_in(self.agents_dir)), AGENTS)
        self.assertEqual(
            {s: os.path.realpath(self.skills_dir / s) for s in SKILLS},
            {s: os.path.realpath(self.clone / "skills" / s) for s in SKILLS},
        )
        self.assertEqual(
            {a: os.path.realpath(self.agents_dir / a) for a in AGENTS},
            {a: os.path.realpath(self.clone / "agents" / a) for a in AGENTS},
        )

    def test_prints_nothing_and_exits_zero__on_a_second_run_from_a_clone_path_with_a_pipe(self):
        """R8.3 a rerun over a finished install from a clone under a `|`-named directory is silent and exits 0 — the rerun misreads its own links and relinks or fails (assumed Q1)."""
        self.given_installed()

        result = self.run_installer(self.clone)

        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(result.stdout, "")

    def test_removes_every_link__on_uninstall_from_a_clone_path_with_a_pipe(self):
        """R8.4 uninstall from a clone under a `|`-named directory removes every link into it — links into a `|` path are stranded in ~/.claude (assumed Q1)."""
        self.given_installed()

        result = self.run_installer(self.clone, "--uninstall")

        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(links_in(self.skills_dir), {})
        self.assertEqual(links_in(self.agents_dir), {})


class GuardedBranches(InstallCase):
    """R9: the script's guards against an environment it does not control — an exported CDPATH,
    a link chain that loops, a non-directory at a link directory, a symlinked link directory."""

    def setUp(self):
        super().setUp()
        self.clone = self.make_clone()

    def test_links_the_real_clone__when_cdpath_names_a_decoy_checkout(self):
        """R9.1 an exported CDPATH does not redirect the clone lookup — a relative invocation links a same-named decoy checkout, or nothing."""
        decoys = self.root / "decoys"
        write(decoys / "checkout/skills/decoy/SKILL.md", "# decoy\n")
        skills, agents = self.synthetic_links(self.clone)

        result = self.run_installer(
            self.clone, script=Path("checkout/install.sh"), cwd=self.root, env={"CDPATH": str(decoys)}
        )

        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(links_in(self.skills_dir), skills)
        self.assertEqual(links_in(self.agents_dir), agents)

    def test_exits_zero_and_keeps_both_links__when_uninstall_meets_a_link_loop(self):
        """R9.2 uninstall gives up on a link chain that loops and leaves it — an endless loop, or a removed link that was never the clone's."""
        self.install_ok(self.clone)
        os.symlink("loop-b", self.skills_dir / "loop-a")
        os.symlink("loop-a", self.skills_dir / "loop-b")

        result = self.uninstall_ok(self.clone)

        self.assertEqual(result.stdout.splitlines(), sorted(f"removed {self.skills_dir / s}" for s in SKILLS)
                         + sorted(f"removed {self.agents_dir / a}" for a in AGENTS))
        self.assertEqual(links_in(self.skills_dir), {"loop-a": "loop-b", "loop-b": "loop-a"})

    def test_refuses_a_file_at_the_skills_directory_and_makes_no_link(self):
        """R9.3 a regular file at ~/.claude/skills is refused as "not a directory", the file kept — a raw mkdir error, or links made beside it."""
        self.claude.mkdir()
        write(self.skills_dir, "my file\n")

        result = self.run_installer(self.clone)

        self.assertEqual(result.returncode, 1, result.stderr)
        self.assertNamesPath(self.skills_dir, result.stderr)
        self.assertIn("is not a directory", result.stderr)
        self.assertEqual(symlinks_under(self.home), [])
        self.assertEqual(self.skills_dir.read_text(), "my file\n")

    def test_refuses_a_file_at_the_agents_directory_and_makes_no_link(self):
        """R9.4 a regular file at ~/.claude/agents is refused as "not a directory", the file kept — a raw mkdir error, or skill links made first."""
        self.claude.mkdir()
        write(self.agents_dir, "my file\n")

        result = self.run_installer(self.clone)

        self.assertEqual(result.returncode, 1, result.stderr)
        self.assertNamesPath(self.agents_dir, result.stderr)
        self.assertIn("is not a directory", result.stderr)
        self.assertEqual(symlinks_under(self.home), [])
        self.assertEqual(self.agents_dir.read_text(), "my file\n")

    def test_removes_nothing__when_uninstall_meets_a_symlinked_skills_directory(self):
        """R9.5 uninstall skips a symlinked ~/.claude/skills and prints nothing — it removes the links in the directory behind the symlink."""
        elsewhere = self.root / "elsewhere-skills"
        elsewhere.mkdir()
        behind = elsewhere / "drafting"
        os.symlink(str(self.clone / "skills/drafting"), behind)
        self.claude.mkdir()
        self.skills_dir.symlink_to(elsewhere)

        result = self.uninstall_ok(self.clone)

        self.assertEqual(result.stdout, "")
        self.assertEqual(os.readlink(self.skills_dir), str(elsewhere))
        self.assertEqual(os.readlink(behind), str(self.clone / "skills/drafting"))


def sh_quoted(word):
    """`word` as one single-quoted sh word."""
    return "'" + word.replace("'", "'\\''") + "'"


class RwGitWrapper(InstallCase):
    """R10: rw-git on the Owner's PATH at ~/.local/bin/rw-git is a wrapper file that execs the clone's rw_git.py."""

    def wrapper(self, clone, python3=None):
        """R10.1's two lines for `clone`, `python3` the install's interpreter unless given."""
        program = os.path.realpath(clone) + "/" + RW_GIT_SOURCE
        return ("#!/bin/sh -p\n"
                f"exec /usr/bin/env -i PATH=/usr/bin:/bin HOME={sh_quoted(str(self.home))} "
                f"{sh_quoted(python3 or self.python3())} -I {sh_quoted(program)} \"$@\"\n")

    def given_wrapper(self, text):
        self.bin_dir.mkdir(parents=True, exist_ok=True)
        self.rw_git.write_text(text)
        self.rw_git.chmod(0o755)

    def test_writes_the_wrapper_file_at_the_clones_program(self):
        """R10.1 a fresh install writes ~/.local/bin/rw-git as a 0755 file holding the wrapper, not a link — a link runs
        rw_git.py under the caller's environment, which a prefixed call chooses (S6-4)."""
        result = self.run_installer(REPO)

        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertFalse(self.rw_git.is_symlink())
        self.assertTrue(self.rw_git.is_file())
        self.assertEqual(stat.S_IMODE(self.rw_git.stat().st_mode), 0o755)
        self.assertEqual(self.rw_git.read_text(), self.wrapper(REPO))

    def test_says_which_folder_it_used_and_why_no_session_may_write_it(self):
        """R10.2 the install names the file, the interpreter it pinned, and the folder, and why it must stay unwritable to
        sessions — the Owner grants it to a session and rw-git is shadowed, or never sees what the wrapper runs."""
        result = self.run_installer(REPO)

        lines = result.stdout.splitlines()
        wrote = lines.index(f"wrote {self.rw_git}")
        self.assertEqual(lines[wrote + 1], f"rw-git: interpreter {self.python3()}")
        self.assertIn(RW_GIT_NOTE.format(bin=self.bin_dir), lines)

    def test_replaces_an_old_rw_git_link_with_the_wrapper(self):
        """R10.3 a link from an old install, into this clone or another checkout, becomes the wrapper, and the file it
        named is unchanged — an old copy keeps running as the Owner."""
        self.bin_dir.mkdir(parents=True)
        elsewhere = self.root / "elsewhere/rw_git.py"
        write(elsewhere, "")
        for target in (os.path.realpath(REPO / RW_GIT_SOURCE), elsewhere):
            with self.subTest(target=str(target)):
                if os.path.lexists(self.rw_git):
                    os.remove(self.rw_git)
                os.symlink(target, self.rw_git)

                result = self.run_installer(REPO)

                self.assertEqual(result.returncode, 0, result.stderr)
                self.assertFalse(self.rw_git.is_symlink())
                self.assertEqual(self.rw_git.read_text(), self.wrapper(REPO))
        self.assertEqual(elsewhere.read_text(), "")

    def test_refuses_a_file_that_is_not_this_clones_wrapper_and_makes_no_link(self):
        """R10.4 a regular file of the user's own, or another clone's wrapper, at ~/.local/bin/rw-git is refused by name,
        left unchanged, and nothing is linked — the user's own program, or another clone's install, is overwritten."""
        for text in ("mine\n", self.wrapper(self.root / "other-clone")):
            with self.subTest(text=text):
                self.given_wrapper(text)

                result = self.run_installer(REPO)

                self.assertEqual(result.returncode, 1)
                self.assertNamesPath(self.rw_git, result.stderr)
                self.assertEqual(self.rw_git.read_text(), text)
                self.assertEqual(links_in(self.skills_dir), {})

    def test_refuses_a_symlinked_bin_folder_and_makes_no_link(self):
        """R10.5 a ~/.local/bin that is a link is refused by name and nothing is linked — rw-git lands in whatever folder the link names."""
        elsewhere = self.root / "elsewhere-bin"
        elsewhere.mkdir()
        (self.home / ".local").mkdir()
        self.bin_dir.symlink_to(elsewhere)

        result = self.run_installer(REPO)

        self.assertEqual(result.returncode, 1)
        self.assertNamesPath(self.bin_dir, result.stderr)
        self.assertEqual(os.listdir(elsewhere), [])
        self.assertEqual(links_in(self.skills_dir), {})

    def test_uninstall_removes_its_own_wrapper_and_keeps_another_clones_and_a_link(self):
        """R10.6 uninstall removes its own wrapper and leaves another clone's wrapper and another tool's link — a stale
        rw-git stays on PATH, or another install's is deleted."""
        self.install_ok(REPO)

        result = self.run_installer(REPO, "--uninstall")

        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn(f"removed {self.rw_git}", result.stdout.splitlines())
        self.assertFalse(os.path.lexists(self.rw_git))
        other = self.wrapper(self.root / "other-clone")
        self.given_wrapper(other)
        self.uninstall_ok(REPO)
        self.assertEqual(self.rw_git.read_text(), other)
        os.remove(self.rw_git)
        elsewhere = self.root / "elsewhere/rw-git"
        write(elsewhere, "")
        os.symlink(elsewhere, self.rw_git)
        self.uninstall_ok(REPO)
        self.assertEqual(os.readlink(self.rw_git), str(elsewhere))

    def test_links_no_rw_git_from_a_clone_without_it(self):
        """R10.7 a clone with no rw_git.py makes no bin folder and no link — a dangling rw-git on PATH."""
        clone = self.make_clone()

        self.install_ok(clone)

        self.assertFalse(os.path.lexists(self.home / ".local"))

    def test_rewrites_this_clones_wrapper_when_it_differs(self):
        """R10.8 this clone's wrapper naming another interpreter is rewritten in place, and the install says so — a
        moved python3 leaves rw-git broken, or a refused install."""
        self.given_wrapper(self.wrapper(REPO, python3="/opt/sample/bin/python3"))

        result = self.run_installer(REPO)

        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn(f"wrote {self.rw_git}", result.stdout.splitlines())
        self.assertEqual(self.rw_git.read_text(), self.wrapper(REPO))

    def test_the_wrapper_runs_rw_git_with_a_scrubbed_environment(self):
        """R10.9 the wrapper, run with FOO, SHELLOPTS, PS4, PYTHONPATH and ENV set, runs rw_git.py isolated with PATH and
        HOME only and its arguments passed through — a prefixed call chooses what git and Python load as the Owner."""
        clone = self.make_clone()
        write(clone / RW_GIT_SOURCE, "import json, os, sys\n"
                                     "print(json.dumps({'env': dict(os.environ), 'isolated': sys.flags.isolated,"
                                     " 'argv': sys.argv[1:]}))\n")
        self.install_ok(clone)
        env = {"PATH": os.environ["PATH"], "FOO": "bar", "SHELLOPTS": "xtrace", "PS4": "traced ", "ENV": "/dev/null",
               "PYTHONPATH": str(self.root)}

        done = subprocess.run([str(self.rw_git), "--help", "a b"], capture_output=True, text=True, env=env, timeout=30)

        self.assertEqual(done.returncode, 0, done.stderr)
        seen = json.loads(done.stdout)
        # Set by the interpreter itself, whatever the caller passed: macOS's CoreFoundation, and Python's C locale
        # coercion (PEP 538) under env -i's C locale.
        for added in ("__CF_USER_TEXT_ENCODING", "LC_CTYPE"):
            seen["env"].pop(added, None)
        self.assertEqual(seen["env"], {"PATH": "/usr/bin:/bin", "HOME": str(self.home)})
        self.assertEqual(seen["isolated"], 1)
        self.assertEqual(seen["argv"], ["--help", "a b"])
        self.assertNotIn("traced", done.stderr)

    def assertNothingInstalled(self, result):
        self.assertEqual(result.returncode, 1, result.stderr)
        self.assertFalse(os.path.lexists(self.rw_git))
        self.assertEqual(links_in(self.skills_dir), {})
        self.assertEqual(links_in(self.agents_dir), {})

    def test_refuses_a_virtual_environments_interpreter_and_links_nothing(self):
        """R10.10 with a venv's bin/ first on PATH, the install is refused naming the venv's python3, with no rw-git and
        nothing linked — a venv's .pth files run under -I, so rw-git would run what the venv's folder holds, as the Owner
        (U58 D1)."""
        venv = self.root / "venv"
        subprocess.run(["python3", "-m", "venv", "--without-pip", str(venv)], capture_output=True, check=True)

        result = self.run_installer(REPO, env={"PATH": f"{venv}/bin:{os.environ['PATH']}"})

        self.assertNothingInstalled(result)
        self.assertIn(f"{venv}/bin/python3", result.stderr)
        self.assertIn("virtual environment", result.stderr)

    def test_refuses_a_python3_that_prints_no_interpreter_and_links_nothing(self):
        """R10.11 a python3 first on PATH that prints nothing is refused before anything is linked — the old exit came
        after every link, leaving a half install."""
        stub = self.root / "stub-bin" / "python3"
        write(stub, "#!/bin/sh\nexit 1\n")
        stub.chmod(0o755)

        result = self.run_installer(REPO, env={"PATH": f"{stub.parent}:{os.environ['PATH']}"})

        self.assertNothingInstalled(result)
        self.assertIn("python3 printed no interpreter path", result.stderr)


if __name__ == "__main__":
    unittest.main()
