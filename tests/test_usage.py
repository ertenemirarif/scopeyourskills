"""Usage from Claude Code transcripts: which installed skills actually fire."""
import json
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
import scopeyourskills as skillscope  # noqa: E402


def line(**kw) -> str:
    return json.dumps(kw) + "\n"


def tool_call(skill, ts, session, tid):
    return line(type="assistant", timestamp=ts, sessionId=session,
                message={"role": "assistant", "content": [
                    {"type": "tool_use", "id": tid, "name": "Skill", "input": {"skill": skill}}]})


def slash(cmd, ts, session):
    return line(type="user", timestamp=ts, sessionId=session,
                message={"role": "user", "content": f"<command-name>/{cmd}</command-name>\n<command-args></command-args>"})


class Usage(unittest.TestCase):
    def setUp(self):
        self.t = Path(tempfile.mkdtemp())
        proj = self.t / "projects" / "p1"
        proj.mkdir(parents=True)
        (proj / "s1.jsonl").write_text(
            tool_call("brand", "2026-11-01T10:00:00Z", "s1", "t1")
            + tool_call("brand", "2026-11-01T10:05:00Z", "s1", "t2")
            + tool_call("brand", "2026-11-01T10:05:00Z", "s1", "t2")      # same call logged twice: count once
            + tool_call("design:design-critique", "2026-11-03T09:00:00Z", "s1", "t3")
            + slash("compact", "2026-11-03T09:01:00Z", "s1")              # built-in command, not a skill
            + "not json at all\n", encoding="utf-8")
        (proj / "s2.jsonl").write_text(
            slash("cinecode", "2026-11-05T20:00:00Z", "s2")
            + tool_call("brand", "2026-11-06T08:00:00Z", "s2", "t9"), encoding="utf-8")

    def test_counts_fires_sessions_and_last_use(self):
        u = skillscope.scan_usage(self.t / "projects")
        self.assertEqual(u["calls"]["brand"]["fires"], 3)
        self.assertEqual(u["calls"]["brand"]["sessions"], 2)
        self.assertEqual(u["calls"]["brand"]["last"], "2026-11-06")
        self.assertEqual(u["calls"]["design:design-critique"]["fires"], 1)
        self.assertEqual(u["calls"]["cinecode"]["fires"], 1)
        self.assertEqual(u["first"], "2026-11-01")
        self.assertEqual(u["files"], 2)

    def test_attach_to_installed_skills_only(self):
        skills_dir = self.t / "skills"
        for name in ("brand", "cinecode", "never-used"):
            p = skills_dir / name / "SKILL.md"
            p.parent.mkdir(parents=True)
            p.write_text(f"---\nname: {name}\ndescription: d {name}\n---\n", encoding="utf-8")
        out = tempfile.mkdtemp()
        rc = skillscope.main(["--no-defaults", "--active-path", f"A={skills_dir}", "--out", out,
                              "--translations", out + "/tr", "--usage", "--usage-dir", str(self.t / "projects")])
        self.assertEqual(rc, 0)
        data = json.loads((Path(out) / "skills.json").read_text(encoding="utf-8"))
        by = {s["name"]: s for s in data["skills"]}
        self.assertEqual(by["brand"]["usage"]["fires"], 3)
        self.assertEqual(by["cinecode"]["usage"]["fires"], 1)
        self.assertEqual(by["never-used"]["usage"]["fires"], 0)
        self.assertNotIn("compact", json.dumps(data["usage"]))
        self.assertEqual(data["usage"]["never"], 1)
        # transcript text never reaches the output
        html = (Path(out) / "scope-your-skills.html").read_text(encoding="utf-8")
        self.assertNotIn("command-args", html)

    def test_off_by_default(self):
        out = tempfile.mkdtemp()
        p = self.t / "skills" / "x" / "SKILL.md"
        p.parent.mkdir(parents=True)
        p.write_text("---\nname: x\ndescription: d\n---\n", encoding="utf-8")
        skillscope.main(["--no-defaults", "--active-path", f"A={self.t / 'skills'}", "--out", out,
                         "--translations", out + "/tr"])
        data = json.loads((Path(out) / "skills.json").read_text(encoding="utf-8"))
        self.assertIsNone(data.get("usage"))
        self.assertNotIn("usage", data["skills"][0])


if __name__ == "__main__":
    unittest.main()


def answer(skill, ts, session, mid, tokens):
    return line(type="assistant", timestamp=ts, sessionId=session, attributionSkill=skill,
                message={"id": mid, "role": "assistant", "content": [{"type": "text", "text": "x"}],
                         "usage": {"input_tokens": tokens, "output_tokens": 10,
                                   "cache_creation_input_tokens": 5, "cache_read_input_tokens": 999}})


class Tokens(unittest.TestCase):
    """Measured tokens from attributionSkill (idea from notsointresting/skillscope, MIT)."""

    def test_attributed_tokens_counted_once_per_message(self):
        t = Path(tempfile.mkdtemp())
        proj = t / "projects" / "p"
        proj.mkdir(parents=True)
        (proj / "s.jsonl").write_text(
            answer("brand", "2026-11-01T10:00:00Z", "s", "m1", 100)
            + answer("brand", "2026-11-01T10:00:00Z", "s", "m1", 100)   # same message, second content block
            + answer("brand", "2026-11-01T10:01:00Z", "s", "m2", 50), encoding="utf-8")
        u = skillscope.scan_usage(t / "projects")
        # input + output + cache creation; cache reads are near-free and left out
        self.assertEqual(u["tokens"]["brand"], (100 + 10 + 5) + (50 + 10 + 5))

    def test_overhead_estimate_and_summary(self):
        t = Path(tempfile.mkdtemp())
        (t / "projects" / "p").mkdir(parents=True)
        (t / "projects" / "p" / "a.jsonl").write_text(tool_call("used", "2026-11-01T10:00:00Z", "a", "t1"), encoding="utf-8")
        (t / "projects" / "p" / "b.jsonl").write_text("", encoding="utf-8")
        for name, desc in (("used", "x" * 40), ("idle", "y" * 400)):
            p = t / "skills" / name / "SKILL.md"
            p.parent.mkdir(parents=True)
            p.write_text(f"---\nname: {name}\ndescription: {desc}\n---\n", encoding="utf-8")
        out = tempfile.mkdtemp()
        skillscope.main(["--no-defaults", "--active-path", f"A={t / 'skills'}", "--out", out,
                         "--translations", out + "/tr", "--usage", "--usage-dir", str(t / "projects")])
        data = json.loads((Path(out) / "skills.json").read_text(encoding="utf-8"))
        by = {s["name"]: s for s in data["skills"]}
        self.assertEqual(by["idle"]["usage"]["overhead"], round((400 + 4) / 4))   # tokens per session, estimate
        self.assertEqual(data["usage"]["sessions"], 2)
        self.assertEqual(data["usage"]["idle_overhead"], by["idle"]["usage"]["overhead"])
