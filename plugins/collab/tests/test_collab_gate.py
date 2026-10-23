"""Unit tests for the deterministic part of the plugin: scripts/collab_gate.py.

Run: python3 -m unittest discover -s plugins/collab/tests -v
"""
import io
import json
import subprocess
import sys
import tempfile
import unittest
from contextlib import redirect_stdout
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))
import collab_gate as g  # noqa: E402

CONFIG = g.load_config()


class GateTestCase(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        root = Path(self._tmp.name)
        self.project = root / "project"
        self.project.mkdir()
        self.env = g.Env(data_dir=root / "data", project_dir=self.project, config=CONFIG)

    def tearDown(self):
        self._tmp.cleanup()

    def pre(self, state, tool, **tool_input):
        return g.decide_pre_tool_use({"tool_name": tool, "tool_input": tool_input}, state, self.env)

    def command(self, state, name, args=""):
        return g.decide_command({"command_name": name, "command_args": args}, state, self.env)

    @staticmethod
    def decision(out):
        return (out or {}).get("hookSpecificOutput", {}).get("permissionDecision")


class BashWriteDetection(unittest.TestCase):
    WRITES = [
        "echo hi > src/app.py",
        "cat >> notes.txt",
        "printf x &> out.log",
        "cat > src/a.py <<'EOF'\nprint(1)\nEOF",
        "sed -i '' 's/a/b/' file.py",
        "sed -ni 's/a/b/p' file.py",
        "perl -pi -e 's/a/b/' f",
        "rm -rf build",
        "mkdir -p src/new",
        "ls && mv a.py b.py",
        "find . -name '*.pyc' -delete",
        "git commit -m 'x'",
        "git -C repo checkout main",
        "npm install lodash",
        "FOO=1 sudo tee /etc/x",
        "ls | xargs rm",
        "python3 -c \"open('a.py', 'w').write('x')\"",
        "node -e \"require('fs').writeFileSync('a.js', '')\"",
        "python3 - <<'EOF'\nfrom pathlib import Path\nPath('a').write_text('x')\nEOF",
    ]
    READS = [
        "ls -la",
        "cat src/app.py",
        "grep -rn 'a > b' src",
        "echo \"x -> y\"",
        "git status && git diff HEAD~1",
        "git log --oneline -5",
        "pytest -q 2>&1 | tail -20",
        "npm test 2>/dev/null",
        "find . -iname '*.py'",
        "sed -n '1,20p' file.py",
        "python3 -m pytest tests",
        "python3 - <<'EOF'\nprint(1 > 0)\nEOF",
        "jq '.a > 1' data.json",
    ]

    def test_detects_writes(self):
        for cmd in self.WRITES:
            with self.subTest(cmd=cmd):
                self.assertIsNotNone(g.bash_write_reason(cmd, CONFIG))

    def test_ignores_reads(self):
        for cmd in self.READS:
            with self.subTest(cmd=cmd):
                self.assertIsNone(g.bash_write_reason(cmd, CONFIG))


class PreToolUseGate(GateTestCase):
    def test_discussing_denies_writes_inside_project(self):
        state = g.SessionState()
        self.assertEqual(self.decision(self.pre(state, "Write", file_path=str(self.project / "a.py"))), "deny")
        self.assertEqual(self.decision(self.pre(state, "Edit", file_path=str(self.project / "a.py"))), "deny")
        self.assertEqual(self.decision(self.pre(state, "NotebookEdit", notebook_path=str(self.project / "n.ipynb"))), "deny")
        self.assertEqual(self.decision(self.pre(state, "Bash", command="rm a.py")), "deny")

    def test_discussing_allows_reads_and_writes_outside_project(self):
        state = g.SessionState()
        self.assertIsNone(self.pre(state, "Bash", command="git diff"))
        self.assertIsNone(self.pre(state, "Write", file_path="/tmp/scratch/notes.md"))

    def test_open_stages_allow_writes(self):
        for stage in ("agreed", "skipped", "off"):
            with self.subTest(stage=stage):
                state = g.SessionState(stage=stage)
                self.assertIsNone(self.pre(state, "Write", file_path=str(self.project / "a.py")))
                self.assertIsNone(self.pre(state, "Bash", command="rm a.py"))

    def test_plugin_state_is_protected_in_every_stage(self):
        target = self.env.data_dir / "sessions" / "s.json"
        for stage in ("discussing", "agreed", "skipped", "off"):
            with self.subTest(stage=stage):
                state = g.SessionState(stage=stage)
                self.assertEqual(self.decision(self.pre(state, "Write", file_path=str(target))), "deny")
                self.assertEqual(self.decision(self.pre(state, "Bash", command=f"cat {target}")), "deny")

    def test_deny_reason_explains_how_to_unlock(self):
        out = self.pre(g.SessionState(), "Write", file_path=str(self.project / "a.py"))
        self.assertIn("/collab:agree", out["hookSpecificOutput"]["permissionDecisionReason"])


class Commands(GateTestCase):
    AGREEMENT = "offset pagination through limit and offset because the table is small"

    def test_agree_requires_own_words(self):
        state = g.SessionState()
        out, journal = self.command(state, "collab:agree", "ok")
        self.assertEqual(out["decision"], "block")
        self.assertEqual(state.stage, "discussing")
        self.assertEqual(journal, [])

    def test_agree_opens_unit(self):
        state = g.SessionState(changed_files=["old.py"])
        out, journal = self.command(state, "collab:agree", self.AGREEMENT)
        self.assertNotIn("decision", out)
        self.assertEqual(state.stage, "agreed")
        self.assertEqual(state.agreement, self.AGREEMENT)
        self.assertEqual(state.changed_files, [])
        self.assertIn(self.AGREEMENT, out["hookSpecificOutput"]["additionalContext"])
        self.assertEqual(journal, [("agree", self.AGREEMENT)])

    def test_agree_while_off_is_refused(self):
        state = g.SessionState(stage="off")
        out, _ = self.command(state, "collab:agree", self.AGREEMENT)
        self.assertEqual(out["decision"], "block")
        self.assertEqual(state.stage, "off")

    def test_skip_and_off_need_no_reason(self):
        for name, stage in (("collab:skip", "skipped"), ("collab:off", "off")):
            with self.subTest(name=name):
                state = g.SessionState()
                out, journal = self.command(state, name, "  ")
                self.assertNotIn("decision", out)
                self.assertEqual((state.stage, journal), (stage, [(name.split(":")[1], "")]))
        state = g.SessionState()
        self.command(state, "collab:skip")
        self.assertNotIn('""', g.status_line(state))
        self.command(state, "collab:skip", "trivial rename")
        self.assertIn('"trivial rename"', g.status_line(state))

    def test_explain_keeps_writes_blocked(self):
        state = g.SessionState()
        out, journal = self.command(state, "collab:explain", "rate limiting")
        self.assertNotIn("decision", out)
        self.assertIn("stage=discussing", out["hookSpecificOutput"]["additionalContext"])
        self.assertEqual(state.stage, "discussing")
        self.assertEqual(journal, [("explain", "rate limiting")])
        out, _ = self.command(g.SessionState(stage="off"), "collab:explain")
        self.assertEqual(out["decision"], "block")

    def test_off_then_on(self):
        state = g.SessionState()
        self.command(state, "collab:off", "urgent hotfix")
        self.assertEqual(state.stage, "off")
        self.command(state, "collab:on")
        self.assertEqual(state.stage, "discussing")

    def test_done_closes_unit(self):
        state = g.SessionState(stage="agreed", agreement="x", changed_files=["a.py"])
        self.command(state, "collab:done")
        self.assertEqual((state.stage, state.changed_files, state.units_closed), ("discussing", [], 1))

    def test_mode_switch_injects_mode_rules(self):
        state = g.SessionState()
        out, _ = self.command(state, "collab:mode", "learning")
        self.assertEqual(state.mode, "learning")
        self.assertIn("Mode: Learning", out["hookSpecificOutput"]["additionalContext"])
        out, _ = self.command(state, "collab:mode", "turbo")
        self.assertEqual(out["decision"], "block")
        self.assertEqual(state.mode, "learning")

    def test_foreign_commands_are_ignored(self):
        state = g.SessionState()
        for name in ("other:agree", "agree", "review"):
            with self.subTest(name=name):
                self.assertEqual(self.command(state, name, self.AGREEMENT), (None, []))
        self.assertEqual(state.stage, "discussing")


class StopCheck(GateTestCase):
    REVIEW = ("## Final review\n### 1. What was implemented\nPagination.\n### 3. Explanation by file\n"
              "#### `a.py`\nAdded paginate().\n### 7. Verification\nTests were not run.")

    def stop(self, state, message, active=False, transcript=None):
        event = {"last_assistant_message": message, "stop_hook_active": active}
        if transcript is not None:
            event["transcript_path"] = str(transcript)
        return g.decide_stop(event, state, self.env)

    def test_no_check_outside_open_unit(self):
        self.assertIsNone(self.stop(g.SessionState(), "done"))
        self.assertIsNone(self.stop(g.SessionState(stage="off", changed_files=["a"]), "done"))

    def test_open_unit_without_changes_may_stop(self):
        self.assertIsNone(self.stop(g.SessionState(stage="agreed"), "Starting with the data model."))

    def test_changes_without_review_are_blocked(self):
        out = self.stop(g.SessionState(stage="agreed", changed_files=["a.py"]), "Done, all finished.")
        self.assertEqual(out["decision"], "block")
        self.assertIn("Final review", out["reason"])

    def test_question_to_developer_is_a_valid_pause(self):
        msg = "Added the model.\n\nNext there are two options for error handling. Which one do you pick and why?"
        self.assertIsNone(self.stop(g.SessionState(stage="agreed", changed_files=["a.py"]), msg))

    def test_retry_is_never_blocked_twice(self):
        self.assertIsNone(self.stop(g.SessionState(stage="agreed", changed_files=["a.py"]), "Done.", active=True))

    def test_review_without_verification_is_blocked(self):
        state = g.SessionState(stage="agreed", changed_files=["a.py"])
        out = self.stop(state, "## Final review\nPagination is done.")
        self.assertEqual(out["decision"], "block")
        self.assertIn("Verification", out["reason"])
        self.assertEqual(state.stage, "agreed")

    def test_complete_review_closes_unit(self):
        state = g.SessionState(stage="skipped", changed_files=["a.py"])
        out = self.stop(state, self.REVIEW)
        self.assertNotIn("decision", out)
        self.assertEqual((state.stage, state.units_closed), ("discussing", 1))

    def test_russian_and_ukrainian_headings(self):
        for review in ("## Итоговый разбор\n### Объяснение по файлам\n#### a.py\n-\n### Проверка\n-",
                       "## Итоговый обзор\n### Объяснение по файлам\n#### a.py\n-\n### Проверка\n-",
                       "## Підсумковий розбір\n### Пояснення по файлах\n#### a.py\n-\n### Перевірка\n-"):
            with self.subTest(review=review):
                state = g.SessionState(stage="agreed", changed_files=["a.py"])
                self.stop(state, review)
                self.assertEqual(state.stage, "discussing")


class ExplanationByFile(GateTestCase):
    """Stop: every changed file is explained along the way or under "Explanation by file" in the review."""

    REVIEW = "## Final review\nDone.\n### Verification\nTests were not run."
    EXPLAIN_A = "In a.py I moved the email check into is_valid(): it returns a bool instead of raising. " * 3

    def setUp(self):
        super().setUp()
        self.a, self.b = str(self.project / "a.py"), str(self.project / "pkg" / "b.py")
        self.transcript = Path(self._tmp.name) / "transcript.jsonl"
        self.state = g.SessionState(stage="agreed", changed_files=[self.a, self.b],
                                    change_anchors={self.a: "edit_a", self.b: "edit_b"})

    def write_transcript(self, *responses):
        """Each response is a list of blocks: a string is text, ("tool", id) is a tool call."""
        with open(self.transcript, "w", encoding="utf-8") as f:
            for blocks in responses:
                content = [{"type": "tool_use", "id": b[1], "name": "Edit", "input": {}} if isinstance(b, tuple)
                           else {"type": "text", "text": b} for b in blocks]
                f.write(json.dumps({"type": "assistant", "message": {"content": content}}) + "\n")

    def stop(self, message, active=False):
        event = {"last_assistant_message": message, "stop_hook_active": active,
                 "transcript_path": str(self.transcript)}
        return g.decide_stop(event, self.state, self.env)

    def test_files_explained_along_the_way_need_no_section(self):
        self.write_transcript([("tool", "read")], [("tool", "edit_a")], [self.EXPLAIN_A, ("tool", "edit_b")],
                              ["Now b.py: " + "x" * 200, ("tool", "pytest")], [self.REVIEW])
        self.assertNotIn("decision", self.stop(self.REVIEW))
        self.assertEqual(self.state.stage, "discussing")

    def test_unexplained_files_are_listed(self):
        self.write_transcript([("tool", "edit_a")], [self.EXPLAIN_A, ("tool", "edit_b")], [("tool", "pytest")])
        out = self.stop(self.REVIEW)
        self.assertEqual(out["decision"], "block")
        self.assertIn("pkg/b.py", out["reason"])
        self.assertNotIn("a.py,", out["reason"])
        self.assertIn("#### <file>", out["reason"])
        self.assertEqual(self.state.stage, "agreed")

    def test_explanation_right_before_the_change_counts(self):
        self.write_transcript([("tool", "read")], [self.EXPLAIN_A, ("tool", "edit_a")],
                              ["About b.py: " + "x" * 200, ("tool", "edit_b")])
        self.assertNotIn("decision", self.stop(self.REVIEW))

    def test_short_or_earlier_mentions_do_not_count(self):
        self.write_transcript([self.EXPLAIN_A, ("tool", "read")], [("tool", "edit_a")],
                              ["Updated b.py.", ("tool", "edit_b")])
        out = self.stop(self.REVIEW)
        self.assertIn("a.py, pkg/b.py", out["reason"])

    def test_final_review_does_not_count_as_explanation(self):
        review = self.REVIEW.replace("Done.", "Files: a.py and pkg/b.py were changed. " + "x" * 200)
        self.write_transcript([("tool", "edit_a"), ("tool", "edit_b")], [review])
        self.assertEqual(self.stop(review)["decision"], "block")

    def test_section_with_a_heading_per_file_closes_unit(self):
        review = self.REVIEW.replace("Done.", "### Explanation by file\n#### a.py\nx\n#### `pkg/b.py` (new)\ny")
        self.assertNotIn("decision", self.stop(review))  # no transcript needed
        self.assertEqual(self.state.stage, "discussing")

    def test_unreadable_transcript_requires_every_file(self):
        out = self.stop(self.REVIEW)  # transcript file was never written
        self.assertIn("a.py, pkg/b.py", out["reason"])

    def test_one_block_carries_every_problem_and_retry_closes(self):
        out = self.stop("## Final review\nDone.")
        self.assertIn("Verification", out["reason"])
        self.assertIn("pkg/b.py", out["reason"])
        self.assertNotIn("decision", self.stop("## Final review\nDone.", active=True))
        self.assertEqual(self.state.stage, "discussing")


class PlanMode(GateTestCase):
    """/collab:plan: agreement + stages as tasks, with a hard pause for the developer after the plan and each stage."""

    PLAN = "split validation into validators.py, then switch api.py and cli.py, step by step"

    def setUp(self):
        super().setUp()
        self.a = str(self.project / "a.py")
        self.state = g.SessionState()

    def tool(self, phase, tool, call_id="", **tool_input):
        event = {"tool_name": tool, "tool_input": tool_input, "tool_use_id": call_id, "cwd": str(self.project)}
        handler = g.decide_pre_tool_use if phase == "pre" else g.decide_post_tool_use
        return handler(event, self.state, self.env)

    def prompt(self, text):
        return g.decide_user_prompt({"prompt": text}, self.state, self.env)

    def start_stage(self):
        self.command(self.state, "collab:plan", self.PLAN)
        self.prompt("looks good, go")
        self.assertIsNone(self.tool("pre", "TaskUpdate", taskId="1", status="in_progress"))

    def test_plan_needs_own_words_and_starts_paused(self):
        out, _ = self.command(self.state, "collab:plan", "do it")
        self.assertEqual(out["decision"], "block")
        out, journal = self.command(self.state, "collab:plan", self.PLAN)
        self.assertEqual((self.state.stage, self.state.planned, self.state.paused), ("agreed", True, True))
        self.assertIn("TaskCreate", out["hookSpecificOutput"]["additionalContext"])
        self.assertEqual(journal, [("plan", self.PLAN)])

    def test_pause_blocks_changes_and_stage_updates_but_not_planning_or_reading(self):
        self.command(self.state, "collab:plan", self.PLAN)
        self.assertEqual(self.decision(self.tool("pre", "Edit", file_path=self.a)), "deny")
        self.assertEqual(self.decision(self.tool("pre", "Bash", command="rm old.py")), "deny")
        self.assertEqual(self.decision(self.tool("pre", "TaskUpdate", taskId="1", status="in_progress")), "deny")
        self.assertIsNone(self.tool("pre", "TaskUpdate", taskId="1", subject="Rename"))
        self.assertIsNone(self.tool("pre", "Bash", command="pytest -q"))
        self.assertIsNone(self.tool("pre", "Write", file_path="/tmp/notes.md"))

    def test_any_reply_lifts_the_pause_but_collab_commands_do_not(self):
        self.command(self.state, "collab:plan", self.PLAN)
        self.assertIsNone(self.prompt("/collab:status"))
        self.assertTrue(self.state.paused)
        out = self.prompt("rename the function in stage 1 first")
        self.assertFalse(self.state.paused)
        self.assertIn("feedback", out["hookSpecificOutput"]["additionalContext"])
        self.assertIsNone(self.tool("pre", "Edit", file_path=self.a))

    def test_completed_stage_pauses_and_lists_its_files(self):
        self.start_stage()
        self.tool("post", "Edit", "e1", file_path=self.a)
        out = self.tool("post", "TaskUpdate", taskId="1", status="completed")
        self.assertTrue(self.state.paused)
        self.assertIn("a.py", out["reason"])
        self.assertIn("Do not start the next stage", out["reason"])
        self.assertEqual(self.decision(self.tool("pre", "Edit", file_path=self.a)), "deny")

    def test_pause_stop_requires_the_stage_files_explained(self):
        self.start_stage()
        self.tool("post", "Edit", "e1", file_path=self.a)
        self.tool("post", "TaskUpdate", taskId="1", status="completed")
        stop = lambda msg, active=False: g.decide_stop(
            {"last_assistant_message": msg, "stop_hook_active": active}, self.state, self.env)
        out = stop("Stage 1 is done. Continue?")
        self.assertEqual(out["decision"], "block")
        self.assertIn("a.py", out["reason"])
        self.assertIsNone(stop("Stage 1 is done. Continue?", active=True))
        self.assertIsNone(stop("In a.py I added is_valid(), which " + "x" * 200 + "\n\nContinue with stage 2?"))
        self.assertEqual(self.state.stage, "agreed")  # a pause, not the end of the unit

    def test_next_stage_tracks_only_its_own_files(self):
        self.start_stage()
        self.tool("post", "Edit", "e1", file_path=self.a)
        self.tool("post", "TaskUpdate", taskId="1", status="completed")
        self.prompt("go on")
        self.assertEqual(self.state.stage_anchors, {})
        self.tool("post", "Edit", "e2", file_path=self.a)
        self.assertEqual(self.state.stage_anchors, {self.a: "e2"})
        self.assertEqual(self.state.change_anchors, {self.a: "e1"})

    def test_final_review_on_the_last_stage_closes_the_unit(self):
        self.start_stage()
        self.tool("post", "Edit", "e1", file_path=self.a)
        self.tool("post", "TaskUpdate", taskId="1", status="completed")
        review = "## Final review\n### Explanation by file\n#### a.py\nx\n### Verification\nTests were not run."
        g.decide_stop({"last_assistant_message": review}, self.state, self.env)
        self.assertEqual((self.state.stage, self.state.planned, self.state.paused), ("discussing", False, False))

    def test_tasks_outside_a_plan_do_not_pause(self):
        self.command(self.state, "collab:agree", self.PLAN)
        self.assertIsNone(self.tool("post", "TaskUpdate", taskId="1", status="completed"))
        self.assertFalse(self.state.paused)


class GitGate(GateTestCase):
    """Commits, pushes and history-changing git calls need a one-off /collab:commit|push|git from the developer."""

    def run_git(self, state, command, tool="Bash"):
        event = {"tool_name": tool, "tool_input": {"command": command}, "cwd": str(self.project)}
        pre = g.decide_pre_tool_use(event, state, self.env)
        if self.decision(pre) == "deny":
            return pre
        g.decide_post_tool_use(event, state, self.env)
        return None

    def assertDenied(self, state, command, tool="Bash"):
        out = self.run_git(state, command, tool)
        self.assertEqual(self.decision(out), "deny", command)
        return out["hookSpecificOutput"]["permissionDecisionReason"]

    def test_gated_git_is_denied_without_permission_in_every_stage_but_off(self):
        for stage in ("discussing", "agreed", "skipped"):
            for cmd in ("git commit -m x", "git push", "git -C repo merge dev", "git rebase main",
                        "git reset --hard HEAD~1", "git tag v1", "sudo git cherry-pick abc"):
                with self.subTest(stage=stage, cmd=cmd):
                    reason = self.assertDenied(g.SessionState(stage=stage), cmd)
                    self.assertIn("/collab:commit", reason)
        self.assertDenied(g.SessionState(stage="agreed"), "git commit -m x", tool="PowerShell")
        self.assertIsNone(self.run_git(g.SessionState(stage="off"), "git commit -m x && git push --force"))

    def test_reading_git_needs_no_permission(self):
        for cmd in ("git status", "git log --oneline -5", "git diff HEAD", "git tag", "git tag -l 'v*'", "git add a.py"):
            with self.subTest(cmd=cmd):
                self.assertIsNone(self.run_git(g.SessionState(stage="agreed"), cmd))

    def test_commit_permission_after_the_review_allows_staging_and_one_commit(self):
        state = g.SessionState()  # the review closed the unit: discussing
        self.command(state, "collab:commit", "after review")
        self.assertDenied(state, "git commit --amend -m x")
        self.assertDenied(state, "git add a.py && git commit -m x && git push")
        self.assertDenied(state, "rm a.py && git commit -m x")  # the discussing gate still sees rm
        self.assertIsNone(self.run_git(state, "git add a.py b.py && git commit -m 'Add x'"))
        self.assertEqual(state.git_grant, {})
        self.assertDenied(state, "git commit -m again")

    def test_push_goes_to_the_current_branch_by_default(self):
        state = g.SessionState(stage="agreed")
        self.command(state, "collab:push")
        for cmd in ("git push origin main", "git push --force", "git push origin +HEAD", "git push origin :old"):
            with self.subTest(cmd=cmd):
                self.assertDenied(state, cmd)
        self.assertIsNone(self.run_git(state, "git push -u origin HEAD"))
        self.command(state, "collab:push")
        self.assertIsNone(self.run_git(state, "git push"))

    def test_push_to_a_named_branch(self):
        state = g.SessionState(stage="agreed")
        self.command(state, "collab:push", "feature-x")
        self.assertDenied(state, "git push origin main")
        self.assertDenied(state, "git push")
        self.assertIsNone(self.run_git(state, "git push origin HEAD:feature-x"))

    def test_collab_git_allows_one_call_of_that_action_with_any_flags(self):
        state = g.SessionState(stage="agreed")
        self.command(state, "collab:git", "git commit --amend fix the message typo")
        self.assertDenied(state, "git rebase main")
        self.assertIsNone(self.run_git(state, "git commit --amend -m 'Fixed'"))
        self.command(state, "collab:git", "push --force origin feature")
        self.assertIsNone(self.run_git(state, "git push --force origin feature"))

    def test_collab_git_rejects_ungated_or_missing_actions_and_off(self):
        for args in ("status", ""):
            out, _ = self.command(g.SessionState(stage="agreed"), "collab:git", args)
            self.assertEqual(out["decision"], "block")
        out, _ = self.command(g.SessionState(stage="off"), "collab:commit")
        self.assertEqual(out["decision"], "block")

    def test_unused_permission_expires_on_the_next_message(self):
        state = g.SessionState(stage="agreed")
        self.command(state, "collab:commit")
        g.decide_user_prompt({"prompt": "/collab:status"}, state, self.env)
        self.assertTrue(state.git_grant)
        g.decide_user_prompt({"prompt": "actually, wait"}, state, self.env)
        self.assertDenied(state, "git commit -m x")


class ReportedCases(GateTestCase):
    """Cases from a real session report (0.2.0, Ukrainian, multi-step test fixing): the unit closed early and
    silently, a Ukrainian summary heading wasn't recognized, a "yes" in chat didn't open writes and only
    Claude was told which command was needed."""

    AGREEMENT = "fix the three failing tests in test_api.py and set up the CI workflow for them"
    REVIEW_UK = "## Final review\nВиправлено три тести.\n### Explanation by file\n#### a.py\nx\n### Verification\nТести пройшли."

    def stop(self, state, message, active=False):
        return g.decide_stop({"last_assistant_message": message, "stop_hook_active": active}, state, self.env)

    def agreed(self):
        state = g.SessionState()
        self.command(state, "collab:agree", self.AGREEMENT)
        g.decide_post_tool_use({"tool_name": "Edit", "tool_input": {"file_path": str(self.project / "a.py")},
                                "tool_use_id": "e1"}, state, self.env)
        return state

    # 1. closed early and silently
    def test_mid_work_stop_is_told_to_check_the_agreement_before_a_review(self):
        out = self.stop(self.agreed(), "Fixed two of the tests.")
        self.assertEqual(out["decision"], "block")
        self.assertIn("point by point", out["reason"])
        self.assertIn("continue", out["reason"])

    def test_closing_is_visible_to_the_developer_and_can_be_undone(self):
        state = self.agreed()
        out = self.stop(state, self.REVIEW_UK)
        self.assertEqual(state.stage, "discussing")
        self.assertIn(self.AGREEMENT, out["systemMessage"])
        self.assertIn("/collab:resume", out["systemMessage"])
        out, journal = self.command(state, "collab:resume")
        self.assertEqual((state.stage, state.agreement), ("agreed", self.AGREEMENT))
        self.assertIn("not done yet", out["hookSpecificOutput"]["additionalContext"])
        self.assertEqual(journal, [("resume", self.AGREEMENT)])
        self.assertIsNone(self.pre(state, "Edit", file_path=str(self.project / "b.py")))  # the agreed next step runs

    def test_block_right_after_a_close_points_the_developer_to_resume(self):
        state = self.agreed()
        self.stop(state, self.REVIEW_UK)
        hint = self.pre(state, "Edit", file_path=str(self.project / "b.py"))["systemMessage"]
        self.assertIn("/collab:resume", hint)
        self.assertIn(self.AGREEMENT, hint)
        self.assertNotIn("/collab:resume", self.pre(g.SessionState(), "Edit", file_path=str(self.project / "b.py"))["systemMessage"])

    def test_resume_after_done_and_its_refusals(self):
        state = self.agreed()
        self.command(state, "collab:done")
        self.command(state, "collab:resume")
        self.assertEqual(state.stage, "agreed")
        out, _ = self.command(state, "collab:resume")  # already open
        self.assertEqual(out["decision"], "block")
        out, _ = self.command(g.SessionState(), "collab:resume")  # nothing was closed
        self.assertEqual(out["decision"], "block")
        out, _ = self.command(g.SessionState(stage="off"), "collab:resume")
        self.assertEqual(out["decision"], "block")

    def test_skipped_unit_resumes_as_skipped(self):
        state = g.SessionState()
        self.command(state, "collab:skip")
        state.close_unit()
        self.command(state, "collab:resume")
        self.assertEqual((state.stage, state.agreement), ("skipped", ""))

    # 2. heading language
    def test_review_headings_in_any_conversation_language(self):
        for heading in ("## Final review", "## Итоговый разбор", "## Итоговый обзор", "## Підсумковий розбір"):
            with self.subTest(heading=heading):
                state = self.agreed()
                self.stop(state, self.REVIEW_UK.replace("## Final review", heading))
                self.assertEqual(state.stage, "discussing")

    def test_a_loose_summary_heading_does_not_close_and_the_literal_heading_is_named(self):
        state = self.agreed()
        out = self.stop(state, "## Підсумок\nЗроблено.")  # what Claude wrote in the reported session
        self.assertEqual(state.stage, "agreed")
        self.assertIn('literally as "## Final review"', out["reason"])
        self.assertNotIn("Итоговый", out["reason"])  # the 0.2.0 message pushed a Russian heading

    # 3. agreement needs the developer's command, and the developer is told so
    def test_a_yes_in_chat_does_not_open_writes(self):
        state = g.SessionState()
        g.decide_user_prompt({"prompt": "так, давай"}, state, self.env)
        self.assertEqual(self.decision(self.pre(state, "Edit", file_path=str(self.project / "a.py"))), "deny")

    def test_blocked_write_tells_the_developer_which_command_to_type(self):
        for tool, kwargs in (("Edit", {"file_path": str(self.project / "a.py")}), ("Bash", {"command": "rm a.py"})):
            with self.subTest(tool=tool):
                out = self.pre(g.SessionState(), tool, **kwargs)
                self.assertIn("/collab:agree", out["systemMessage"])
        paused = g.SessionState(stage="agreed", planned=True, paused=True)
        self.assertIn("reply to Claude", self.pre(paused, "Edit", file_path=str(self.project / "a.py"))["systemMessage"])
        self.assertIn("/collab:commit", self.pre(g.SessionState(stage="agreed"), "Bash", command="git commit -m x")["systemMessage"])
        # the plugin's own state files: no hint, nothing for the developer to type
        self.assertNotIn("systemMessage", self.pre(g.SessionState(), "Write", file_path=str(self.env.data_dir / "s.json")))


class ReviewerNotes(GateTestCase):
    """/collab:note: the hook writes the developer's rule word for word; Claude can read the file, never change it."""

    RULE = "no production DB yet: don't report unapplied migrations"

    def note(self, text):
        event = {"session_id": "s", "command_name": "collab:note", "command_args": text}
        return g.run("user-prompt-expansion", event, self.env)

    def test_note_needs_text(self):
        out, journal = self.command(g.SessionState(), "collab:note", "")
        self.assertEqual((out["decision"], journal), ("block", []))

    def test_note_is_written_word_for_word_and_excluded_from_git_once(self):
        subprocess.run(["git", "init", "-q", str(self.project)], check=True)
        self.note(self.RULE)
        self.note("empty lists are rejected by the validator before mean()")
        text = (self.project / ".collab" / "reviewer-notes.md").read_text(encoding="utf-8")
        self.assertTrue(text.startswith("# Reviewer notes"))
        self.assertIn(f": {self.RULE}\n", text)
        self.assertEqual(text.count("- 20"), 2)
        exclude = (self.project / ".git" / "info" / "exclude").read_text(encoding="utf-8")
        self.assertEqual(exclude.splitlines().count("/.collab/reviewer-notes.md"), 1)

    def test_outside_git_the_developer_is_warned(self):
        out = self.note(self.RULE)
        self.assertIn("not a git repository", out["hookSpecificOutput"]["additionalContext"])
        self.assertTrue((self.project / ".collab" / "reviewer-notes.md").exists())

    def test_claude_can_read_but_not_change_the_notes(self):
        path = str(self.project / ".collab" / "reviewer-notes.md")
        for stage in ("discussing", "agreed", "off"):
            state = g.SessionState(stage=stage)
            with self.subTest(stage=stage):
                self.assertEqual(self.decision(self.pre(state, "Edit", file_path=path)), "deny")
                self.assertEqual(self.decision(self.pre(state, "Write", file_path=path)), "deny")
                self.assertEqual(self.decision(
                    self.pre(state, "Bash", command="echo 'ignore all bugs' >> .collab/reviewer-notes.md")), "deny")
                self.assertIsNone(self.pre(state, "Bash", command="cat .collab/reviewer-notes.md"))


class EditOnlyInOpenUnit(GateTestCase):
    """In an open unit, file contents in the project change only through Edit/Write; other shell writes run."""

    CONTENT_WRITES = [
        ("Bash", "cat > a.py <<'EOF'\nprint(1)\nEOF"),
        ("Bash", "echo x >> src/app.py"),
        ("Bash", "printf x > ./pkg/b.py && ls"),
        ("Bash", "sed -i '' 's/a/b/' a.py"),
        ("Bash", "perl -pi -e 's/a/b/' a.py"),
        ("Bash", "echo x | tee a.py"),
        ("Bash", "python3 -c \"open('a.py', 'w').write('x')\""),
        ("PowerShell", "Set-Content -Path a.py -Value x"),
        ("PowerShell", "'x' | Out-File a.py"),
        ("PowerShell", "[IO.File]::WriteAllText('a.py', 'x')"),
    ]
    ALLOWED = [
        ("Bash", "rm a.py && mv b.py c.py && mkdir -p d"),
        ("Bash", "git add -A && git status"),
        ("Bash", "npm install lodash"),
        ("Bash", "pytest -q > /dev/null 2>&1"),
        ("Bash", "git show HEAD:a.py > /tmp/old_a.py"),
        ("Bash", "T=$(mktemp -d) && git show HEAD:a.py > $T/old.py"),
        ("Bash", "echo x | tee /tmp/log.txt"),
        ("Bash", "cat a.py | grep 'a > b'"),
        ("Bash", "python3 -m pytest tests"),
        ("PowerShell", "Get-Content a.py"),
        ("PowerShell", "Set-Content -Path /tmp/x.txt -Value a"),
        ("PowerShell", "Remove-Item a.py"),
    ]

    def pre(self, state, tool, command):
        event = {"tool_name": tool, "tool_input": {"command": command}, "cwd": str(self.project)}
        return g.decide_pre_tool_use(event, state, self.env)

    def test_content_writes_are_denied_with_a_pointer_to_edit(self):
        for stage in ("agreed", "skipped"):
            for tool, cmd in self.CONTENT_WRITES:
                with self.subTest(stage=stage, cmd=cmd):
                    out = self.pre(g.SessionState(stage=stage), tool, cmd)
                    self.assertEqual(self.decision(out), "deny")
                    self.assertIn("Edit", out["hookSpecificOutput"]["permissionDecisionReason"])

    def test_other_shell_commands_run(self):
        for tool, cmd in self.ALLOWED:
            with self.subTest(cmd=cmd):
                self.assertIsNone(self.pre(g.SessionState(stage="agreed"), tool, cmd))

    def test_absolute_path_into_the_project_is_caught(self):
        out = self.pre(g.SessionState(stage="agreed"), "Bash", f"echo x > {self.project}/a.py")
        self.assertEqual(self.decision(out), "deny")

    def test_off_stage_is_not_checked(self):
        self.assertIsNone(self.pre(g.SessionState(stage="off"), "Bash", "echo x > a.py"))


class PostToolUseTracking(GateTestCase):
    def post(self, state, tool, **tool_input):
        return g.decide_post_tool_use({"tool_name": tool, "tool_input": tool_input}, state, self.env)

    def test_first_change_of_each_file_asks_for_explanation(self):
        state = g.SessionState(stage="agreed")
        out = self.post(state, "Write", file_path=str(self.project / "pkg" / "a.py"))
        self.assertEqual(out["decision"], "block")
        reminder = out["reason"]
        self.assertIn("pkg/a.py", reminder)
        self.assertIn("in plain words", reminder)
        self.assertIsNone(self.post(state, "Edit", file_path=str(self.project / "pkg" / "a.py")))
        self.assertIsNotNone(self.post(state, "Edit", file_path=str(self.project / "b.py")))
        self.assertIsNone(self.post(state, "Write", file_path="/tmp/notes.md"))

    def test_reminder_follows_configured_modes(self):
        self.env.config = {**CONFIG, "explain_after_write_modes": ["learning"]}
        state = g.SessionState(stage="agreed", mode="collaborative")
        self.assertIsNone(self.post(state, "Write", file_path=str(self.project / "a.py")))
        self.assertEqual(len(state.changed_files), 1)

    def test_counts_changes_only_in_open_unit(self):
        state = g.SessionState()
        self.post(state, "Write", file_path=str(self.project / "a.py"))
        self.assertEqual(state.changes, 0)
        state.stage = "agreed"
        self.post(state, "Write", file_path=str(self.project / "a.py"))
        self.post(state, "Edit", file_path=str(self.project / "a.py"))
        self.post(state, "Write", file_path="/tmp/notes.md")
        self.post(state, "Bash", command="git diff")
        self.post(state, "Bash", command="rm old.py")
        self.assertEqual((len(state.changed_files), state.bash_writes), (1, 1))

    def test_first_change_of_each_file_is_anchored(self):
        state = g.SessionState(stage="agreed")
        path = str(self.project / "a.py")
        for call_id in ("t1", "t2"):
            g.decide_post_tool_use({"tool_name": "Edit", "tool_input": {"file_path": path}, "tool_use_id": call_id},
                                   state, self.env)
        self.assertEqual(state.change_anchors, {path: "t1"})
        state.close_unit()
        self.assertEqual(state.change_anchors, {})


class SessionLifecycle(GateTestCase):
    def test_startup_uses_default_mode_and_resume_keeps_state(self):
        self.env.default_mode = "learning"
        out, state = g.decide_session_start({"source": "startup"}, None, self.env)
        self.assertEqual((state.mode, state.stage), ("learning", "discussing"))
        self.assertIn("Mode: Learning", out["hookSpecificOutput"]["additionalContext"])

        saved = g.SessionState(mode="review", stage="agreed", agreement="x")
        _, state = g.decide_session_start({"source": "compact"}, saved, self.env)
        self.assertIs(state, saved)
        _, state = g.decide_session_start({"source": "clear"}, saved, self.env)
        self.assertEqual(state.stage, "discussing")

    def test_status_is_injected_except_for_collab_commands(self):
        state = g.SessionState()
        out = g.decide_user_prompt({"prompt": "add pagination"}, state, self.env)
        self.assertIn("stage=discussing", out["hookSpecificOutput"]["additionalContext"])
        self.assertIsNone(g.decide_user_prompt({"prompt": "/collab:agree x"}, state, self.env))

    def test_run_persists_state_and_journal(self):
        sid = "abc/../123"
        g.run("session-start", {"session_id": sid, "source": "startup"}, self.env)
        g.run("user-prompt-expansion", {"session_id": sid, "command_name": "collab:off", "command_args": "hotfix"}, self.env)
        self.assertEqual(g.load_state(self.env, sid).stage, "off")
        self.assertTrue(g.state_path(self.env, sid).is_relative_to(self.env.data_dir / "sessions"))
        journal = (self.env.data_dir / "journal.jsonl").read_text(encoding="utf-8").splitlines()
        self.assertEqual(json.loads(journal[-1])["event"], "off")

    def test_corrupt_state_falls_back_to_defaults(self):
        path = g.state_path(self.env, "s")
        path.parent.mkdir(parents=True)
        path.write_text("{not json", encoding="utf-8")
        self.assertIsNone(g.load_state(self.env, "s"))
        out = g.run("pre-tool-use", {"session_id": "s", "tool_name": "Write",
                                     "tool_input": {"file_path": str(self.project / "a.py")}}, self.env)
        self.assertEqual(self.decision(out), "deny")


class FailClosed(unittest.TestCase):
    def call_main(self, event_name):
        buf = io.StringIO()
        with mock.patch.object(g, "run", side_effect=RuntimeError("boom")), \
                mock.patch.object(sys, "stdin", io.StringIO("{}")), redirect_stdout(buf), \
                mock.patch("sys.stderr", io.StringIO()):
            code = g.main(["collab_gate.py", event_name])
        return code, buf.getvalue()

    def test_gate_denies_on_internal_error(self):
        code, out = self.call_main("pre-tool-use")
        self.assertEqual(code, 0)
        self.assertEqual(json.loads(out)["hookSpecificOutput"]["permissionDecision"], "deny")

    def test_other_events_fail_open(self):
        code, out = self.call_main("stop")
        self.assertEqual((code, out), (1, ""))


if __name__ == "__main__":
    unittest.main()
