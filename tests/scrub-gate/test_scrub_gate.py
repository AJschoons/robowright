"""Behavior suite for the scrub gate: tools/scrub-gate.sh and tools/hooks/{pre-commit,pre-push}.

Every row is in tests/scrub-gate/BEHAVIORS.md; each test's docstring starts with its row id.

Every test runs in a scratch repository under a scratch HOME, with a scratch denylist of
invented patterns. The suite never opens a real denylist: ROBOWRIGHT_DENYLIST always names a
scratch file or is removed, and HOME always points at a scratch directory.

A hit names the denylist line, never the pattern (rule 7): on SCRATCH_DENYLIST, `forbidden-token`
is `denylist:2` and `example-secret-[0-9]+` is `denylist:3`, the comment line being line 1.

Run from the repository root:  python3 tests/scrub-gate/test_scrub_gate.py
"""

from __future__ import annotations

import os
import re
import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
TOOLS = REPO / "tools"

ZERO_OID = "0" * 40
TIMEOUT_S = 60

# A line in the rules' hit shape: `scrub: <file>:<line>: denylist:<n>`.
HIT_LINE = re.compile(r"^scrub: .+:\d+: denylist:\d+$")

# Any line that reads like a hit: a `denylist:<n>` or any `<file>:<line>: ` shape, including one naming a pattern.
HIT_SHAPED = re.compile(r"denylist:\d|:\d+: ")

SCRATCH_DENYLIST = (
    "# synthetic patterns for the scrub-gate suite\n"
    "forbidden-token\n"
    "example-secret-[0-9]+\n"
)


def scrubbed_env(home: Path, denylist: Path | None) -> dict[str, str]:
    """The inherited environment minus anything that points git or the gate outside the scratch dir."""
    env = {
        key: value
        for key, value in os.environ.items()
        if not key.startswith("GIT_") and key not in ("ROBOWRIGHT_DENYLIST", "XDG_CONFIG_HOME")
    }
    env["HOME"] = str(home)
    env["XDG_CONFIG_HOME"] = str(home / ".config")
    env["GIT_CONFIG_NOSYSTEM"] = "1"
    env["GIT_TERMINAL_PROMPT"] = "0"
    if denylist is not None:
        env["ROBOWRIGHT_DENYLIST"] = str(denylist)
    return env


def lines_of(proc: subprocess.CompletedProcess) -> list[str]:
    """stdout and stderr lines together — git passes hook output through on either."""
    return proc.stdout.splitlines() + proc.stderr.splitlines()


def hit_lines(text: str) -> list[str]:
    """The `scrub: <file>:<line>: denylist:<n>` lines of `text`, sorted — order is not part of the rules."""
    return sorted(line for line in text.splitlines() if HIT_LINE.match(line))


class ScratchRepoCase(unittest.TestCase):
    """A scratch repo with the worktree's tools/ copied in (untracked), hooks wired, and a bare `origin`."""

    def setUp(self) -> None:
        if not TOOLS.is_dir():
            self.fail(f"tools/ not found beside the suite: {TOOLS}")
        tmp = tempfile.TemporaryDirectory(prefix="scrub-gate-")
        self.addCleanup(tmp.cleanup)
        base = Path(tmp.name).resolve()
        self.base = base
        self.home = base / "home"
        self.work = base / "work"
        self.remote = base / "remote.git"
        self.denylist = base / "denylist"
        self.home.mkdir()
        self.work.mkdir()
        self.denylist.write_text(SCRATCH_DENYLIST)
        self.env = scrubbed_env(self.home, self.denylist)
        self.assertNotEqual(self.env["HOME"], os.environ.get("HOME"), "the suite must never run under the real HOME")

        self.git("init", "-q", "-b", "main")
        self.git("config", "user.name", "Sample Owner")
        self.git("config", "user.email", "owner@example.com")
        self.git("config", "core.hooksPath", "tools/hooks")
        shutil.copytree(TOOLS, self.work / "tools")
        exclude = self.work / ".git" / "info" / "exclude"
        exclude.parent.mkdir(parents=True, exist_ok=True)
        with exclude.open("a") as handle:
            handle.write("/tools/\n")
        self.run_cmd(["git", "init", "-q", "--bare", str(self.remote)], cwd=base)
        self.git("remote", "add", "origin", str(self.remote))

    # -- plumbing ---------------------------------------------------------------------------

    def run_cmd(self, argv, *, cwd=None, env=None, check=True, stdin_text=None) -> subprocess.CompletedProcess:
        proc = subprocess.run(
            argv,
            cwd=cwd or self.work,
            env=env if env is not None else self.env,
            input=stdin_text,
            stdin=None if stdin_text is not None else subprocess.DEVNULL,
            capture_output=True,
            text=True,
            errors="replace",
            timeout=TIMEOUT_S,
        )
        if check and proc.returncode != 0:
            self.fail(f"setup command failed: {argv}\n{proc.stdout}{proc.stderr}")
        return proc

    def git(self, *args, check=True, env=None) -> subprocess.CompletedProcess:
        return self.run_cmd(["git", *args], check=check, env=env)

    def gate(self, *args, env=None) -> subprocess.CompletedProcess:
        return self.run_cmd([str(self.work / "tools" / "scrub-gate.sh"), *args], check=False, env=env)

    def env_without_denylist_var(self) -> dict[str, str]:
        return scrubbed_env(self.home, None)

    def env_naming(self, denylist: Path) -> dict[str, str]:
        return scrubbed_env(self.home, denylist)

    def write(self, relpath: str, *lines: str) -> None:
        path = self.work / relpath
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text("".join(f"{line}\n" for line in lines))

    def write_default_denylist(self, text: str) -> Path:
        path = self.home / ".config" / "robowright" / "denylist"
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text)
        return path

    def stage_all(self) -> None:
        self.git("add", "-A")

    def commit_ungated(self, message: str) -> str:
        """Commit everything with the hook bypassed — a Given, never the behavior under test."""
        self.stage_all()
        self.git("commit", "-q", "--no-verify", "-m", message)
        return self.head()

    def push_ungated(self, *args: str) -> None:
        """Push with the hook bypassed — a Given, never the behavior under test."""
        self.git("push", "-q", "--no-verify", *args)

    def given_base_commit(self) -> str:
        self.write("readme.txt", "sample project")
        return self.commit_ungated("base")

    def head(self) -> str | None:
        proc = self.git("rev-parse", "--verify", "-q", "HEAD", check=False)
        return proc.stdout.strip() or None

    def remote_ref(self, branch: str) -> str | None:
        proc = self.run_cmd(
            ["git", "--git-dir", str(self.remote), "rev-parse", "--verify", "-q", f"refs/heads/{branch}"],
            check=False,
        )
        return proc.stdout.strip() or None


# MARK: - R1 · a commit whose added lines match is refused; a removed line is not a hit


class R1AddedLines(ScratchRepoCase):

    def test_refuses_naming_file_line_and_denylist_line__when_a_staged_added_line_matches(self):
        """R1.1 · a staged hit is refused with its file, line and denylist line — a silent pass leaks the line into history."""
        self.given_base_commit()
        self.write("notes.txt", "alpha", "forbidden-token here", "charlie")
        self.stage_all()

        result = self.gate("--cached")

        self.assertEqual(result.returncode, 1)
        self.assertEqual(hit_lines(result.stdout), ["scrub: notes.txt:2: denylist:2"])

    def test_passes__when_the_only_matching_line_is_staged_for_removal(self):
        """R1.2 · removing a matching line is not a hit — otherwise a leak can never be cleaned up."""
        self.write("notes.txt", "alpha", "forbidden-token here", "charlie")
        self.commit_ungated("seed a hit")
        self.write("notes.txt", "alpha", "charlie")
        self.stage_all()

        result = self.gate("--cached")

        self.assertEqual(result.returncode, 0)
        self.assertIn("scrub: clean", result.stdout.splitlines())

    def test_reports_the_line_number_of_the_new_version__when_earlier_lines_were_removed(self):
        """R1.3 · <line> counts lines in the new file — an old-side number points the owner at the wrong line."""
        self.write("notes.txt", "alpha", "bravo", "charlie", "delta", "echo")
        self.commit_ungated("five lines")
        self.write("notes.txt", "bravo", "charlie", "forbidden-token here", "delta", "echo")
        self.stage_all()

        result = self.gate("--cached")

        self.assertEqual(result.returncode, 1)
        self.assertEqual(hit_lines(result.stdout), ["scrub: notes.txt:3: denylist:2"])

    def test_refuses__when_the_first_commit_of_a_repository_adds_a_matching_line(self):
        """R1.4 · the first commit is gated too — a repo with no HEAD would otherwise leak its whole seed."""
        self.write("notes.txt", "forbidden-token first")
        self.stage_all()

        result = self.gate("--cached")

        self.assertEqual(result.returncode, 1)
        self.assertEqual(hit_lines(result.stdout), ["scrub: notes.txt:1: denylist:2"])

    def test_git_commit_is_refused_and_names_the_hit__when_a_staged_line_matches(self):
        """R1.5 · the pre-commit hook stops a real commit — a gate nobody runs protects nothing."""
        before = self.given_base_commit()
        self.write("notes.txt", "alpha", "forbidden-token here")
        self.stage_all()

        result = self.git("commit", "-m", "add notes", check=False)

        self.assertNotEqual(result.returncode, 0)
        self.assertEqual(self.head(), before)
        self.assertIn("scrub: notes.txt:2: denylist:2", lines_of(result))

    def test_git_commit_lands__when_no_staged_line_matches(self):
        """R1.6 · a clean commit goes through the hook — a gate that refuses everything gets bypassed."""
        before = self.given_base_commit()
        self.write("notes.txt", "alpha", "bravo")
        self.stage_all()

        result = self.git("commit", "-m", "add notes", check=False)

        self.assertEqual(result.returncode, 0, "\n".join(lines_of(result)))
        self.assertNotEqual(self.head(), before)


# MARK: - R2 · patterns match case-insensitively; `#` and blank denylist lines are not patterns


class R2Patterns(ScratchRepoCase):

    def test_matches_regardless_of_case_and_names_the_denylist_line(self):
        """R2.1 · FORBIDDEN-Token hits `forbidden-token` at denylist line 2 — a case change would slip a real name through."""
        self.given_base_commit()
        self.write("notes.txt", "alpha", "Found FORBIDDEN-Token again")
        self.stage_all()

        result = self.gate("--cached")

        self.assertEqual(result.returncode, 1)
        self.assertEqual(hit_lines(result.stdout), ["scrub: notes.txt:2: denylist:2"])

    def test_matches_a_pattern_as_an_extended_regular_expression(self):
        """R2.2 · `example-secret-[0-9]+` hits example-secret-42 — a fixed-string match misses every numbered secret."""
        self.given_base_commit()
        self.write("notes.txt", "alpha", "bravo", "key example-secret-42 end")
        self.stage_all()

        result = self.gate("--cached")

        self.assertEqual(result.returncode, 1)
        self.assertEqual(hit_lines(result.stdout), ["scrub: notes.txt:3: denylist:3"])

    def test_passes__when_a_line_falls_outside_the_regular_expression(self):
        """R2.3 · example-secret-x is not `example-secret-[0-9]+` — a loose match refuses innocent text."""
        self.given_base_commit()
        self.write("notes.txt", "alpha", "example-secret-x")
        self.stage_all()

        result = self.gate("--cached")

        self.assertEqual(result.returncode, 0)
        self.assertIn("scrub: clean", result.stdout.splitlines())

    def test_passes__when_a_line_matches_only_a_comment_line_of_the_denylist(self):
        """R2.4 · a `#` denylist line is not a pattern — otherwise comments refuse the text they describe."""
        self.denylist.write_text("# release-notes\nforbidden-token\n")
        self.given_base_commit()
        self.write("notes.txt", "# release-notes", "bravo")
        self.stage_all()

        result = self.gate("--cached")

        self.assertEqual(result.returncode, 0)
        self.assertIn("scrub: clean", result.stdout.splitlines())

    def test_passes__when_the_denylist_contains_an_empty_line(self):
        """R2.5 · an empty denylist line is not a pattern — an empty regex matches every line and refuses everything."""
        self.denylist.write_text("forbidden-token\n\nexample-secret-[0-9]+\n")
        self.given_base_commit()
        self.write("notes.txt", "alpha", "bravo")
        self.stage_all()

        result = self.gate("--cached")

        self.assertEqual(result.returncode, 0)
        self.assertIn("scrub: clean", result.stdout.splitlines())

    def test_passes__when_the_denylist_contains_a_whitespace_only_line(self):
        """R2.6 · a whitespace-only denylist line is blank — as a pattern it refuses every line with a space (assumed Q5)."""
        self.denylist.write_text("forbidden-token\n \nexample-secret-[0-9]+\n")
        self.given_base_commit()
        self.write("notes.txt", "alpha bravo")
        self.stage_all()

        result = self.gate("--cached")

        self.assertEqual(result.returncode, 0)
        self.assertIn("scrub: clean", result.stdout.splitlines())

    def test_reports_one_line_per_pattern__when_two_patterns_match_one_line(self):
        """R2.7 · each matching pattern is its own hit — naming only one hides the second leak (assumed Q3)."""
        self.given_base_commit()
        self.write("notes.txt", "forbidden-token beside example-secret-9")
        self.stage_all()

        result = self.gate("--cached")

        self.assertEqual(result.returncode, 1)
        self.assertEqual(
            hit_lines(result.stdout),
            ["scrub: notes.txt:1: denylist:2", "scrub: notes.txt:1: denylist:3"],
        )

    def test_passes__when_the_denylist_holds_only_comments_and_blank_lines(self):
        """R2.8 · a present denylist with no patterns has nothing to match — joining zero patterns must not match all (assumed Q6)."""
        self.denylist.write_text("# nothing listed yet\n\n")
        self.given_base_commit()
        self.write("notes.txt", "alpha")
        self.stage_all()

        result = self.gate("--cached")

        self.assertEqual(result.returncode, 0)
        self.assertIn("scrub: clean", result.stdout.splitlines())


# MARK: - R3 · ROBOWRIGHT_DENYLIST names the denylist, default under HOME; missing refuses with exit 2


class R3DenylistLocation(ScratchRepoCase):

    def test_uses_the_named_denylist_over_the_default__when_the_variable_is_set(self):
        """R3.1 · ROBOWRIGHT_DENYLIST wins over the default path — otherwise the override is ignored."""
        self.write_default_denylist("forbidden-token\n")
        self.denylist.write_text("example-secret-[0-9]+\n")
        self.given_base_commit()
        self.write("notes.txt", "forbidden-token here", "example-secret-7 here")
        self.stage_all()

        result = self.gate("--cached", env=self.env_naming(self.denylist))

        self.assertEqual(result.returncode, 1)
        self.assertEqual(hit_lines(result.stdout), ["scrub: notes.txt:2: denylist:1"])

    def test_uses_the_default_denylist_under_home__when_the_variable_is_unset(self):
        """R3.2 · unset, the denylist is $HOME/.config/robowright/denylist — the ordinary install reads nothing else."""
        self.write_default_denylist("forbidden-token\n")
        self.given_base_commit()
        self.write("notes.txt", "forbidden-token here")
        self.stage_all()

        result = self.gate("--cached", env=self.env_without_denylist_var())

        self.assertEqual(result.returncode, 1)
        self.assertEqual(hit_lines(result.stdout), ["scrub: notes.txt:1: denylist:1"])

    def test_uses_the_default_denylist__when_the_variable_is_empty(self):
        """R3.3 · an empty ROBOWRIGHT_DENYLIST means the default (`:-`) — otherwise an empty path is opened."""
        self.write_default_denylist("forbidden-token\n")
        self.given_base_commit()
        self.write("notes.txt", "forbidden-token here")
        self.stage_all()
        env = self.env_without_denylist_var()
        env["ROBOWRIGHT_DENYLIST"] = ""

        result = self.gate("--cached", env=env)

        self.assertEqual(result.returncode, 1)
        self.assertEqual(hit_lines(result.stdout), ["scrub: notes.txt:1: denylist:1"])

    def test_refuses_with_exit_2_naming_the_default_path__when_it_is_missing(self):
        """R3.4 · a missing default denylist is exit 2 naming where it looked — a pass here scrubs nothing."""
        self.given_base_commit()
        self.write("notes.txt", "alpha")
        self.stage_all()

        result = self.gate("--cached", env=self.env_without_denylist_var())

        self.assertEqual(result.returncode, 2)
        self.assertIn(f"{self.home}/.config/robowright/denylist", result.stdout + result.stderr)

    def test_refuses_with_exit_2_naming_the_path__when_the_named_denylist_is_missing(self):
        """R3.5 · a missing named denylist is exit 2 naming that path — a typo in the variable must not pass."""
        absent = self.base / "absent-denylist"
        self.given_base_commit()
        self.write("notes.txt", "alpha")
        self.stage_all()

        result = self.gate("--cached", env=self.env_naming(absent))

        self.assertEqual(result.returncode, 2)
        self.assertIn(str(absent), result.stdout + result.stderr)

    def test_git_commit_is_refused__when_the_denylist_is_missing(self):
        """R3.6 · the pre-commit hook passes the exit-2 refusal on — otherwise a fresh machine commits unscrubbed."""
        absent = self.base / "absent-denylist"
        before = self.given_base_commit()
        self.write("notes.txt", "alpha")
        self.stage_all()

        result = self.git("commit", "-m", "add notes", check=False, env=self.env_naming(absent))

        self.assertNotEqual(result.returncode, 0)
        self.assertEqual(self.head(), before)
        self.assertIn(str(absent), "\n".join(lines_of(result)))

    def test_git_push_is_refused__when_the_denylist_is_missing(self):
        """R3.7 · the pre-push hook passes the exit-2 refusal on — otherwise a fresh machine pushes unscrubbed."""
        absent = self.base / "absent-denylist"
        self.given_base_commit()

        result = self.git("push", "origin", "main", check=False, env=self.env_naming(absent))

        self.assertNotEqual(result.returncode, 0)
        self.assertIsNone(self.remote_ref("main"))
        self.assertIn(str(absent), "\n".join(lines_of(result)))


# MARK: - R4 · --cached reads the index, --range every commit in the range, --tree every tracked file


class R4Modes(ScratchRepoCase):

    # --cached

    def test_cached_passes__when_the_hit_is_only_in_an_unstaged_hunk(self):
        """R4.1 · --cached reads the index, not the working tree — otherwise unstaged scratch blocks a clean commit."""
        ten = ["alpha", "bravo", "charlie", "delta", "echo", "foxtrot", "golf", "hotel", "india", "juliet"]
        self.write("notes.txt", *ten)
        self.commit_ungated("ten lines")
        self.write("notes.txt", "alpha revised", *ten[1:])
        self.stage_all()
        self.write("notes.txt", "alpha revised", *ten[1:9], "juliet forbidden-token")

        result = self.gate("--cached")

        self.assertEqual(result.returncode, 0)
        self.assertIn("scrub: clean", result.stdout.splitlines())

    def test_cached_refuses_naming_the_new_path__when_a_file_with_a_matching_line_is_renamed(self):
        """R4.2 · a staged rename of a file with a hit is refused — rename detection would show no added lines (assumed Q2)."""
        self.write("draft.txt", "alpha", "forbidden-token here", "charlie")
        self.commit_ungated("seed a hit")
        self.git("mv", "draft.txt", "renamed.txt")

        result = self.gate("--cached")

        self.assertEqual(result.returncode, 1)
        self.assertEqual(hit_lines(result.stdout), ["scrub: renamed.txt:2: denylist:2"])

    # --range

    def test_range_reports_a_hit_added_by_an_intermediate_commit__though_a_later_commit_removes_it(self):
        """R4.3 · --range reads every commit, not the net diff — the pushed history still carries the line."""
        base = self.given_base_commit()
        self.write("notes.txt", "alpha", "forbidden-token here", "charlie")
        self.commit_ungated("add a hit")
        self.write("notes.txt", "alpha", "charlie")
        tip = self.commit_ungated("remove the hit")

        result = self.gate("--range", base, tip)

        self.assertEqual(result.returncode, 1)
        self.assertEqual(hit_lines(result.stdout), ["scrub: notes.txt:2: denylist:2"])

    def test_range_passes__when_the_hit_is_in_the_old_commit_itself(self):
        """R4.4 · <old> is outside the range — otherwise every push re-refuses what the remote already has."""
        self.given_base_commit()
        self.write("notes.txt", "alpha", "forbidden-token here", "charlie")
        old = self.commit_ungated("add a hit")
        self.write("notes.txt", "alpha", "charlie")
        tip = self.commit_ungated("remove the hit")

        result = self.gate("--range", old, tip)

        self.assertEqual(result.returncode, 0)
        self.assertIn("scrub: clean", result.stdout.splitlines())

    def test_range_from_zero_reads_every_commit__when_no_remote_has_any(self):
        """R4.5 · a zero <old> with nothing on a remote reads the whole history — tip-only misses the seed commit."""
        self.write("notes.txt", "alpha", "forbidden-token here")
        self.commit_ungated("add a hit")
        self.write("other.txt", "bravo")
        tip = self.commit_ungated("clean tip")

        result = self.gate("--range", ZERO_OID, tip)

        self.assertEqual(result.returncode, 1)
        self.assertEqual(hit_lines(result.stdout), ["scrub: notes.txt:2: denylist:2"])

    def test_range_from_zero_skips_commits_already_on_a_remote(self):
        """R4.6 · a zero <old> reads only commits on no remote — otherwise every new branch re-refuses old history."""
        self.write("notes.txt", "alpha", "forbidden-token here")
        self.commit_ungated("add a hit")
        self.push_ungated("origin", "main")
        self.git("checkout", "-q", "-b", "feature")
        self.write("other.txt", "bravo")
        tip = self.commit_ungated("clean feature commit")

        result = self.gate("--range", ZERO_OID, tip)

        self.assertEqual(result.returncode, 0)
        self.assertIn("scrub: clean", result.stdout.splitlines())

    def test_range_refuses_naming_the_new_path__when_a_commit_renames_a_file_with_a_matching_line(self):
        """R4.7 · a committed rename of a file with a hit is refused — rename detection would show no added lines (assumed Q8)."""
        self.write("draft.txt", "alpha", "forbidden-token here", "charlie")
        old = self.commit_ungated("seed a hit")
        self.git("mv", "draft.txt", "renamed.txt")
        self.git("commit", "-q", "--no-verify", "-m", "rename")
        tip = self.head()

        result = self.gate("--range", old, tip)

        self.assertEqual(result.returncode, 1)
        self.assertEqual(hit_lines(result.stdout), ["scrub: renamed.txt:2: denylist:2"])

    # --tree

    def test_tree_reports_a_hit_in_a_committed_tracked_file(self):
        """R4.8 · --tree reads every tracked file — history committed before the gate existed is found."""
        self.write("docs/guide.md", "intro", "usage", "forbidden-token appears here")
        self.commit_ungated("seed a hit")

        result = self.gate("--tree")

        self.assertEqual(result.returncode, 1)
        self.assertEqual(hit_lines(result.stdout), ["scrub: docs/guide.md:3: denylist:2"])

    def test_tree_passes__when_the_only_hit_is_in_an_untracked_file(self):
        """R4.9 · --tree reads tracked files only — a local scratch file is never published and must not refuse."""
        self.given_base_commit()
        self.write("scratch.txt", "forbidden-token")

        result = self.gate("--tree")

        self.assertEqual(result.returncode, 0)
        self.assertIn("scrub: clean", result.stdout.splitlines())

    def test_tree_reports_a_hit_in_an_uncommitted_edit_to_a_tracked_file(self):
        """R4.10 · --tree reads the tracked file as it is on disk — the release check must see the tree it ships (assumed Q7)."""
        self.write("docs/guide.md", "intro", "usage")
        self.commit_ungated("clean guide")
        self.write("docs/guide.md", "intro", "usage", "forbidden-token appears here")

        result = self.gate("--tree")

        self.assertEqual(result.returncode, 1)
        self.assertEqual(hit_lines(result.stdout), ["scrub: docs/guide.md:3: denylist:2"])


# MARK: - R5 (R7 since U2) · clean prints `scrub: clean` and exits 0; hits print one line each and exit 1


class R5Output(ScratchRepoCase):

    def test_prints_scrub_clean_and_exits_0__when_nothing_matches(self):
        """R5.1 · a clean run says `scrub: clean` and exits 0 — callers and the runner read exactly that."""
        self.given_base_commit()
        self.write("notes.txt", "alpha", "bravo")
        self.stage_all()

        result = self.gate("--cached")

        self.assertEqual(result.returncode, 0)
        self.assertIn("scrub: clean", result.stdout.splitlines())
        self.assertEqual(hit_lines(result.stdout), [])

    def test_prints_one_line_per_hit_and_no_clean_line__when_two_files_have_hits(self):
        """R5.2 · every hit gets its own line and the run is not called clean — stopping at the first hides the rest (assumed Q1)."""
        self.given_base_commit()
        self.write("notes.txt", "forbidden-token one")
        self.write("docs/guide.md", "intro", "example-secret-12 two")
        self.stage_all()

        result = self.gate("--cached")

        self.assertEqual(result.returncode, 1)
        self.assertEqual(
            hit_lines(result.stdout),
            ["scrub: docs/guide.md:2: denylist:3", "scrub: notes.txt:1: denylist:2"],
        )
        self.assertNotIn("scrub: clean", result.stdout.splitlines())


# MARK: - R6 · pre-push runs the range check per stdin line; any hit aborts the push


class R6PrePush(ScratchRepoCase):

    def test_push_is_refused__when_a_new_branch_carries_a_hit_below_its_tip(self):
        """R6.1 · a first push reads every commit not on a remote — checking only the tip publishes the seed."""
        self.write("notes.txt", "alpha", "forbidden-token here")
        self.commit_ungated("add a hit")
        self.write("other.txt", "bravo")
        self.commit_ungated("clean tip")

        result = self.git("push", "origin", "main", check=False)

        self.assertNotEqual(result.returncode, 0)
        self.assertIsNone(self.remote_ref("main"))
        self.assertIn("scrub: notes.txt:2: denylist:2", lines_of(result))

    def test_push_lands__when_new_commits_are_clean_though_the_remote_branch_already_has_a_hit(self):
        """R6.2 · an update push reads only <remote-oid>..<local-oid> — re-reading old history blocks every push."""
        self.write("notes.txt", "alpha", "forbidden-token here")
        self.commit_ungated("add a hit")
        self.push_ungated("origin", "main")
        self.write("other.txt", "bravo")
        tip = self.commit_ungated("clean follow-up")

        result = self.git("push", "origin", "main", check=False)

        self.assertEqual(result.returncode, 0, "\n".join(lines_of(result)))
        self.assertEqual(self.remote_ref("main"), tip)

    def test_push_is_refused__when_a_new_commit_on_the_remote_branch_adds_a_hit(self):
        """R6.3 · an update push with a hit is aborted and the remote keeps its old tip — the leak is published otherwise."""
        remote_tip = self.given_base_commit()
        self.push_ungated("origin", "main")
        self.write("notes.txt", "alpha", "forbidden-token here")
        self.commit_ungated("add a hit")

        result = self.git("push", "origin", "main", check=False)

        self.assertNotEqual(result.returncode, 0)
        self.assertEqual(self.remote_ref("main"), remote_tip)
        self.assertIn("scrub: notes.txt:2: denylist:2", lines_of(result))

    def test_push_of_a_new_branch_lands__when_its_only_hit_is_already_on_the_remote(self):
        """R6.4 · a zero remote oid reads only commits on no remote — otherwise no branch off old history can be pushed."""
        self.write("notes.txt", "alpha", "forbidden-token here")
        self.commit_ungated("add a hit")
        self.push_ungated("origin", "main")
        self.git("checkout", "-q", "-b", "feature")
        self.write("other.txt", "bravo")
        tip = self.commit_ungated("clean feature commit")

        result = self.git("push", "origin", "feature", check=False)

        self.assertEqual(result.returncode, 0, "\n".join(lines_of(result)))
        self.assertEqual(self.remote_ref("feature"), tip)

    def test_force_push_lands__when_the_rewrite_drops_a_hit_the_remote_had(self):
        """R6.5 · a force-push whose remote oid is not an ancestor still reads just the new commits — the cleanup push must go through."""
        base = self.given_base_commit()
        self.write("notes.txt", "alpha", "forbidden-token here")
        self.commit_ungated("add a hit")
        self.push_ungated("origin", "main")
        self.git("reset", "-q", "--hard", base)
        self.write("other.txt", "bravo")
        rewritten = self.commit_ungated("clean rewrite")

        result = self.git("push", "--force", "origin", "main", check=False)

        self.assertEqual(result.returncode, 0, "\n".join(lines_of(result)))
        self.assertEqual(self.remote_ref("main"), rewritten)

    def test_force_push_is_refused__when_the_rewritten_commit_adds_a_hit(self):
        """R6.6 · a force-push of a rewrite that adds a hit is aborted — force must not bypass the gate."""
        base = self.given_base_commit()
        self.write("other.txt", "bravo")
        remote_tip = self.commit_ungated("clean commit")
        self.push_ungated("origin", "main")
        self.git("reset", "-q", "--hard", base)
        self.write("notes.txt", "alpha", "forbidden-token here")
        self.commit_ungated("rewrite with a hit")

        result = self.git("push", "--force", "origin", "main", check=False)

        self.assertNotEqual(result.returncode, 0)
        self.assertEqual(self.remote_ref("main"), remote_tip)
        self.assertIn("scrub: notes.txt:2: denylist:2", lines_of(result))

    def test_push_of_two_refs_lands_neither__when_one_carries_a_hit(self):
        """R6.7 · one hit among several pushed refs aborts the whole push — reading one line lets the other ref leak."""
        remote_tip = self.given_base_commit()
        self.push_ungated("origin", "main")
        self.git("checkout", "-q", "-b", "feature")
        self.write("notes.txt", "alpha", "forbidden-token here")
        self.commit_ungated("add a hit")
        self.git("checkout", "-q", "main")
        self.write("other.txt", "bravo")
        self.commit_ungated("clean main commit")

        result = self.git("push", "origin", "main", "feature", check=False)

        self.assertNotEqual(result.returncode, 0)
        self.assertEqual(self.remote_ref("main"), remote_tip)
        self.assertIsNone(self.remote_ref("feature"))

    def test_pre_push_fails__when_the_hit_is_on_the_second_stdin_line(self):
        """R6.8 · the hook checks every stdin line, not the first — a clean first ref must not wave the rest through."""
        self.given_base_commit()
        self.git("checkout", "-q", "-b", "feature")
        self.write("notes.txt", "alpha", "forbidden-token here")
        feature_tip = self.commit_ungated("add a hit")
        self.git("checkout", "-q", "main")
        self.write("other.txt", "bravo")
        main_tip = self.commit_ungated("clean main commit")
        stdin = (
            f"refs/heads/main {main_tip} refs/heads/main {ZERO_OID}\n"
            f"refs/heads/feature {feature_tip} refs/heads/feature {ZERO_OID}\n"
        )

        result = self.run_cmd(
            [str(self.work / "tools" / "hooks" / "pre-push"), "origin", str(self.remote)],
            check=False,
            stdin_text=stdin,
        )

        self.assertNotEqual(result.returncode, 0)
        self.assertIn("scrub: notes.txt:2: denylist:2", lines_of(result))

    def test_deleting_a_remote_branch_lands__even_when_its_commits_carry_a_hit(self):
        """R6.9 · a `(delete)` line adds nothing and is not a hit — otherwise a leaked branch can never be deleted (assumed Q9)."""
        self.given_base_commit()
        self.push_ungated("origin", "main")
        self.git("checkout", "-q", "-b", "feature")
        self.write("notes.txt", "alpha", "forbidden-token here")
        self.commit_ungated("add a hit")
        self.push_ungated("origin", "feature")
        self.git("checkout", "-q", "main")

        result = self.git("push", "origin", "--delete", "feature", check=False)

        self.assertEqual(result.returncode, 0, "\n".join(lines_of(result)))
        self.assertIsNone(self.remote_ref("feature"))


# MARK: - Held out · one example per rule the spec rows did not use


class HeldOut(ScratchRepoCase):

    def test_reports_each_hunk_at_its_own_new_line__when_one_file_gains_two_separate_hits(self):
        """H1 · R1 · two hunks in one file keep their own line numbers — a counter that ignores the second hunk header misplaces it."""
        ten = ["alpha", "bravo", "charlie", "delta", "echo", "foxtrot", "golf", "hotel", "india", "juliet"]
        self.write("notes.txt", *ten)
        self.commit_ungated("ten lines")
        self.write("notes.txt", "forbidden-token top", *ten[:8], "forbidden-token low", *ten[8:])
        self.stage_all()

        result = self.gate("--cached")

        self.assertEqual(result.returncode, 1)
        self.assertEqual(
            hit_lines(result.stdout),
            ["scrub: notes.txt:10: denylist:2", "scrub: notes.txt:1: denylist:2"],
        )

    def test_matches_lowercase_text__when_the_pattern_is_written_in_capitals(self):
        """H2 · R2 · case-insensitivity runs both ways — lowering only the text misses a pattern written in capitals."""
        self.denylist.write_text("Forbidden-TOKEN\n")
        self.given_base_commit()
        self.write("notes.txt", "a forbidden-token here")
        self.stage_all()

        result = self.gate("--cached")

        self.assertEqual(result.returncode, 1)
        self.assertEqual(hit_lines(result.stdout), ["scrub: notes.txt:1: denylist:1"])

    def test_reads_the_named_denylist__when_its_path_contains_a_space(self):
        """H3 · R3 · a denylist path with a space is one path — word-splitting it reads nothing or refuses a present file."""
        spaced = self.base / "deny list" / "patterns"
        spaced.parent.mkdir()
        spaced.write_text("forbidden-token\n")
        self.given_base_commit()
        self.write("notes.txt", "forbidden-token here")
        self.stage_all()

        result = self.gate("--cached", env=self.env_naming(spaced))

        self.assertEqual(result.returncode, 1)
        self.assertEqual(hit_lines(result.stdout), ["scrub: notes.txt:1: denylist:1"])

    def test_tree_reports_a_hit__when_it_is_in_a_file_read_before_another_tracked_file(self):
        """H4 · R4 · --tree keeps every file's lines — only the last file read would be checked otherwise."""
        self.write("a-first.txt", "forbidden-token here")
        self.write("z-last.txt", "clean")
        self.commit_ungated("two files")

        result = self.gate("--tree")

        self.assertEqual(result.returncode, 1)
        self.assertEqual(hit_lines(result.stdout), ["scrub: a-first.txt:1: denylist:2"])

    def test_range_reports_a_hit_in_the_tip__when_an_older_commit_in_the_range_is_clean(self):
        """H5 · R4 · --range keeps every commit's lines — only the oldest commit read would be checked otherwise."""
        base = self.given_base_commit()
        self.write("other.txt", "bravo")
        self.commit_ungated("clean")
        self.write("notes.txt", "forbidden-token here")
        tip = self.commit_ungated("hit at tip")

        result = self.gate("--range", base, tip)

        self.assertEqual(result.returncode, 1)
        self.assertEqual(hit_lines(result.stdout), ["scrub: notes.txt:1: denylist:2"])

    def test_names_the_file__when_its_path_contains_a_space(self):
        """H6 · R5 · the hit names a path with a space whole — a split or quoted path points the owner at no file."""
        self.given_base_commit()
        self.write("my notes/to do.txt", "forbidden-token here")
        self.stage_all()

        result = self.gate("--cached")

        self.assertEqual(result.returncode, 1)
        self.assertEqual(hit_lines(result.stdout), ["scrub: my notes/to do.txt:1: denylist:2"])

    def test_pre_push_fails__when_a_delete_line_precedes_a_line_with_a_hit(self):
        """H7 · R6 · a skipped `(delete)` line does not end the loop — the ref after it is still read."""
        self.given_base_commit()
        self.git("checkout", "-q", "-b", "feature")
        self.write("notes.txt", "forbidden-token here")
        feature_tip = self.commit_ungated("add a hit")
        stdin = (
            f"(delete) {ZERO_OID} refs/heads/old {ZERO_OID[:-1]}1\n"
            f"refs/heads/feature {feature_tip} refs/heads/feature {ZERO_OID}\n"
        )

        result = self.run_cmd(
            [str(self.work / "tools" / "hooks" / "pre-push"), "origin", str(self.remote)],
            check=False,
            stdin_text=stdin,
        )

        self.assertNotEqual(result.returncode, 0)
        self.assertIn("scrub: notes.txt:1: denylist:2", lines_of(result))


# MARK: - gate findings · a byte that is not UTF-8 hides nothing (reviews/U1-gate.md F1, F2)

# The macOS default locale; awk and grep read input as UTF-8 under it.
UTF8_LOCALE = "en_US.UTF-8"
# `naïve` in Latin-1: 0xEF alone is not valid UTF-8.
LATIN1_LINE = b"na\xefve note"


class NonUtf8Content(ScratchRepoCase):

    def utf8_env(self) -> dict[str, str]:
        return dict(self.env, LANG=UTF8_LOCALE, LC_ALL=UTF8_LOCALE)

    def write_bytes(self, relpath: str, *lines: bytes) -> None:
        (self.work / relpath).write_bytes(b"".join(line + b"\n" for line in lines))

    def test_cached_refuses__when_a_non_utf8_file_is_staged_ahead_of_a_hit(self):
        """G1 · R1 · a Latin-1 file read first does not end the scan of the files after it."""
        self.given_base_commit()
        self.write_bytes("a-latin.txt", LATIN1_LINE)
        self.write("z-plain.txt", "forbidden-token in z")
        self.stage_all()

        result = self.gate("--cached", env=self.utf8_env())

        self.assertEqual(result.returncode, 1)
        self.assertEqual(hit_lines(result.stdout), ["scrub: z-plain.txt:1: denylist:2"])

    def test_cached_refuses__when_the_hit_is_on_a_non_utf8_line(self):
        """G2 · R1 · a matching line that is not valid UTF-8 is still a hit."""
        self.given_base_commit()
        self.write_bytes("a-latin.txt", b"first", LATIN1_LINE + b" forbidden-token")
        self.stage_all()

        result = self.gate("--cached", env=self.utf8_env())

        self.assertEqual(result.returncode, 1)
        self.assertEqual(hit_lines(result.stdout), ["scrub: a-latin.txt:2: denylist:2"])

    def test_range_refuses__when_a_commit_adds_a_non_utf8_file_ahead_of_a_hit(self):
        """G3 · R4, R6 · the pre-push range check reads past a Latin-1 file too."""
        base = self.given_base_commit()
        self.write_bytes("a-latin.txt", LATIN1_LINE)
        self.write("z-plain.txt", "forbidden-token in z")
        tip = self.commit_ungated("latin-1 ahead of a hit")

        result = self.gate("--range", base, tip, env=self.utf8_env())

        self.assertEqual(result.returncode, 1)
        self.assertEqual(hit_lines(result.stdout), ["scrub: z-plain.txt:1: denylist:2"])

    def test_tree_reports_a_hit__when_it_is_in_a_non_utf8_tracked_file(self):
        """G4 · R4 · --tree reads every tracked file, a Latin-1 one included."""
        self.write_bytes("a-latin.txt", b"first", LATIN1_LINE + b" forbidden-token")
        self.commit_ungated("latin-1 file with a hit")

        result = self.gate("--tree", env=self.utf8_env())

        self.assertEqual(result.returncode, 1)
        self.assertEqual(hit_lines(result.stdout), ["scrub: a-latin.txt:2: denylist:2"])

    def test_matches_a_non_ascii_pattern_regardless_of_case(self):
        """G5 · R2 · case-insensitivity is not limited to ASCII letters."""
        self.denylist.write_text("ëvarnoq\n", encoding="utf-8")
        self.given_base_commit()
        self.write("a.txt", "Contact Ëvarnoq today")
        self.stage_all()

        result = self.gate("--cached", env=self.utf8_env())

        self.assertEqual(result.returncode, 1)
        self.assertEqual(hit_lines(result.stdout), ["scrub: a.txt:1: denylist:1"])


# MARK: - gate findings · what git shows is not what was added (reviews/U1-gate-2.md F2, F3)

class WhatGitShows(ScratchRepoCase):

    def test_cached_reads_the_added_lines__when_a_textconv_driver_would_hide_them(self):
        """G6 · R1 · a diff textconv driver does not stand in for the added lines."""
        self.write(".gitattributes", "*.cfg diff=first")
        self.commit_ungated("attributes")
        self.git("config", "diff.first.textconv", "head -1")
        self.write("app.cfg", "name = sample", "forbidden-token here")
        self.stage_all()

        result = self.gate("--cached")

        self.assertEqual(result.returncode, 1)
        self.assertEqual(hit_lines(result.stdout), ["scrub: app.cfg:2: denylist:2"])

    def test_cached_reads_the_added_lines__when_an_attribute_marks_the_file_binary(self):
        """G7 · R1 · a `-diff` attribute does not turn added lines into "Binary files differ"."""
        self.write(".gitattributes", "*.cfg -diff")
        self.commit_ungated("attributes")
        self.write("app.cfg", "forbidden-token here")
        self.stage_all()

        result = self.gate("--cached")

        self.assertEqual(result.returncode, 1)
        self.assertEqual(hit_lines(result.stdout), ["scrub: app.cfg:1: denylist:2"])

    def test_cached_reads_past_a_nul_byte_in_an_added_line(self):
        """G8 · R1 · a NUL before the matching text does not cut the line short."""
        self.given_base_commit()
        (self.work / "n.txt").write_bytes(b"x" * 9000 + b"\n" + b"pre\x00 forbidden-token\n")
        self.stage_all()

        result = self.gate("--cached")

        self.assertEqual(result.returncode, 1)
        self.assertEqual(hit_lines(result.stdout), ["scrub: n.txt:2: denylist:2"])

    def test_tree_reports_a_hit_in_a_tracked_binary_file(self):
        """G9 · R4 · --tree reads every tracked file, one holding NUL bytes included."""
        (self.work / "blob.bin").write_bytes(b"\x00\x01\x02\nforbidden-token\n")
        self.commit_ungated("binary file with a hit")

        result = self.gate("--tree")

        self.assertEqual(result.returncode, 1)
        self.assertEqual(hit_lines(result.stdout), ["scrub: blob.bin:2: denylist:2"])


# MARK: - R7 · a hit names its denylist line; no output carries any part of a pattern's text


class R7DenylistLine(ScratchRepoCase):

    def test_names_the_denylist_line_counting_comments_and_blanks_and_prints_no_pattern_text__on_a_hit(self):
        """R7.1 · the hit reads `denylist:5` and neither stream holds `quokka`, `zebra` or `[0-9]` — a printed pattern publishes the private list through every log (assumed Q16)."""
        self.denylist.write_text(
            "# synthetic patterns for the leak check\n"
            "\n"
            "forbidden-token\n"
            "# a second comment\n"
            "quokka-[0-9]+-zebra\n"
        )
        self.given_base_commit()
        self.write("notes.txt", "a quokka-42-zebra b")
        self.stage_all()

        result = self.gate("--cached")

        self.assertEqual(result.returncode, 1)
        self.assertEqual(hit_lines(result.stdout), ["scrub: notes.txt:1: denylist:5"])
        output = (result.stdout + result.stderr).lower()
        self.assertNotIn("quokka", output)
        self.assertNotIn("zebra", output)
        self.assertNotIn("[0-9]", output)

    def test_counts_denylist_lines_from_1__when_the_matching_pattern_is_on_the_first_line(self):
        """R7.2 · the first line is `denylist:1` — a count from 0 sends the owner to the line above the pattern."""
        self.denylist.write_text("forbidden-token\n# a trailing comment\n")
        self.given_base_commit()
        self.write("notes.txt", "forbidden-token here")
        self.stage_all()

        result = self.gate("--cached")

        self.assertEqual(result.returncode, 1)
        self.assertEqual(hit_lines(result.stdout), ["scrub: notes.txt:1: denylist:1"])

    def test_counts_a_whitespace_only_denylist_line__when_a_pattern_after_it_matches(self):
        """R7.3 · a whitespace-only line is blank and blank lines count, so the pattern after it is `denylist:3` — skipping it points one line short (assumed Q5)."""
        self.denylist.write_text("forbidden-token\n \nexample-secret-[0-9]+\n")
        self.given_base_commit()
        self.write("notes.txt", "key example-secret-5 end")
        self.stage_all()

        result = self.gate("--cached")

        self.assertEqual(result.returncode, 1)
        self.assertEqual(hit_lines(result.stdout), ["scrub: notes.txt:1: denylist:3"])

    def test_refuses_naming_the_denylist_line_and_no_pattern_text__when_a_pattern_is_unusable(self):
        """R7.4 · an unusable pattern is reported as `denylist:3` and never quoted — the regex engine's own error message is where a pattern leaks (assumed Q13, Q16)."""
        self.denylist.write_text("# synthetic patterns\nforbidden-token\nzqx-[wvu\n")
        self.given_base_commit()
        self.write("notes.txt", "alpha")
        self.stage_all()

        result = self.gate("--cached")

        self.assertEqual(result.returncode, 2)
        output = result.stdout + result.stderr
        self.assertRegex(output, r"(?m)^scrub: .*denylist:3\b")
        self.assertNotIn("zqx", output.lower())
        self.assertNotIn("wvu", output.lower())

    def test_prints_no_part_of_a_pattern_holding_a_colon_and_digits__when_a_backslash_name_is_tracked_before_the_hit(self):
        r"""R7.5 · `zqx:12: wvu` behind a tracked `a\nb\tc` still prints only `denylist:2` — a cut after `:12: ` kept part of the pattern (U2-gate-3 F1 B; assumed Q16)."""
        self.denylist.write_text("# synthetic patterns\nzqx:12: wvu\n")
        self.write("a\\nb\\tc", "clean line")
        self.write("c.md", "ZQX:12: WVU here")
        self.commit_ungated("backslash name ahead of a hit")

        result = self.gate("--tree")

        self.assertEqual(result.returncode, 1)
        self.assertEqual(hit_lines(result.stdout), ["scrub: c.md:1: denylist:2"])
        output = (result.stdout + result.stderr).lower()
        self.assertNotIn("zqx", output)
        self.assertNotIn("wvu", output)


# MARK: - R8 · a file name prints as git lists it; record alignment does not depend on its characters


class R8FileNames(ScratchRepoCase):

    def test_tree_names_a_file_holding_a_backslash_unchanged__when_it_holds_a_hit(self):
        r"""R8.1 · tracked `a\nb` prints as `a\nb`, backslash and all — an escape-expanded or quoted name points the owner at no file (assumed Q12)."""
        self.write("a\\nb", "forbidden-token here")
        self.commit_ungated("backslash name with a hit")

        result = self.gate("--tree")

        self.assertEqual(result.returncode, 1)
        self.assertEqual(hit_lines(result.stdout), ["scrub: a\\nb:1: denylist:2"])

    def test_tree_names_the_hit_s_own_file_and_line__when_a_backslash_name_is_listed_before_it(self):
        r"""R8.2 · `a\nb\tdenylist not found` listed first leaves `c.md:2` whole — an escape-expanded name shifted every later record (U2-gate-3 F1 A)."""
        self.write("a\\nb\\tdenylist not found", "one line of text")
        self.write("c.md", "intro", "forbidden-token here")
        self.commit_ungated("backslash name ahead of a hit")

        result = self.gate("--tree")

        self.assertEqual(result.returncode, 1)
        self.assertEqual(
            [line for line in lines_of(result) if HIT_SHAPED.search(line)],
            ["scrub: c.md:2: denylist:2"],
        )

    def test_cached_names_a_staged_file_holding_a_backslash_unchanged__when_it_holds_a_hit(self):
        r"""R8.3 · staged `a\nb` prints as `a\nb` at pre-commit too — a diff header's quoting is not the name (assumed Q12)."""
        self.given_base_commit()
        self.write("a\\nb", "alpha", "forbidden-token here")
        self.stage_all()

        result = self.gate("--cached")

        self.assertEqual(result.returncode, 1)
        self.assertEqual(hit_lines(result.stdout), ["scrub: a\\nb:2: denylist:2"])

    def test_tree_names_a_file_holding_a_tab_unchanged__when_it_holds_a_hit(self):
        """R8.4 · a tab in a tracked name prints as a tab — a tab-separated record would split the name (assumed Q12)."""
        self.write("a\tb.txt", "forbidden-token here")
        self.commit_ungated("tab name with a hit")

        result = self.gate("--tree")

        self.assertEqual(result.returncode, 1)
        self.assertEqual(hit_lines(result.stdout), ["scrub: a\tb.txt:1: denylist:2"])

    def test_tree_names_a_file_holding_a_colon_with_its_own_line__when_it_holds_a_hit(self):
        """R8.5 · `docs/a:b.md` line 4 prints whole — a record split at the first colon reads `b.md` as the line."""
        self.write("docs/a:b.md", "one", "two", "three", "forbidden-token here")
        self.commit_ungated("colon name with a hit")

        result = self.gate("--tree")

        self.assertEqual(result.returncode, 1)
        self.assertEqual(hit_lines(result.stdout), ["scrub: docs/a:b.md:4: denylist:2"])

    def test_tree_names_a_file_holding_non_ascii_letters_unchanged__when_it_holds_a_hit(self):
        """R8.6 · `été.md` prints as `été.md`, not git's octal quoting — `"\\303\\251t\\303\\251.md"` is no path the owner can open (assumed Q12)."""
        self.write("été.md", "forbidden-token here")
        self.commit_ungated("non-ascii name with a hit")

        result = self.gate("--tree")

        self.assertEqual(result.returncode, 1)
        self.assertEqual(hit_lines(result.stdout), ["scrub: été.md:1: denylist:2"])


# MARK: - R9 · a tracked name holding a newline refuses with exit 2 and its count, and prints no hit


class R9NewlineNames(ScratchRepoCase):

    def test_tree_refuses_with_exit_2_naming_the_count_and_prints_no_hit__when_three_tracked_names_hold_a_newline(self):
        """R9.1 · three tracked names with a newline: exit 2, the count 3 on stderr, no hit line — a hit on a split name is a line that names no file (assumed Q14)."""
        self.write("one\nname.txt", "forbidden-token here")
        self.write("two\nname.txt", "alpha")
        self.write("three\nname.txt", "bravo")
        self.write("notes.txt", "forbidden-token here")
        self.commit_ungated("names with newlines")

        result = self.gate("--tree")

        self.assertEqual(result.returncode, 2)
        self.assertRegex(result.stderr, r"(?m)^scrub: .*\b3\b")
        self.assertEqual([line for line in lines_of(result) if HIT_SHAPED.search(line)], [])

    def test_cached_refuses_with_exit_2_naming_the_count_and_prints_no_hit__when_three_staged_names_hold_a_newline(self):
        """R9.2 · pre-commit refuses three staged names with a newline the same way — the commit that adds them is the one to stop (assumed Q14, Q15)."""
        self.given_base_commit()
        self.write("one\nname.txt", "forbidden-token here")
        self.write("two\nname.txt", "alpha")
        self.write("three\nname.txt", "bravo")
        self.write("notes.txt", "forbidden-token here")
        self.stage_all()

        result = self.gate("--cached")

        self.assertEqual(result.returncode, 2)
        self.assertRegex(result.stderr, r"(?m)^scrub: .*\b3\b")
        self.assertEqual([line for line in lines_of(result) if HIT_SHAPED.search(line)], [])

    def test_range_refuses_with_exit_2_naming_the_count_and_prints_no_hit__when_a_pushed_commit_adds_three_names_holding_a_newline(self):
        """R9.3 · pre-push refuses a range whose commit adds three names with a newline — the push is where a misprinted hit is published (assumed Q14, Q15)."""
        base = self.given_base_commit()
        self.write("one\nname.txt", "forbidden-token here")
        self.write("two\nname.txt", "alpha")
        self.write("three\nname.txt", "bravo")
        self.write("notes.txt", "forbidden-token here")
        tip = self.commit_ungated("names with newlines")

        result = self.gate("--range", base, tip)

        self.assertEqual(result.returncode, 2)
        self.assertRegex(result.stderr, r"(?m)^scrub: .*\b3\b")
        self.assertEqual([line for line in lines_of(result) if HIT_SHAPED.search(line)], [])


# MARK: - Held out · one example per U2 rule, written after the implementation and run once


class HeldOutU2(ScratchRepoCase):

    def test_range_names_the_denylist_line__when_the_denylist_has_crlf_line_endings(self):
        """H8 · R7 · a CRLF denylist still counts its comment and blank lines — `denylist:3` at pre-push."""
        self.denylist.write_bytes(b"# synthetic\r\n\r\nforbidden-token\r\n")
        base = self.given_base_commit()
        self.write("notes.txt", "forbidden-token here")
        tip = self.commit_ungated("hit")

        result = self.gate("--range", base, tip)

        self.assertEqual(result.returncode, 1)
        self.assertEqual(hit_lines(result.stdout), ["scrub: notes.txt:1: denylist:3"])

    def test_range_names_a_backslash_file_and_the_file_after_it__when_both_hold_a_hit(self):
        r"""H9 · R8 · pushed `a\nb` and `b.md` each keep their own name — a quoted header name is not the file."""
        base = self.given_base_commit()
        self.write("a\\nb", "forbidden-token here")
        self.write("b.md", "alpha", "forbidden-token here")
        tip = self.commit_ungated("backslash name and a hit after it")

        result = self.gate("--range", base, tip)

        self.assertEqual(result.returncode, 1)
        self.assertEqual(
            sorted(hit_lines(result.stdout)),
            ["scrub: a\\nb:1: denylist:2", "scrub: b.md:2: denylist:2"],
        )

    def test_cached_refuses_with_exit_2_and_the_count__when_one_staged_name_holds_a_newline_and_nothing_matches(self):
        """H10 · R9 · one newline name refuses though no line matches — the refusal is about the name, not a hit."""
        self.given_base_commit()
        self.write("odd\nname.txt", "alpha")
        self.stage_all()

        result = self.gate("--cached")

        self.assertEqual(result.returncode, 2)
        self.assertRegex(result.stderr, r"(?m)^scrub: .*\b1\b")
        self.assertNotIn("scrub: clean", result.stdout)


# MARK: - Gate findings on U2 · a diff that is not one header per name; a newline name the change removes


class U2GateFindings(ScratchRepoCase):

    def test_range_names_the_hit_s_own_file__when_the_same_commit_turns_a_file_into_a_symlink(self):
        """G10 · R8 · a file turned into a symlink is two diff sections for one name — the hit in `m.txt` stays `m.txt:3`, not the next file's name."""
        self.write("a.txt", "alpha")
        self.write("m.txt", "one", "two", "three")
        self.write("z.txt", "zulu")
        base = self.commit_ungated("base")
        (self.work / "a.txt").unlink()
        os.symlink("m.txt", self.work / "a.txt")
        self.write("m.txt", "one", "two", "forbidden-token here")
        self.write("z.txt", "zulu", "yankee")
        tip = self.commit_ungated("symlink, hit, harmless change")

        result = self.gate("--range", base, tip)

        self.assertEqual(result.returncode, 1)
        self.assertEqual(hit_lines(result.stdout), ["scrub: m.txt:3: denylist:2"])

    def test_cached_names_the_hit_s_own_file__when_a_submodule_bump_is_staged_under_diff_submodule_log(self):
        """G11 · R8 · `diff.submodule=log` drops the submodule's diff header — the hit in `z.txt` stays `z.txt:1`, not the submodule's path."""
        source = self.base / "subsource"
        source.mkdir()
        self.run_cmd(["git", "init", "-q", "-b", "main"], cwd=source)
        self.run_cmd(["git", "-c", "user.name=S", "-c", "user.email=s@example.com", "commit", "-q", "--allow-empty", "-m", "one"], cwd=source)
        self.git("-c", "protocol.file.allow=always", "submodule", "add", "-q", str(source), "a-sub")
        self.commit_ungated("add submodule")
        self.run_cmd(["git", "-c", "user.name=S", "-c", "user.email=s@example.com", "commit", "-q", "--allow-empty", "-m", "two"], cwd=self.work / "a-sub")
        self.git("config", "diff.submodule", "log")
        self.write("z.txt", "forbidden-token here")
        self.stage_all()

        result = self.gate("--cached")

        self.assertEqual(result.returncode, 1)
        self.assertEqual(hit_lines(result.stdout), ["scrub: z.txt:1: denylist:2"])

    def test_cached_passes__when_the_change_renames_a_newline_name_to_a_plain_one(self):
        """G12 · R9 · a newline name the change removes is never reported, so it is not refused — the gate's own advice, rename it, must commit."""
        self.write("odd\nname.txt", "alpha")
        self.commit_ungated("newline name")
        self.git("mv", "odd\nname.txt", "plain.txt")

        result = self.gate("--cached")

        self.assertEqual(result.returncode, 0)
        self.assertEqual(result.stdout.strip(), "scrub: clean")

    def test_cached_reports_every_hit__when_run_from_a_subdirectory(self):
        """G13 · R1 · run by hand from `sub/`, every staged hit in the repository is still named — a root-relative name read as a cwd-relative path matched nothing."""
        self.given_base_commit()
        self.write("sub/hit.txt", "forbidden-token here")
        self.write("other/hit.txt", "forbidden-token here")
        self.write("top.txt", "forbidden-token here")
        self.stage_all()

        result = self.run_cmd([str(self.work / "tools" / "scrub-gate.sh"), "--cached"], cwd=self.work / "sub", check=False)

        self.assertEqual(result.returncode, 1)
        self.assertEqual(
            sorted(hit_lines(result.stdout)),
            ["scrub: other/hit.txt:1: denylist:2", "scrub: sub/hit.txt:1: denylist:2", "scrub: top.txt:1: denylist:2"],
        )

    def test_cached_names_a_decomposed_unicode_name_as_stored__when_it_holds_a_hit(self):
        """G14 · R8 · an index name in decomposed form (`e` + U+0301) is read and printed as stored — macOS git precomposes a pathspec, which then matched nothing."""
        self.given_base_commit()
        blob = self.run_cmd(["git", "hash-object", "-w", "--stdin"], stdin_text="forbidden-token here\n").stdout.strip()
        # Through stdin: git on macOS precomposes a name given on the command line.
        self.run_cmd(["git", "update-index", "--add", "--index-info"], stdin_text=f"100644 blob {blob}\tcafé.txt\n")

        result = self.gate("--cached")

        self.assertEqual(result.returncode, 1)
        self.assertEqual(hit_lines(result.stdout), ["scrub: café.txt:1: denylist:2"])


# MARK: - U5 · a file name is content (R10–R13), written before the gate changed

# N in BEHAVIORS.md: on SCRATCH_DENYLIST it matches `forbidden-token` (denylist:2) and no other line.
MATCHING_NAME = "wombat-forbidden-token-kestrel.md"


class NameContentCase(ScratchRepoCase):
    """Plumbing shared by the U5 rows: the no-leak check, and the gate run by hand from `sub/`."""

    def assert_output_holds_none_of(self, result: subprocess.CompletedProcess, *words: str) -> None:
        """Neither stream holds any of `words`, in any case (Q21)."""
        output = (result.stdout + result.stderr).lower()
        self.assertEqual([word for word in words if word in output], [])

    def given_relative_denylist(self) -> str:
        """SCRATCH_DENYLIST beside the scratch repo, named relative to `sub/`; from the repository root the same text names no file."""
        name = f"{self.base.name}.denylist"
        (self.base / name).write_text(SCRATCH_DENYLIST)
        return f"../../{name}"

    def gate_from_subdirectory(self, *args: str, denylist: str) -> subprocess.CompletedProcess:
        """The gate run by hand from `sub/`, with `ROBOWRIGHT_DENYLIST` set to `denylist` exactly as given."""
        return self.run_cmd(
            [str(self.work / "tools" / "scrub-gate.sh"), *args],
            cwd=self.work / "sub",
            env=self.env_naming(Path(denylist)),
            check=False,
        )


class R10NamesAreContent(NameContentCase):

    def test_cached_withholds_the_name_in_both_hit_lines__when_a_staged_file_s_name_and_line_both_match(self):
        """R10.1 · `--cached`: the name is `(name withheld):0: denylist:2`, its line `(name withheld):2: denylist:3`, no word of either in any stream — a name printed as listed publishes the pattern through every log (assumed Q21)."""
        self.given_base_commit()
        self.write(MATCHING_NAME, "alpha", "key example-secret-7 end")
        self.stage_all()

        result = self.gate("--cached")

        self.assertEqual(result.returncode, 1)
        self.assertEqual(
            hit_lines(result.stdout),
            ["scrub: (name withheld):0: denylist:2", "scrub: (name withheld):2: denylist:3"],
        )
        self.assert_output_holds_none_of(result, "wombat", "forbidden", "token", "kestrel", "example", "secret")

    def test_range_withholds_the_name_in_both_hit_lines__when_a_commit_adds_a_file_whose_name_and_line_both_match(self):
        """R10.2 · `--range`: a pushed commit adding a matching name is withheld as at pre-commit — the push gate must not publish what the commit gate hides (assumed Q21)."""
        base = self.given_base_commit()
        self.write(MATCHING_NAME, "alpha", "key example-secret-7 end")
        tip = self.commit_ungated("add a plan")

        result = self.gate("--range", base, tip)

        self.assertEqual(result.returncode, 1)
        self.assertEqual(
            hit_lines(result.stdout),
            ["scrub: (name withheld):0: denylist:2", "scrub: (name withheld):2: denylist:3"],
        )
        self.assert_output_holds_none_of(result, "wombat", "forbidden", "token", "kestrel", "example", "secret")

    def test_tree_withholds_the_name_in_both_hit_lines__when_a_tracked_file_s_name_and_line_both_match(self):
        """R10.3 · `--tree`: a tracked matching name is withheld in both lines — the whole-tree backstop writes straight into evidence (assumed Q21)."""
        self.given_base_commit()
        self.write(MATCHING_NAME, "alpha", "key example-secret-7 end")
        self.commit_ungated("add a plan")

        result = self.gate("--tree")

        self.assertEqual(result.returncode, 1)
        self.assertEqual(
            hit_lines(result.stdout),
            ["scrub: (name withheld):0: denylist:2", "scrub: (name withheld):2: denylist:3"],
        )
        self.assert_output_holds_none_of(result, "wombat", "forbidden", "token", "kestrel", "example", "secret")

    def test_cached_withholds_a_clean_file_s_name__when_its_directory_s_name_matches(self):
        """R10.4 · a clean file under a matching directory is a name hit, and no `scrub: clean` — a directory prints as part of every path under it (assumed Q21)."""
        self.given_base_commit()
        self.write("wombat-forbidden-token/kestrel.md", "alpha")
        self.stage_all()

        result = self.gate("--cached")

        self.assertEqual(result.returncode, 1)
        self.assertEqual(hit_lines(result.stdout), ["scrub: (name withheld):0: denylist:2"])
        self.assertNotIn("scrub: clean", result.stdout.splitlines())
        self.assert_output_holds_none_of(result, "wombat", "forbidden", "token", "kestrel")

    def test_git_commit_is_refused_with_the_name_withheld__when_a_staged_name_matches(self):
        """R10.5 · the pre-commit hook refuses a matching name with clean content — otherwise the name lands in history (assumed Q21)."""
        before = self.given_base_commit()
        self.write(MATCHING_NAME, "alpha")
        self.stage_all()

        result = self.git("commit", "-m", "add a plan", check=False)

        self.assertNotEqual(result.returncode, 0)
        self.assertEqual(self.head(), before)
        self.assertIn("scrub: (name withheld):0: denylist:2", lines_of(result))
        self.assert_output_holds_none_of(result, "wombat", "forbidden", "token", "kestrel")

    def test_range_passes__when_a_matching_name_predates_the_range_and_no_commit_touches_it(self):
        """R10.6 · `--range` matches only the paths its commits add or change — refusing an old name would block every push until the tree is cleaned."""
        self.write("readme.txt", "sample project")
        self.write(MATCHING_NAME, "alpha")
        old = self.commit_ungated("a plan from before the range")
        self.write("readme.txt", "sample project", "second line")
        new = self.commit_ungated("edit the readme")

        result = self.gate("--range", old, new)

        self.assertEqual(result.returncode, 0)
        self.assertIn("scrub: clean", result.stdout.splitlines())

    def test_tree_withholds_a_matching_name__when_no_recent_commit_touched_it(self):
        """R10.7 · `--tree` matches every tracked name — the backstop for names that came in before the hooks (assumed Q21)."""
        self.write("readme.txt", "sample project")
        self.write(MATCHING_NAME, "alpha")
        self.commit_ungated("a plan from before the range")
        self.write("readme.txt", "sample project", "second line")
        self.commit_ungated("edit the readme")

        result = self.gate("--tree")

        self.assertEqual(result.returncode, 1)
        self.assertEqual(hit_lines(result.stdout), ["scrub: (name withheld):0: denylist:2"])
        self.assertNotIn("scrub: clean", result.stdout.splitlines())
        self.assert_output_holds_none_of(result, "wombat", "forbidden", "token", "kestrel")

    def test_cached_withholds_the_new_name__when_a_clean_file_is_renamed_to_a_matching_name(self):
        """R10.8 · a `git mv` into a matching name is a hit — a rename is how a clean file picks up a leaking name (assumed Q21)."""
        self.write("draft.txt", "alpha")
        self.commit_ungated("a draft")
        self.git("mv", "draft.txt", MATCHING_NAME)

        result = self.gate("--cached")

        self.assertEqual(result.returncode, 1)
        self.assertEqual(hit_lines(result.stdout), ["scrub: (name withheld):0: denylist:2"])
        self.assert_output_holds_none_of(result, "wombat", "forbidden", "token", "kestrel")

    def test_cached_passes__when_the_only_matching_name_is_staged_for_deletion(self):
        """R10.9 · deleting a matching name is not a hit — otherwise the leak can never be removed."""
        self.write("readme.txt", "sample project")
        self.write(MATCHING_NAME, "alpha")
        self.commit_ungated("a plan committed before the gate")
        self.git("rm", "-q", MATCHING_NAME)

        result = self.gate("--cached")

        self.assertEqual(result.returncode, 0)
        self.assertIn("scrub: clean", result.stdout.splitlines())

    def test_cached_withholds_a_matching_name__when_a_clean_edit_to_that_file_is_staged(self):
        """R10.10 · a staged edit puts a matching name in scope — the commit carries that name forward (assumed Q21)."""
        self.write("readme.txt", "sample project")
        self.write(MATCHING_NAME, "alpha")
        self.commit_ungated("a plan committed before the gate")
        self.write(MATCHING_NAME, "alpha", "bravo")
        self.stage_all()

        result = self.gate("--cached")

        self.assertEqual(result.returncode, 1)
        self.assertEqual(hit_lines(result.stdout), ["scrub: (name withheld):0: denylist:2"])
        self.assertNotIn("scrub: clean", result.stdout.splitlines())
        self.assert_output_holds_none_of(result, "wombat", "forbidden", "token", "kestrel")

    def test_cached_passes__when_a_committed_matching_name_is_not_staged(self):
        """R10.11 · `--cached` matches staged paths only — an unrelated commit must not be refused for a name it does not touch."""
        self.write("readme.txt", "sample project")
        self.write(MATCHING_NAME, "alpha")
        self.commit_ungated("a plan committed before the gate")
        self.write("readme.txt", "sample project", "second line")
        self.stage_all()

        result = self.gate("--cached")

        self.assertEqual(result.returncode, 0)
        self.assertIn("scrub: clean", result.stdout.splitlines())

    def test_range_withholds_a_matching_name__when_a_commit_in_the_range_edits_that_file(self):
        """R10.12 · a pushed commit that changes a matching file puts its name in scope — the push carries that name (assumed Q21)."""
        self.write(MATCHING_NAME, "alpha")
        old = self.commit_ungated("a plan")
        self.write(MATCHING_NAME, "alpha", "bravo")
        new = self.commit_ungated("edit the plan")

        result = self.gate("--range", old, new)

        self.assertEqual(result.returncode, 1)
        self.assertEqual(hit_lines(result.stdout), ["scrub: (name withheld):0: denylist:2"])
        self.assertNotIn("scrub: clean", result.stdout.splitlines())
        self.assert_output_holds_none_of(result, "wombat", "forbidden", "token", "kestrel")

    def test_cached_withholds_a_name__when_a_pattern_matches_across_its_slash(self):
        """R10.13 · `ibis/kestrel` matches the whole path `ibis/kestrel.md` though no component does — per-component matching misses it (assumed Q21)."""
        self.denylist.write_text("# synthetic patterns for the path check\nibis/kestrel\n")
        self.given_base_commit()
        self.write("ibis/kestrel.md", "alpha")
        self.stage_all()

        result = self.gate("--cached")

        self.assertEqual(result.returncode, 1)
        self.assertEqual(hit_lines(result.stdout), ["scrub: (name withheld):0: denylist:2"])
        self.assert_output_holds_none_of(result, "ibis", "kestrel")


# MARK: - R11 · the denylist path is resolved once; missing, unreadable or a directory is exit 2


class R11DenylistResolvedOnce(NameContentCase):

    def given_a_tree_with_a_hit_beside_a_subdirectory(self) -> None:
        self.write("sub/keep.txt", "alpha")
        self.write("notes.txt", "alpha", "forbidden-token here")
        self.commit_ungated("a hit at the root, a subdirectory beside it")

    def test_tree_reports_the_hit__when_a_relative_denylist_is_named_from_a_subdirectory(self):
        """R11.1 · `--tree` from `sub/` reads the relative denylist the caller named — re-reading it after a `cd` printed `scrub: clean` over a hit (F2; assumed Q23)."""
        self.given_a_tree_with_a_hit_beside_a_subdirectory()
        relative = self.given_relative_denylist()

        result = self.gate_from_subdirectory("--tree", denylist=relative)

        self.assertEqual(result.returncode, 1)
        self.assertEqual(hit_lines(result.stdout), ["scrub: notes.txt:2: denylist:2"])

    def test_tree_refuses_with_exit_2_naming_the_path_as_given__when_a_relative_denylist_from_a_subdirectory_is_missing(self):
        """R11.2 · a missing relative denylist is exit 2 naming the path as given, never `scrub: clean` — a typo must not pass the tree."""
        self.given_a_tree_with_a_hit_beside_a_subdirectory()
        missing = f"../../{self.base.name}-absent.denylist"

        result = self.gate_from_subdirectory("--tree", denylist=missing)

        self.assertEqual(result.returncode, 2)
        self.assertIn(missing, result.stdout + result.stderr)
        self.assertNotIn("scrub: clean", result.stdout.splitlines())
        self.assertEqual([line for line in lines_of(result) if HIT_SHAPED.search(line)], [])

    def test_cached_refuses_with_exit_2_naming_it__when_the_denylist_is_a_directory(self):
        """R11.3 · a directory as the denylist is exit 2 naming it, no hit line — exit 1 with no line reads as a hit nobody can find (F5)."""
        directory = self.base / "denylist.d"
        directory.mkdir()
        self.given_base_commit()
        self.write("notes.txt", "forbidden-token here")
        self.stage_all()

        result = self.gate("--cached", env=self.env_naming(directory))

        self.assertEqual(result.returncode, 2)
        self.assertIn(str(directory), result.stdout + result.stderr)
        self.assertEqual([line for line in lines_of(result) if HIT_SHAPED.search(line)], [])
        self.assertNotIn("scrub: clean", result.stdout.splitlines())

    def test_tree_refuses_with_exit_2_naming_it__when_the_denylist_is_a_directory(self):
        """R11.4 · the same refusal under `--tree` — a mode that reads the denylist its own way must refuse the same way (F5)."""
        directory = self.base / "denylist.d"
        directory.mkdir()
        self.given_base_commit()
        self.write("notes.txt", "forbidden-token here")
        self.commit_ungated("a hit")

        result = self.gate("--tree", env=self.env_naming(directory))

        self.assertEqual(result.returncode, 2)
        self.assertIn(str(directory), result.stdout + result.stderr)
        self.assertEqual([line for line in lines_of(result) if HIT_SHAPED.search(line)], [])
        self.assertNotIn("scrub: clean", result.stdout.splitlines())


# MARK: - R12 · `--tree` reads a symlink's link text, never its target


class R12TreeReadsLinkText(NameContentCase):

    def test_tree_reports_line_1_of_a_dangling_link__when_its_link_text_matches(self):
        """R12.1 · a dangling link whose text matches is a hit at line 1 under `--tree`, as under `--cached` — skipping it let the backstop miss what git stores (F3)."""
        self.given_base_commit()
        os.symlink("/nonexistent/forbidden-token/path", self.work / "link-dangling")
        self.commit_ungated("a dangling link")

        result = self.gate("--tree")

        self.assertEqual(result.returncode, 1)
        self.assertEqual(hit_lines(result.stdout), ["scrub: link-dangling:1: denylist:2"])
        self.assert_output_holds_none_of(result, "forbidden", "token")

    def test_tree_passes__when_a_clean_link_points_at_a_matching_file_outside_the_repository(self):
        """R12.2 · a link's target outside the repository is never read — the repository holds only the link text, and a hit there names a file git never stores."""
        outside = self.base / "outside.txt"
        outside.write_text("forbidden-token here\n")
        self.given_base_commit()
        os.symlink(str(outside), self.work / "outside-link")
        self.commit_ungated("a link out of the repository")

        result = self.gate("--tree")

        self.assertEqual(result.returncode, 0)
        self.assertIn("scrub: clean", result.stdout.splitlines())

    def test_tree_reports_only_the_target_s_own_name__when_a_clean_link_points_at_a_matching_tracked_file(self):
        """R12.3 · a link to a tracked hit reports the hit once, under the target's name — following the link reports the same line against a name that does not hold it."""
        self.write("m.txt", "alpha", "forbidden-token here")
        os.symlink("m.txt", self.work / "a-link")
        self.commit_ungated("a link to a tracked hit")

        result = self.gate("--tree")

        self.assertEqual(result.returncode, 1)
        self.assertEqual(hit_lines(result.stdout), ["scrub: m.txt:2: denylist:2"])

    def test_tree_passes__when_a_tracked_file_holding_a_hit_is_absent_from_disk(self):
        """R12.4 · a tracked path deleted from the working copy is skipped — reading links differently must not turn a missing file into a failure."""
        self.given_base_commit()
        self.write("notes.txt", "forbidden-token here")
        self.commit_ungated("a hit")
        (self.work / "notes.txt").unlink()

        result = self.gate("--tree")

        self.assertEqual(result.returncode, 0)
        self.assertIn("scrub: clean", result.stdout.splitlines())


# MARK: - R13 · rules 1–9 unchanged: a deleted path and a commit message are not matched


class R13RulesOneToNineHold(NameContentCase):

    def test_range_passes__when_a_commit_deletes_a_matching_name(self):
        """R13.1 · a pushed commit that deletes a matching name is not a hit — the push that removes the leak must land."""
        self.write("readme.txt", "sample project")
        self.write(MATCHING_NAME, "alpha")
        old = self.commit_ungated("a plan")
        self.git("rm", "-q", MATCHING_NAME)
        new = self.commit_ungated("drop the plan")

        result = self.gate("--range", old, new)

        self.assertEqual(result.returncode, 0)
        self.assertIn("scrub: clean", result.stdout.splitlines())

    def test_range_passes__when_only_a_commit_message_holds_a_pattern(self):
        """R13.2 · a commit message is not matched — the Owner kept messages out of D10's scope."""
        base = self.given_base_commit()
        self.write("notes.txt", "alpha")
        tip = self.commit_ungated("forbidden-token in the message")

        result = self.gate("--range", base, tip)

        self.assertEqual(result.returncode, 0)
        self.assertIn("scrub: clean", result.stdout.splitlines())


# MARK: - U5 hostile shapes (H11–H17), written with the rule rows before the gate changed


class HostileNamesU5(NameContentCase):

    def test_tree_withholds_a_matching_name_holding_a_tab_and_prints_the_names_around_it_as_listed(self):
        r"""H11 · a withheld tab name between `a\nb` and `z.md`: each hit keeps its own file and line — withholding one record must not shift its neighbours (assumed Q21)."""
        self.write("a\\nb", "forbidden-token here")
        self.write("m\twombat-forbidden-token.md", "alpha", "key example-secret-7 end")
        self.write("z.md", "one", "two", "forbidden-token here")
        self.commit_ungated("a withheld name between two listed ones")

        result = self.gate("--tree")

        self.assertEqual(result.returncode, 1)
        self.assertEqual(
            hit_lines(result.stdout),
            [
                "scrub: (name withheld):0: denylist:2",
                "scrub: (name withheld):2: denylist:3",
                "scrub: a\\nb:1: denylist:2",
                "scrub: z.md:3: denylist:2",
            ],
        )
        self.assert_output_holds_none_of(result, "wombat", "forbidden", "token", "example", "secret")

    def test_cached_withholds_a_name__when_it_matches_only_regardless_of_case(self):
        """H12 · `Wombat-FORBIDDEN-Token-Kestrel.md` matches `forbidden-token` — names are matched under rule 2, case-insensitively (assumed Q21)."""
        self.given_base_commit()
        self.write("Wombat-FORBIDDEN-Token-Kestrel.md", "alpha")
        self.stage_all()

        result = self.gate("--cached")

        self.assertEqual(result.returncode, 1)
        self.assertEqual(hit_lines(result.stdout), ["scrub: (name withheld):0: denylist:2"])
        self.assert_output_holds_none_of(result, "wombat", "forbidden", "token", "kestrel")

    def test_cached_passes__when_a_matching_name_is_renamed_to_a_clean_one(self):
        """H13 · renaming a matching name away is not a hit — the fix for a leaking name must commit."""
        self.write(MATCHING_NAME, "alpha")
        self.commit_ungated("a plan committed before the gate")
        self.git("mv", MATCHING_NAME, "plain.txt")

        result = self.gate("--cached")

        self.assertEqual(result.returncode, 0)
        self.assertIn("scrub: clean", result.stdout.splitlines())

    def test_cached_prints_one_withheld_line_per_pattern__when_two_patterns_match_one_name(self):
        """H14 · a name matching lines 2 and 3 prints `:0: denylist:2` and `:0: denylist:3` — the Owner needs every line to find the name (assumed Q21)."""
        self.given_base_commit()
        self.write("wombat-forbidden-token-example-secret-42.md", "alpha")
        self.stage_all()

        result = self.gate("--cached")

        self.assertEqual(result.returncode, 1)
        self.assertEqual(
            hit_lines(result.stdout),
            ["scrub: (name withheld):0: denylist:2", "scrub: (name withheld):0: denylist:3"],
        )
        self.assert_output_holds_none_of(result, "wombat", "forbidden", "token", "example", "secret")

    def test_tree_refuses_with_exit_2_and_prints_no_part_of_the_name__when_a_matching_name_holds_a_newline(self):
        """H15 · a matching newline name still takes rule 9's refusal: exit 2, the count 3, no hit line, no word of the name (assumed Q20, Q21)."""
        self.write("wombat-forbidden-token\nkestrel.md", "alpha")
        self.write("two\nname.txt", "alpha")
        self.write("three\nname.txt", "bravo")
        self.write("notes.txt", "forbidden-token here")
        self.commit_ungated("names with newlines, one matching")

        result = self.gate("--tree")

        self.assertEqual(result.returncode, 2)
        self.assertRegex(result.stderr, r"(?m)^scrub: .*\b3\b")
        self.assertEqual([line for line in lines_of(result) if HIT_SHAPED.search(line)], [])
        self.assert_output_holds_none_of(result, "wombat", "forbidden", "token", "kestrel")

    def test_git_push_is_refused_with_the_name_withheld__when_a_pushed_commit_adds_a_matching_name(self):
        """H16 · the pre-push hook refuses a matching name and withholds it — a name that slipped past pre-commit must not reach the remote (assumed Q21)."""
        self.given_base_commit()
        self.write(MATCHING_NAME, "alpha")
        self.commit_ungated("add a plan")

        result = self.git("push", "origin", "main", check=False)

        self.assertNotEqual(result.returncode, 0)
        self.assertIsNone(self.remote_ref("main"))
        self.assertIn("scrub: (name withheld):0: denylist:2", lines_of(result))
        self.assert_output_holds_none_of(result, "wombat", "forbidden", "token", "kestrel")

    @unittest.skipIf(os.geteuid() == 0, "root reads a file whatever its mode")
    def test_tree_refuses_with_exit_2_naming_it__when_the_denylist_is_unreadable(self):
        """H17 · an unreadable denylist is exit 2 naming it, never `scrub: clean` — a denylist that cannot be read has checked nothing."""
        unreadable = self.base / "unreadable-denylist"
        unreadable.write_text(SCRATCH_DENYLIST)
        unreadable.chmod(0)
        self.addCleanup(unreadable.chmod, 0o600)
        self.write("notes.txt", "forbidden-token here")
        self.commit_ungated("a hit")

        result = self.gate("--tree", env=self.env_naming(unreadable))

        self.assertEqual(result.returncode, 2)
        self.assertIn(str(unreadable), result.stdout + result.stderr)
        self.assertEqual([line for line in lines_of(result) if HIT_SHAPED.search(line)], [])
        self.assertNotIn("scrub: clean", result.stdout.splitlines())

    @unittest.skipIf(os.geteuid() == 0, "root reads a file whatever its mode")
    def test_tree_refuses_with_exit_2_and_prints_no_part_of_the_name__when_a_matching_name_is_unreadable(self):
        """H18 · a tracked file `--tree` cannot read is still a name no output may carry (U5 gate F1; assumed Q21)."""
        self.write("readme.txt", "sample project")
        self.write(MATCHING_NAME, "alpha")
        self.commit_ungated("a plan")
        (self.work / MATCHING_NAME).chmod(0)
        self.addCleanup((self.work / MATCHING_NAME).chmod, 0o600)

        result = self.gate("--tree")

        self.assertEqual(result.returncode, 2)
        self.assertNotIn("scrub: clean", result.stdout.splitlines())
        self.assert_output_holds_none_of(result, "wombat", "forbidden", "token", "kestrel")

    @unittest.skipIf(os.geteuid() == 0, "root searches a directory whatever its mode")
    def test_tree_refuses_with_exit_2__when_a_tracked_file_sits_in_a_directory_it_cannot_search(self):
        """H21 · a tracked file under an unsearchable directory is unread, not absent — never `scrub: clean` (end-of-stack F1; assumed Q30)."""
        self.write("sealed/notes.txt", "forbidden-token here")
        self.commit_ungated("a hit")
        (self.work / "sealed").chmod(0)
        self.addCleanup((self.work / "sealed").chmod, 0o700)

        result = self.gate("--tree")

        self.assertEqual(result.returncode, 2)
        self.assertNotIn("scrub: clean", result.stdout.splitlines())

    def given_git_warning_naming_a_matching_directory(self) -> None:
        """A `.gitattributes` under a matching directory that git warns about on every diff, naming its own path."""
        self.write("wombat-forbidden-token/kestrel.md", "alpha")
        self.write("wombat-forbidden-token/.gitattributes", "[attr]bin -diff")

    def test_cached_prints_no_part_of_a_withheld_name__when_git_warns_about_a_file_under_it(self):
        """H19 · a tool the gate runs may name a withheld path on stderr; none of it reaches the gate's output (U5 gate F1, attempt 2; assumed Q21)."""
        self.given_base_commit()
        self.given_git_warning_naming_a_matching_directory()
        self.stage_all()

        result = self.gate("--cached")

        self.assertEqual(result.returncode, 1)
        self.assertIn("scrub: (name withheld):0: denylist:2", hit_lines(result.stdout))
        self.assert_output_holds_none_of(result, "wombat", "forbidden", "token", "kestrel")

    def test_range_prints_no_part_of_a_withheld_name__when_git_warns_about_a_file_under_it(self):
        """H20 · as H19, at pre-push — the push gate must not publish what the commit gate hides (assumed Q21)."""
        base = self.given_base_commit()
        self.given_git_warning_naming_a_matching_directory()
        tip = self.commit_ungated("add a plan")

        result = self.gate("--range", base, tip)

        self.assertEqual(result.returncode, 1)
        self.assertIn("scrub: (name withheld):0: denylist:2", hit_lines(result.stdout))
        self.assert_output_holds_none_of(result, "wombat", "forbidden", "token", "kestrel")


# MARK: - U5 · from the end-of-stack review (F1, F2, F3, F5)


class EndOfStackFindings(NameContentCase):

    def test_tree_withholds_a_file_under_a_matching_directory_in_both_hit_lines(self):
        """G15 · F1 · a hit inside a matching directory prints as `(name withheld):2`, never the path — the directory leaked as part of the name (assumed Q21)."""
        self.given_base_commit()
        self.write("wombat-forbidden-token/kestrel.md", "intro", "key example-secret-7 end")
        self.commit_ungated("a hit under a matching directory")

        result = self.gate("--tree")

        self.assertEqual(result.returncode, 1)
        self.assertEqual(
            hit_lines(result.stdout),
            ["scrub: (name withheld):0: denylist:2", "scrub: (name withheld):2: denylist:3"],
        )
        self.assert_output_holds_none_of(result, "wombat", "forbidden", "token", "kestrel", "example", "secret")

    def test_range_reports_the_hit__when_a_relative_denylist_is_named_from_a_subdirectory(self):
        """G16 · F2 · `--range` from `sub/` reads the relative denylist the caller named — resolving it once must hold in every mode, not only `--tree`."""
        base = self.given_base_commit()
        self.write("sub/keep.txt", "alpha")
        self.write("notes.txt", "alpha", "forbidden-token here")
        tip = self.commit_ungated("a hit at the root, a subdirectory beside it")
        relative = self.given_relative_denylist()

        result = self.gate_from_subdirectory("--range", base, tip, denylist=relative)

        self.assertEqual(result.returncode, 1)
        self.assertEqual(hit_lines(result.stdout), ["scrub: notes.txt:2: denylist:2"])

    def test_range_refuses_with_exit_2_naming_it__when_the_denylist_is_a_directory(self):
        """G17 · F5 · a directory as the denylist is exit 2 at pre-push too — exit 1 with no line reads as a hit nobody can find."""
        directory = self.base / "denylist.d"
        directory.mkdir()
        base = self.given_base_commit()
        self.write("notes.txt", "forbidden-token here")
        tip = self.commit_ungated("a hit")

        result = self.gate("--range", base, tip, env=self.env_naming(directory))

        self.assertEqual(result.returncode, 2)
        self.assertIn(str(directory), result.stdout + result.stderr)
        self.assertEqual([line for line in lines_of(result) if HIT_SHAPED.search(line)], [])
        self.assertNotIn("scrub: clean", result.stdout.splitlines())

    def test_cached_reports_line_1_of_a_dangling_link__when_its_link_text_matches(self):
        """G18 · F3 · a staged dangling link whose text matches stays a hit at line 1 — the `--tree` fix must leave `--cached` as it was."""
        self.given_base_commit()
        os.symlink("/nonexistent/forbidden-token/path", self.work / "link-dangling")
        self.stage_all()

        result = self.gate("--cached")

        self.assertEqual(result.returncode, 1)
        self.assertEqual(hit_lines(result.stdout), ["scrub: link-dangling:1: denylist:2"])
        self.assert_output_holds_none_of(result, "forbidden", "token")



# MARK: - R14 · every refusal says why (tracer-polish P1), written before the gate changed


class R14EveryRefusalSaysWhy(NameContentCase):
    """One row per refusal site that exited 2 with no line before P1, and the bash error that exited 1.

    `assert_output_holds_none_of` lowercases the output before it looks, so a path is passed
    lowercased: a path holding a capital letter would otherwise never be found, leaked or not.
    """

    def test_refuses_with_exit_2_and_only_the_scratch_directory_line__when_tmpdir_does_not_exist(self):
        """R14.1 · no scratch directory is `scrub: could not create a scratch directory` and exit 2 — a gate that exits 2 with no line leaves the builder nothing to go on."""
        self.given_base_commit()
        missing_tmpdir = self.base / "no-such-tmpdir"
        env = dict(self.env, TMPDIR=str(missing_tmpdir))

        result = self.gate("--tree", env=env)

        self.assertEqual(result.returncode, 2)
        self.assertEqual(result.stdout, "")
        self.assertEqual(result.stderr.splitlines(), ["scrub: could not create a scratch directory"])
        self.assert_output_holds_none_of(
            result,
            "forbidden", "token", "example", "secret",
            str(self.base).lower(), str(self.work).lower(), str(missing_tmpdir).lower(),
        )

    def test_range_refuses_with_exit_2_and_only_the_commit_list_line__when_new_names_no_commit(self):
        """R14.2 · a `<new>` that names no commit is `scrub: could not list the commits to check` and exit 2 — the push is blocked with no reason given."""
        base = self.given_base_commit()

        result = self.gate("--range", base, "nonexistent")

        self.assertEqual(result.returncode, 2)
        self.assertEqual(result.stdout, "")
        self.assertEqual(result.stderr.splitlines(), ["scrub: could not list the commits to check"])
        self.assert_output_holds_none_of(
            result,
            "forbidden", "token", "example", "secret",
            str(self.base).lower(), str(self.work).lower(),
        )

    def test_tree_refuses_with_exit_2_and_only_the_tracked_files_line__when_run_outside_any_repository(self):
        """R14.3 · `--tree` with no repository to list is `scrub: could not list the tracked files` and exit 2 — the release check stops with no reason given."""
        outside = self.base / "outside"
        outside.mkdir()
        env = dict(self.env, GIT_CEILING_DIRECTORIES=str(self.base.parent))
        self.assertNotEqual(
            self.run_cmd(["git", "rev-parse", "--git-dir"], cwd=outside, env=env, check=False).returncode,
            0,
            "the Given must be outside every repository",
        )

        result = self.run_cmd([str(self.work / "tools" / "scrub-gate.sh"), "--tree"], cwd=outside, env=env, check=False)

        self.assertEqual(result.returncode, 2)
        self.assertEqual(result.stdout, "")
        self.assertEqual(result.stderr.splitlines(), ["scrub: could not list the tracked files"])
        self.assert_output_holds_none_of(
            result,
            "forbidden", "token", "example", "secret",
            str(self.base).lower(), str(self.work).lower(),
        )

    def test_tree_refuses_with_exit_2_and_only_the_top_level_line__when_the_work_tree_does_not_exist(self):
        """R14.4 · a top level the gate cannot enter is `scrub: could not enter the top level of the repository` and exit 2, never its path — the reason line must not carry what `git rev-parse` printed."""
        self.given_base_commit()
        missing_work_tree = self.base / "no-such-work-tree"
        env = dict(self.env, GIT_WORK_TREE=str(missing_work_tree))

        result = self.gate("--tree", env=env)

        self.assertEqual(result.returncode, 2)
        self.assertEqual(result.stdout, "")
        self.assertEqual(result.stderr.splitlines(), ["scrub: could not enter the top level of the repository"])
        self.assert_output_holds_none_of(
            result,
            "forbidden", "token", "example", "secret",
            str(self.base).lower(), str(self.work).lower(), str(missing_work_tree).lower(),
        )

    def test_tree_refuses_with_exit_2_and_only_the_internal_error_line__when_a_bash_error_stops_the_gate(self):
        """R14.5 · an unbound `$HOME` under `set -u` is `scrub: stopped on an internal error` and exit 2 — before P1 it exits 1 with no line, which reads as a hit nobody can find."""
        self.given_base_commit()
        env = dict(self.env)
        del env["HOME"]
        del env["ROBOWRIGHT_DENYLIST"]

        result = self.gate("--tree", env=env)

        self.assertEqual(result.returncode, 2)
        self.assertEqual(result.stdout, "")
        self.assertEqual(result.stderr.splitlines(), ["scrub: stopped on an internal error"])
        self.assert_output_holds_none_of(
            result,
            "forbidden", "token", "example", "secret",
            str(self.base).lower(), str(self.work).lower(),
        )

    def test_tree_leaves_no_scratch_directory_behind__when_the_run_is_clean(self):
        """H23 · held out: the gate's scratch directory is removed when the run ends."""
        self.given_base_commit()
        tmpdir = self.base / "tmp"
        tmpdir.mkdir()

        result = self.gate("--tree", env=dict(self.env, TMPDIR=str(tmpdir)))

        self.assertEqual((result.returncode, result.stdout.splitlines()), (0, ["scrub: clean"]))
        self.assertEqual(list(tmpdir.iterdir()), [])

    def test_refusal_leaves_a_directory_named_by_an_inherited_work_variable__when_it_exits_before_its_scratch_directory(self):
        """H24 · a `work` in the caller's environment is not the gate's scratch directory: a refusal before `mktemp` removes nothing (P1 gate F1)."""
        victim = self.base / "victim"
        victim.mkdir()
        (victim / "keep.txt").write_text("alpha\n")
        env = dict(self.env, work=str(victim), ROBOWRIGHT_DENYLIST=str(self.base / "no-such-denylist"))

        result = self.gate("--tree", env=env)

        self.assertEqual(result.returncode, 2)
        self.assertTrue((victim / "keep.txt").is_file())

    def test_bash_error_refuses_with_the_internal_error_line__when_the_caller_exports_verdict_hit(self):
        """H25 · a `verdict` in the caller's environment does not turn R14.5's bash error into a silent exit 1 (P1 gate F2)."""
        self.given_base_commit()
        env = dict(self.env, verdict="hit")
        del env["HOME"]
        del env["ROBOWRIGHT_DENYLIST"]

        result = self.gate("--tree", env=env)

        self.assertEqual(result.returncode, 2)
        self.assertEqual(result.stdout, "")
        self.assertEqual(result.stderr.splitlines(), ["scrub: stopped on an internal error"])
        self.assert_output_holds_none_of(
            result,
            "forbidden", "token", "example", "secret",
            str(self.base).lower(), str(self.work).lower(),
        )


# MARK: - Polish P2 · the pre-push fallback and the ancestor that is now a file


class P2FallbackAndAncestor(ScratchRepoCase):

    def given_remote_advanced_by_another_clone(self) -> str:
        """Pushes a clean base, then a clean commit from a second clone the pusher never fetches; returns that commit."""
        self.given_base_commit()
        self.push_ungated("origin", "main")
        other = self.base / "other"
        self.run_cmd(["git", "clone", "-q", "-b", "main", str(self.remote), str(other)], cwd=self.base)
        self.run_cmd(["git", "config", "user.name", "Other Owner"], cwd=other)
        self.run_cmd(["git", "config", "user.email", "other@example.com"], cwd=other)
        (other / "theirs.txt").write_text("charlie\n")
        self.run_cmd(["git", "add", "-A"], cwd=other)
        self.run_cmd(["git", "commit", "-q", "--no-verify", "-m", "their commit"], cwd=other)
        self.run_cmd(["git", "push", "-q", "--no-verify", "origin", "main"], cwd=other)
        remote_tip = self.remote_ref("main")
        self.assertNotEqual(
            self.git("cat-file", "-e", f"{remote_tip}^{{commit}}", check=False).returncode,
            0,
            "the Given must leave the remote's tip out of the pusher's object store",
        )
        return remote_tip

    def test_force_push_is_refused__when_the_remote_moved_past_the_last_fetch_and_the_unpushed_commit_adds_a_hit(self):
        """R4.11 · a remote oid the pusher does not have falls back to every commit on no remote, so the unpushed hit is read — `^<old>` on a missing object would refuse with no hit line."""
        remote_tip = self.given_remote_advanced_by_another_clone()
        self.write("notes.txt", "alpha", "forbidden-token here")
        tip = self.commit_ungated("add a hit")

        result = self.git("push", "--force", "origin", "main", check=False)

        self.assertNotEqual(result.returncode, 0)
        self.assertEqual(self.remote_ref("main"), remote_tip)
        self.assertIn("scrub: notes.txt:2: denylist:2", lines_of(result))
        self.assertEqual(self.gate("--range", remote_tip, tip).returncode, 1)

    def test_force_push_lands__when_the_remote_moved_past_the_last_fetch_and_the_unpushed_commit_is_clean(self):
        """R4.12 · the same fallback on a clean commit lets the push through, as R6.5 does with a local remote oid — the fallback scans, it does not refuse."""
        self.given_remote_advanced_by_another_clone()
        self.write("other.txt", "bravo")
        tip = self.commit_ungated("clean commit")

        result = self.git("push", "--force", "origin", "main", check=False)

        self.assertEqual(result.returncode, 0, "\n".join(lines_of(result)))
        self.assertEqual(self.remote_ref("main"), tip)

    def test_tree_passes__when_a_tracked_file_s_directory_is_now_a_regular_file(self):
        """R12.5 · a tracked path whose directory was replaced on disk by a regular file is absent, and skipped — a file cannot hold the path, so nothing is unread."""
        self.given_base_commit()
        self.write("a/notes.txt", "forbidden-token here")
        self.commit_ungated("a hit under a directory")
        shutil.rmtree(self.work / "a")
        (self.work / "a").write_text("alpha\n")

        result = self.gate("--tree")

        self.assertEqual(result.returncode, 0)
        self.assertEqual(result.stdout.splitlines(), ["scrub: clean"])


if __name__ == "__main__":
    unittest.main()
