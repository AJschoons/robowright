#!/usr/bin/env python3
"""Tests for the conventions lint, written from BEHAVIORS.md before the lint existed.

Every fixture is syntax only: the names it uses are never defined and nothing here runs it."""
import os, shutil, subprocess, sys, tempfile, unittest
from pathlib import Path

LINT = Path(__file__).resolve().parent / "lint.py"
REPO = Path(__file__).resolve().parents[2]

TOOL_PY = "skills/sample/scripts/tool.py"
TOOL_SH = "skills/sample/scripts/tool.sh"
HOOK_SH = "skills/sample/hooks/gate.sh"
ACCEPT_SH = "skills/lead/scripts/accept.sh"
LAUNCHER = "skills/robowright/scripts/run-launch.sh"
RUN_COST = "skills/worker/scripts/run-cost.py"
DASH = "tools/robowright-dash.py"

ARITHMETIC = 'next=$((count + 1))\nlet next=count+1\n(( count > 5 ))\n[[ $count -gt 5 ]]\n'
DASH_HELPER = "def e(value):\n    return html.escape(str(value))\n"


class Lint(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name) / "tree"
        self.allowlist = Path(self.tmp.name) / "allowlist.txt"
        self.allowlist.write_text("")

    def tearDown(self):
        self.tmp.cleanup()

    def given(self, files: dict):
        for rel, text in files.items():
            path = self.root / rel
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(text)

    def given_allowlist(self, *entries):
        self.allowlist.write_text("# check\tpath\treason\tsource line\n" + "".join(f"{entry}\n" for entry in entries))

    def lint(self):
        return subprocess.run([sys.executable, str(LINT), f"--root={self.root}", f"--allowlist={self.allowlist}"],
                              capture_output=True, text=True)

    def assertFinding(self, done, check, path, line):
        self.assertIn(f"conventions: {check} {path}:{line}: ", done.stdout, done.stdout + done.stderr)
        self.assertEqual(done.returncode, 1, done.stdout + done.stderr)

    def assertNoFinding(self, done, check):
        self.assertNotIn(f"conventions: {check} ", done.stdout, done.stdout + done.stderr)

    def assertClean(self, done):
        self.assertEqual((done.returncode, done.stdout), (0, "conventions: clean\n"), done.stdout + done.stderr)

    def test_C1_shell_true_is_a_finding(self):
        self.given({TOOL_PY: "subprocess.run(command, shell=True)\n"})
        self.assertFinding(self.lint(), "shell-true", TOOL_PY, 1)

    def test_C2_os_system_and_os_popen_are_findings(self):
        self.given({TOOL_PY: "os.system(command)\nos.popen(command)\n"})
        done = self.lint()
        self.assertFinding(done, "os-system", TOOL_PY, 1)
        self.assertFinding(done, "os-system", TOOL_PY, 2)

    def test_C3_eval_is_a_finding_in_python_and_in_shell(self):
        self.given({TOOL_PY: "value = eval(text)\n", HOOK_SH: '#!/bin/bash\neval "$line"\n'})
        done = self.lint()
        self.assertFinding(done, "eval", TOOL_PY, 1)
        self.assertFinding(done, "eval", HOOK_SH, 2)

    def test_C4_sh_c_with_a_variable_command_string_is_a_finding(self):
        self.given({TOOL_PY: 'subprocess.run(["bash", "-c", command])\n', HOOK_SH: '#!/bin/bash\nbash -c "$command"\n'})
        done = self.lint()
        self.assertFinding(done, "sh-c", TOOL_PY, 1)
        self.assertFinding(done, "sh-c", HOOK_SH, 2)

    def test_C4a_a_constant_script_with_positional_data_is_not(self):
        self.given({TOOL_PY: 'subprocess.run(["bash", "-c", \'printf "%s" "$1"\', "probe", value])\n',
                    HOOK_SH: '#!/bin/bash\nbash -c \'printf "%s\\n" "$1"\' probe "$value"\n'})
        self.assertClean(self.lint())

    def test_C5_json_built_by_printf_echo_or_a_double_quoted_jq_filter_is_a_finding(self):
        self.given({TOOL_SH: "#!/usr/bin/env bash\n"
                             "printf '{\"model\": \"%s\"}\\n' \"$model\"\n"
                             'echo "{\\"model\\": \\"$model\\"}"\n'
                             'jq -n "{model: \\"$model\\"}"\n'})
        done = self.lint()
        for line in (2, 3, 4):
            self.assertFinding(done, "json-shell", TOOL_SH, line)

    def test_C5a_jq_arg_is_not(self):
        self.given({TOOL_SH: "#!/usr/bin/env bash\njq -cn --arg model \"$model\" '{model: $model}'\n"})
        self.assertClean(self.lint())

    def test_C6_arithmetic_on_a_variable_in_a_hook_is_a_finding(self):
        self.given({HOOK_SH: "#!/bin/bash\n" + ARITHMETIC})
        done = self.lint()
        for line in (2, 3, 4, 5):
            self.assertFinding(done, "hook-arithmetic", HOOK_SH, line)

    def test_C6a_the_same_arithmetic_outside_a_hook_is_not(self):
        self.given({TOOL_SH: "#!/usr/bin/env bash\n" + ARITHMETIC})
        self.assertClean(self.lint())

    def test_C7_raw_git_in_an_owner_side_tool_is_a_finding(self):
        self.given({ACCEPT_SH: '#!/usr/bin/env bash\nstatus=$(git -C "$worktree" status --porcelain)\n',
                    RUN_COST: 'subprocess.run(["git", "-C", worktree, "diff"])\n'})
        done = self.lint()
        self.assertFinding(done, "raw-git", ACCEPT_SH, 2)
        self.assertFinding(done, "raw-git", RUN_COST, 1)

    def test_C7a_git_through_owner_git_or_outside_the_owner_side_tools_is_not(self):
        self.given({ACCEPT_SH: '#!/usr/bin/env bash\nstatus=$("${GIT[@]}" -C "$worktree" status --porcelain)\n',
                    TOOL_SH: '#!/usr/bin/env bash\ngit -C "$dir" status\n'})
        self.assertClean(self.lint())

    def test_C9_a_bare_redirect_to_a_file_in_a_hook_or_the_launcher_is_a_finding(self):
        self.given({HOOK_SH: '#!/bin/bash\nprintf "%s\\n" "$line" >> "$run_dir/LEDGER.md"\n'
                             'jq -r . "$f" >/dev/null 2>&1\necho "$why" >&2\n',
                    LAUNCHER: '#!/usr/bin/env bash\nprintf "%s\\n" "$dir" > "$MARKER"\n',
                    TOOL_SH: '#!/usr/bin/env bash\nprintf x > "$out"\n'})
        done = self.lint()
        self.assertFinding(done, "session-write", HOOK_SH, 2)
        self.assertFinding(done, "session-write", LAUNCHER, 2)
        self.assertEqual(done.stdout.count("conventions: session-write "), 2, done.stdout)

    def test_C8_unescaped_html_interpolation_in_the_dashboard_is_a_finding(self):
        self.given({DASH: DASH_HELPER
                    + "def row(name):\n    return f'<div>{name}</div>'\n"
                    + "def bold(name):\n    return '<b>%s</b>' % name\n"
                    + "def strong(name):\n    return '<b>{}</b>'.format(name)\n"})
        done = self.lint()
        for line in (4, 6, 8):
            self.assertFinding(done, "dash-unescaped", DASH, line)

    def test_C8a_escaped_numeric_and_constant_interpolations_are_not(self):
        self.given({DASH: DASH_HELPER
                    + "def row(name, items, big):\n"
                    + "    return (f'<div>{e(name)}</div>' + f'<span>{len(items)}</span>'\n"
                    + "            + f'<i class=\"{\"big\" if big else \"\"}\"></i>')\n"})
        self.assertClean(self.lint())

    def test_C2b_os_system_imported_by_name_and_subprocess_getoutput_are_findings(self):
        self.given({TOOL_PY: "from os import system\nsubprocess.getoutput(command)\n"})
        done = self.lint()
        self.assertFinding(done, "os-system", TOOL_PY, 1)
        self.assertFinding(done, "os-system", TOOL_PY, 2)

    def test_C4b_sh_c_behind_other_options_or_env_is_a_finding(self):
        self.given({TOOL_PY: 'subprocess.run(["bash", "-lc", command])\nsubprocess.run(["/usr/bin/env", "bash", "-c", command])\n',
                    HOOK_SH: '#!/bin/bash\nbash -lc "$command"\nsh -ec "$command"\nbash --norc -c "$command"\n'})
        done = self.lint()
        for line in (1, 2):
            self.assertFinding(done, "sh-c", TOOL_PY, line)
        for line in (2, 3, 4):
            self.assertFinding(done, "sh-c", HOOK_SH, line)

    def test_C5b_json_built_in_an_assignment_is_a_finding(self):
        self.given({TOOL_SH: '#!/usr/bin/env bash\npayload="{\\"model\\": \\"$model\\"}"\n'})
        self.assertFinding(self.lint(), "json-shell", TOOL_SH, 2)

    def test_C6b_arithmetic_with_no_space_before_it_is_a_finding(self):
        self.given({HOOK_SH: "#!/bin/bash\nif((count>5)); then :; fi\n"})
        self.assertFinding(self.lint(), "hook-arithmetic", HOOK_SH, 2)

    def test_C7b_raw_git_after_a_condition_keyword_or_through_a_constant_is_a_finding(self):
        self.given({ACCEPT_SH: '#!/usr/bin/env bash\nif git -C "$worktree" diff --quiet; then :; fi\n'
                             'while git -C "$worktree" diff --quiet; do :; done\n'
                             'until git -C "$worktree" diff --quiet; do :; done\n',
                    RUN_COST: 'GIT = "/usr/bin/git"\nsubprocess.run([GIT, "-C", worktree, "diff"])\n'
                              'subprocess.run(["/usr/bin/git", "-C", worktree, "diff"])\n'})
        done = self.lint()
        for line in (2, 3, 4):
            self.assertFinding(done, "raw-git", ACCEPT_SH, line)
        for line in (2, 3):
            self.assertFinding(done, "raw-git", RUN_COST, line)

    def test_C8b_html_reached_through_a_local_a_template_constant_or_a_helper_parameter_is_a_finding(self):
        self.given({DASH: DASH_HELPER
                    + "ROW = '<td>%s</td>'\n"
                    + "CELL = '<td>{}</td>'\n"
                    + "def tag(cls):\n    return f'<i class=\"{cls}\"></i>'\n"
                    + "def row(name, names, session):\n"
                    + "    text = '%s' % name\n"
                    + "    return (f'<div>{text}</div>'\n"
                    + "            + ROW % name\n"
                    + "            + CELL.format(name)\n"
                    + "            + f'<b>{max(names)}</b>'\n"
                    + "            + tag(session['tone']))\n"})
        done = self.lint()
        for line in (9, 10, 11, 12, 13):
            self.assertFinding(done, "dash-unescaped", DASH, line)
        self.assertNotIn(f"{DASH}:6:", done.stdout)

    def test_C8c_a_helper_parameter_given_constants_is_not(self):
        self.given({DASH: DASH_HELPER
                    + "def tag(cls):\n    return f'<i class=\"{cls}\"></i>'\n"
                    + "def row(big):\n    return tag('idle') + tag('big' if big else 'small')\n"})
        self.assertClean(self.lint())

    def test_C5c_json_spliced_into_a_quoted_word_is_a_finding(self):
        self.given({TOOL_SH: "#!/usr/bin/env bash\n"
                             "payload='{\"model\": \"'\"$model\"'\"}'\n"
                             'body="$(printf %s "{\\"model\\": \\"$model\\"}")"\n'})
        done = self.lint()
        for line in (2, 3):
            self.assertFinding(done, "json-shell", TOOL_SH, line)

    def test_C5d_a_quoted_key_in_a_jq_filter_is_not_even_inside_a_command_substitution(self):
        self.given({TOOL_SH: "#!/usr/bin/env bash\n"
                             "jq -n --arg model \"$model\" '{\"model\":$model}'\n"
                             "settings=\"$(jq -cn --arg m \"$m\" '{\"model\": $m}')\"\n"})
        self.assertClean(self.lint())

    def test_C7c_raw_git_behind_an_environment_assignment_or_in_backticks_is_a_finding(self):
        self.given({ACCEPT_SH: '#!/usr/bin/env bash\nLC_ALL=C git -C "$worktree" status\nhead=`git -C "$worktree" rev-parse HEAD`\n'})
        done = self.lint()
        for line in (2, 3):
            self.assertFinding(done, "raw-git", ACCEPT_SH, line)

    def test_C7d_raw_git_after_command_or_exec_or_in_a_case_arm_is_a_finding(self):
        self.given({ACCEPT_SH: '#!/usr/bin/env bash\ncommand git -C "$worktree" status\nexec git -C "$worktree" status\n'
                             'case "$1" in a) git -C "$worktree" status ;; esac\n'})
        done = self.lint()
        for line in (2, 3, 4):
            self.assertFinding(done, "raw-git", ACCEPT_SH, line)

    def test_C7e_the_word_git_in_a_string_or_a_comment_is_not(self):
        self.given({ACCEPT_SH: '#!/usr/bin/env bash\necho "run git status in the worktree"\n'
                             'printf \'%s\\n\' "git -C $dir"  # git here is text\n'})
        self.assertClean(self.lint())

    def test_C7f_a_quote_the_reader_could_lose_does_not_hide_the_lines_after_it(self):
        self.given({ACCEPT_SH: "#!/usr/bin/env bash\n"
                             "cat <<EOF\n"
                             "The Owner's call; it doesn't run anything.\n"
                             "EOF\n"
                             'die "$(printf "no worktree \\"%s\\"" "$w")"\n'
                             'git -C "$worktree" status\n'
                             'echo "`git -C "$worktree" status`"\n'
                             'status=$(command -p \\\n'
                             'git -C "$worktree" status)\n'})
        done = self.lint()
        for line in (6, 7, 9):
            self.assertFinding(done, "raw-git", ACCEPT_SH, line)

    def test_C7g_an_apostrophe_in_a_heredoc_body_does_not_hide_the_lines_after_it(self):
        self.given({ACCEPT_SH: "#!/usr/bin/env bash\n"
                             "cat <<EOF\n"
                             "Run it from the Owner's terminal.\n"
                             "EOF\n"
                             'git -C "$worktree" status\n'})
        self.assertFinding(self.lint(), "raw-git", ACCEPT_SH, 5)

    def test_C7h_a_heredoc_inside_a_substitution_does_not_hide_the_lines_after_it(self):
        self.given({ACCEPT_SH: "#!/usr/bin/env bash\n"
                             '"${GIT[@]}" commit -m "$(cat <<\'EOF\'\n'
                             "accept: the Owner's change\n"
                             "EOF\n"
                             ')"\n'
                             'git -C "$worktree" status\n'})
        self.assertFinding(self.lint(), "raw-git", ACCEPT_SH, 6)

    def test_C7i_a_substitution_in_an_expanding_heredoc_body_is_read_and_in_a_quoted_one_is_not(self):
        self.given({ACCEPT_SH: "#!/usr/bin/env bash\n"
                             "cat <<EOF\n"
                             "Accepted $slug at $(git rev-parse --short HEAD).\n"
                             "EOF\n"
                             "cat <<'EOF'\n"
                             "Run $(git status) to see it.\n"
                             "EOF\n"})
        done = self.lint()
        self.assertFinding(done, "raw-git", ACCEPT_SH, 3)
        self.assertNotIn(f"{ACCEPT_SH}:6:", done.stdout)

    def test_C7j_backticks_in_an_expanding_heredoc_body_are_read_and_an_escaped_substitution_is_not(self):
        self.given({ACCEPT_SH: "#!/usr/bin/env bash\n"
                             "cat <<EOF\n"
                             "Accepted at `git rev-parse HEAD`.\n"
                             "Run \\$(git status) yourself.\n"
                             "EOF\n"})
        done = self.lint()
        self.assertFinding(done, "raw-git", ACCEPT_SH, 3)
        self.assertNotIn(f"{ACCEPT_SH}:4:", done.stdout)

    def test_C7k_parentheses_nested_in_a_quoted_substitution_do_not_end_it(self):
        self.given({ACCEPT_SH: "#!/usr/bin/env bash\n"
                             'delta="$(diff <(sort "$a") <(git show "$base:$f" | sort))"\n'
                             'added="$(comm -13 <(sort "$old") <(sort "$new") | tr -d \'"\')"\n'
                             'next="$(seq 1 $((k + 1)); git -C "$worktree" status)"\n'
                             'git -C "$worktree" status\n'})
        done = self.lint()
        for line in (2, 4, 5):
            self.assertFinding(done, "raw-git", ACCEPT_SH, line)

    def test_C5e_json_in_an_expanding_heredoc_body_is_a_finding_and_in_a_quoted_one_is_not(self):
        self.given({TOOL_SH: "#!/usr/bin/env bash\n"
                             "cat <<EOF\n"
                             '{"model": "$model"}\n'
                             "EOF\n"
                             "cat <<'EOF'\n"
                             '{"model": "$model"}\n'
                             "EOF\n"})
        done = self.lint()
        self.assertFinding(done, "json-shell", TOOL_SH, 3)
        self.assertNotIn(f"{TOOL_SH}:6:", done.stdout)

    def test_C8d_format_keywords_star_parameters_and_nested_helpers_are_checked(self):
        self.given({DASH: DASH_HELPER
                    + "def parts(*items):\n    return f'<p>{items[0]}</p>'\n"
                    + "def attrs(**named):\n    return f'<p>{named}</p>'\n"
                    + "def row(name, session):\n"
                    + "    label = '{n}'.format(n=name)\n"
                    + "    def inner(cls):\n        return f'<i class=\"{cls}\"></i>'\n"
                    + "    return (f'<b>{label}</b>'\n"
                    + "            + parts(session['tone'])\n"
                    + "            + attrs(tone=session['tone'])\n"
                    + "            + inner(name))\n"})
        done = self.lint()
        for line in (10, 11, 12, 13):
            self.assertFinding(done, "dash-unescaped", DASH, line)

    def test_A1_an_allowlist_entry_with_a_reason_clears_its_site(self):
        self.given({TOOL_PY: "subprocess.run(command, shell=True)\n"})
        self.given_allowlist(f"shell-true\t{TOOL_PY}\tthe command is a constant\tsubprocess.run(command, shell=True)")
        self.assertClean(self.lint())

    def test_A2_an_allowlist_entry_without_a_reason_is_refused(self):
        self.given({TOOL_PY: "subprocess.run(command, shell=True)\n"})
        self.given_allowlist(f"shell-true\t{TOOL_PY}\t \tsubprocess.run(command, shell=True)")
        done = self.lint()
        self.assertEqual(done.returncode, 2, done.stdout + done.stderr)
        self.assertIn("allowlist line 2", done.stderr)
        self.assertIn("reason", done.stderr)

    def test_A3_an_entry_that_matches_no_site_is_a_finding(self):
        self.given({TOOL_PY: "print(1)\n"})
        self.given_allowlist(f"shell-true\t{TOOL_PY}\tthe command is a constant\tsubprocess.run(command, shell=True)")
        done = self.lint()
        self.assertIn(f"conventions: stale allowlist line 2: shell-true {TOOL_PY}", done.stdout, done.stdout)
        self.assertEqual(done.returncode, 1)

    def test_A4_one_entry_clears_one_site_of_identical_lines(self):
        self.given({TOOL_PY: "subprocess.run(command, shell=True)\nsubprocess.run(command, shell=True)\n"})
        self.given_allowlist(f"shell-true\t{TOOL_PY}\tthe command is a constant\tsubprocess.run(command, shell=True)")
        self.assertFinding(self.lint(), "shell-true", TOOL_PY, 2)

    def test_A5_a_second_identical_entry_with_one_site_left_is_stale(self):
        self.given({TOOL_PY: "subprocess.run(command, shell=True)\n"})
        entry = f"shell-true\t{TOOL_PY}\tthe command is a constant\tsubprocess.run(command, shell=True)"
        self.given_allowlist(entry, entry)
        done = self.lint()
        self.assertIn(f"conventions: stale allowlist line 3: shell-true {TOOL_PY}", done.stdout, done.stdout)
        self.assertEqual(done.returncode, 1)

    def test_T1_the_tree_is_clean_with_the_shipped_allowlist(self):
        self.assertClean(subprocess.run([sys.executable, str(LINT)], cwd=REPO, capture_output=True, text=True))


class PreCommit(unittest.TestCase):
    """The pre-commit hook in a scratch repository: the real tools/hooks and scrub gate, the real lint, an empty
    allowlist, an invented denylist pattern, a scratch HOME."""

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        base = Path(self.tmp.name).resolve()
        self.work, home, denylist = base / "work", base / "home", base / "denylist"
        home.mkdir()
        denylist.write_text("# invented pattern\nsample-forbidden-word\n")
        self.env = {k: v for k, v in os.environ.items() if not k.startswith("GIT_")}
        self.env.update(HOME=str(home), XDG_CONFIG_HOME=str(home / ".config"), GIT_CONFIG_NOSYSTEM="1",
                        ROBOWRIGHT_DENYLIST=str(denylist))
        (self.work / "tools").mkdir(parents=True)
        shutil.copytree(REPO / "tools" / "hooks", self.work / "tools" / "hooks")
        shutil.copy2(REPO / "tools" / "scrub-gate.sh", self.work / "tools" / "scrub-gate.sh")
        (self.work / "tests" / "conventions").mkdir(parents=True)
        shutil.copy2(LINT, self.work / "tests" / "conventions" / "lint.py")
        (self.work / "tests" / "conventions" / "allowlist.txt").write_text("# check\tpath\treason\tsource line\n")
        (self.work / "readme.txt").write_text("sample project\n")
        for args in (["init", "-q", "-b", "main"], ["config", "user.name", "Sample Owner"],
                     ["config", "user.email", "owner@example.com"], ["config", "core.hooksPath", "tools/hooks"],
                     ["add", "-A"], ["commit", "-q", "--no-verify", "-m", "base"]):
            self.git(*args)
        self.base = self.head()

    def tearDown(self):
        self.tmp.cleanup()

    def git(self, *args):
        return subprocess.run(["git", *args], cwd=self.work, env=self.env, capture_output=True, text=True,
                              stdin=subprocess.DEVNULL, timeout=60)

    def head(self):
        return self.git("rev-parse", "HEAD").stdout.strip()

    def write(self, rel, text):
        path = self.work / rel
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text)

    def commit(self):
        return self.git("commit", "-m", "change")

    def assertRefusedBy(self, done, *gates):
        self.assertNotEqual(done.returncode, 0, done.stdout + done.stderr)
        self.assertEqual(self.head(), self.base)
        for gate in gates:
            self.assertIn(f"pre-commit: refused by {gate}", done.stdout + done.stderr, done.stdout + done.stderr)

    def test_H1_a_staged_lint_finding_blocks_the_commit_and_names_the_lint(self):
        self.write(TOOL_PY, "subprocess.run(command, shell=True)\n")
        self.git("add", "-A")
        done = self.commit()
        self.assertRefusedBy(done, "the conventions lint")
        self.assertIn(f"conventions: shell-true {TOOL_PY}:1: ", done.stdout + done.stderr)

    def test_H2_a_clean_commit_lands(self):
        self.write(TOOL_PY, "print(1)\n")
        self.git("add", "-A")
        done = self.commit()
        self.assertEqual(done.returncode, 0, done.stdout + done.stderr)
        self.assertNotEqual(self.head(), self.base)

    def test_H3_the_lint_judges_the_index_not_the_working_tree(self):
        self.write(TOOL_PY, "subprocess.run(command, shell=True)\n")
        self.git("add", "-A")
        self.write(TOOL_PY, "print(1)\n")
        self.assertRefusedBy(self.commit(), "the conventions lint")
        self.git("add", "-A")
        self.write(TOOL_PY, "subprocess.run(command, shell=True)\n")
        done = self.commit()
        self.assertEqual(done.returncode, 0, done.stdout + done.stderr)

    def test_H4_both_gates_run_and_each_failure_is_named(self):
        self.write(TOOL_PY, "subprocess.run(command, shell=True)\n")
        self.write("notes.txt", "sample-forbidden-word\n")
        self.git("add", "-A")
        self.assertRefusedBy(self.commit(), "the scrub gate", "the conventions lint")

    def test_H5_a_scrub_hit_alone_blocks_the_commit_and_names_only_the_scrub_gate(self):
        self.write("notes.txt", "sample-forbidden-word\n")
        self.git("add", "-A")
        done = self.commit()
        self.assertRefusedBy(done, "the scrub gate")
        self.assertNotIn("refused by the conventions lint", done.stdout + done.stderr)

    def test_H6_the_allowlist_is_read_from_the_index_too(self):
        self.write(TOOL_PY, "subprocess.run(command, shell=True)\n")
        self.write("tests/conventions/allowlist.txt", "# check\tpath\treason\tsource line\n"
                   f"shell-true\t{TOOL_PY}\tthe command is a constant\tsubprocess.run(command, shell=True)\n")
        self.git("add", "-A")
        self.write("tests/conventions/allowlist.txt", "# check\tpath\treason\tsource line\n")
        done = self.commit()
        self.assertEqual(done.returncode, 0, done.stdout + done.stderr)

    def test_H7_a_staged_finding_on_a_skip_worktree_entry_is_still_judged(self):
        self.write(TOOL_PY, "subprocess.run(command, shell=True)\n")
        self.git("add", "-A")
        self.git("update-index", "--skip-worktree", TOOL_PY)
        self.assertRefusedBy(self.commit(), "the conventions lint")


if __name__ == "__main__":
    unittest.main()
