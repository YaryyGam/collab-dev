"""Unit tests for the deterministic part of the plugin: scripts/collab_gate.py.

Run: python3 -m unittest discover -s plugins/collab/tests -v
"""
import io
import json
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
    AGREEMENT = "offset пагинация через limit и offset потому что таблица небольшая"

    def test_agree_requires_own_words(self):
        state = g.SessionState()
        out, journal = self.command(state, "collab:agree", "ок")
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

    def test_skip_and_off_require_reason(self):
        for name in ("collab:skip", "collab:off"):
            with self.subTest(name=name):
                state = g.SessionState()
                out, _ = self.command(state, name, "  ")
                self.assertEqual(out["decision"], "block")
                self.assertEqual(state.stage, "discussing")

    def test_off_then_on(self):
        state = g.SessionState()
        self.command(state, "collab:off", "срочный хотфикс")
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
        self.assertIn("Режим: Learning", out["hookSpecificOutput"]["additionalContext"])
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
    REVIEW = "## Итоговый разбор\n### 1. Что реализовано\nПагинация.\n### 7. Проверка\nТесты не запускались."

    def stop(self, state, message, active=False):
        return g.decide_stop({"last_assistant_message": message, "stop_hook_active": active}, state, self.env)

    def test_no_check_outside_open_unit(self):
        self.assertIsNone(self.stop(g.SessionState(), "готово"))
        self.assertIsNone(self.stop(g.SessionState(stage="off", changed_files=["a"]), "готово"))

    def test_open_unit_without_changes_may_stop(self):
        self.assertIsNone(self.stop(g.SessionState(stage="agreed"), "Начинаю с модели данных."))

    def test_changes_without_review_are_blocked(self):
        out = self.stop(g.SessionState(stage="agreed", changed_files=["a.py"]), "Готово, всё сделал.")
        self.assertEqual(out["decision"], "block")
        self.assertIn("Итоговый разбор", out["reason"])

    def test_question_to_developer_is_a_valid_pause(self):
        msg = "Добавил модель.\n\nДальше два варианта обработки ошибок. Какой выберешь и почему?"
        self.assertIsNone(self.stop(g.SessionState(stage="agreed", changed_files=["a.py"]), msg))

    def test_retry_is_never_blocked_twice(self):
        self.assertIsNone(self.stop(g.SessionState(stage="agreed", changed_files=["a.py"]), "Готово.", active=True))

    def test_review_without_verification_is_blocked(self):
        state = g.SessionState(stage="agreed", changed_files=["a.py"])
        out = self.stop(state, "## Итоговый разбор\nСделана пагинация.")
        self.assertEqual(out["decision"], "block")
        self.assertIn("Проверка", out["reason"])
        self.assertEqual(state.stage, "agreed")

    def test_complete_review_closes_unit(self):
        state = g.SessionState(stage="skipped", changed_files=["a.py"])
        out = self.stop(state, self.REVIEW)
        self.assertNotIn("decision", out)
        self.assertEqual((state.stage, state.units_closed), ("discussing", 1))

    def test_ukrainian_and_english_headings(self):
        for review in ("## Підсумковий розбір\n### Перевірка\n-", "## Final review\n### Verification\n-"):
            with self.subTest(review=review):
                state = g.SessionState(stage="agreed", changed_files=["a.py"])
                self.stop(state, review)
                self.assertEqual(state.stage, "discussing")


class PostToolUseTracking(GateTestCase):
    def post(self, state, tool, **tool_input):
        return g.decide_post_tool_use({"tool_name": tool, "tool_input": tool_input}, state, self.env)

    def test_first_change_of_each_file_asks_for_explanation(self):
        state = g.SessionState(stage="agreed")
        out = self.post(state, "Write", file_path=str(self.project / "pkg" / "a.py"))
        self.assertEqual(out["decision"], "block")
        reminder = out["reason"]
        self.assertIn("pkg/a.py", reminder)
        self.assertIn("на пальцах", reminder)
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


class SessionLifecycle(GateTestCase):
    def test_startup_uses_default_mode_and_resume_keeps_state(self):
        self.env.default_mode = "learning"
        out, state = g.decide_session_start({"source": "startup"}, None, self.env)
        self.assertEqual((state.mode, state.stage), ("learning", "discussing"))
        self.assertIn("Режим: Learning", out["hookSpecificOutput"]["additionalContext"])

        saved = g.SessionState(mode="review", stage="agreed", agreement="x")
        _, state = g.decide_session_start({"source": "compact"}, saved, self.env)
        self.assertIs(state, saved)
        _, state = g.decide_session_start({"source": "clear"}, saved, self.env)
        self.assertEqual(state.stage, "discussing")

    def test_status_is_injected_except_for_collab_commands(self):
        state = g.SessionState()
        out = g.decide_user_prompt({"prompt": "добавь пагинацию"}, state, self.env)
        self.assertIn("стадия=discussing", out["hookSpecificOutput"]["additionalContext"])
        self.assertIsNone(g.decide_user_prompt({"prompt": "/collab:agree x"}, state, self.env))

    def test_run_persists_state_and_journal(self):
        sid = "abc/../123"
        g.run("session-start", {"session_id": sid, "source": "startup"}, self.env)
        g.run("user-prompt-expansion", {"session_id": sid, "command_name": "collab:off", "command_args": "хотфикс"}, self.env)
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
