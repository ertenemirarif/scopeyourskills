"""X-ray (flow + quality score) and audit (structural checks) modes.

Ideas: silvesterdivas/skillscope (skill flowchart, quality score) and
amd/skillscope (structural and routing tests, MIT). Implemented from scratch here.
"""
import json
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
import scopeyourskills as skillscope  # noqa: E402

GOOD = """---
name: slide-maker
description: Build slide decks from notes. Use when the user asks for slides, a deck or a presentation.
---
# Slide maker

## Steps
1. Read the notes with the Read tool.
2. If the notes are empty, ask the user for content.
3. Run `python scripts/build.py` with Bash.
4. Save the deck.

## Example
Input: three bullet points. Output: a 3-slide deck.

## Output
A .pptx file. See [the template guide](references/template.md).
"""


def make(folder: Path, name: str, text: str) -> Path:
    p = folder / name / "SKILL.md"
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(text, encoding="utf-8")
    return p


class Xray(unittest.TestCase):
    def test_flow_nodes(self):
        meta, body = skillscope.parse_frontmatter(GOOD)
        x = skillscope.xray(meta, body)
        kinds = [n["k"] for n in x["flow"]]
        self.assertEqual(kinds[0], "trigger")
        self.assertIn("step", kinds)
        self.assertIn("branch", kinds)
        self.assertIn("tool", kinds)
        self.assertIn("output", kinds)
        self.assertTrue(all(len(n["t"]) <= 90 for n in x["flow"]))
        self.assertLessEqual(len(x["flow"]), skillscope.MAX_FLOW)

    def test_score_good_vs_bare(self):
        meta, body = skillscope.parse_frontmatter(GOOD)
        good = skillscope.quality(meta, body, "slide-maker", [])
        meta2, body2 = skillscope.parse_frontmatter("---\nname: x\n---\nDo stuff.\n")
        bare = skillscope.quality(meta2, body2, "x", [])
        self.assertGreater(good["score"], 80)
        self.assertLess(bare["score"], 50)
        self.assertEqual(set(good["parts"]), {"trigger", "structure", "size", "examples", "resources"})
        self.assertIn("no_trigger_phrase", bare["fixes"])


class Audit(unittest.TestCase):
    def test_structural_checks(self):
        t = Path(tempfile.mkdtemp())
        f = make(t, "slide-maker", GOOD)
        self.assertIn("missing_ref", skillscope.lint(f, *skillscope.parse_frontmatter(GOOD)))
        (f.parent / "references").mkdir()
        (f.parent / "references" / "template.md").write_text("x", encoding="utf-8")
        (f.parent / "scripts").mkdir()
        (f.parent / "scripts" / "build.py").write_text("x", encoding="utf-8")
        self.assertEqual(skillscope.lint(f, *skillscope.parse_frontmatter(GOOD)), [])

        g = make(t, "folder-name", "---\nname: Other_Name\n---\nbody\n")
        issues = skillscope.lint(g, *skillscope.parse_frontmatter(g.read_text(encoding="utf-8")))
        for code in ("name_mismatch", "name_format", "desc_missing"):
            self.assertIn(code, issues)
        h = make(t, "nofm", "just text\n")
        self.assertIn("frontmatter_missing", skillscope.lint(h, *skillscope.parse_frontmatter("just text\n")))

    def test_embedded_in_output(self):
        t = Path(tempfile.mkdtemp())
        make(t, "slide-maker", GOOD)
        out = tempfile.mkdtemp()
        skillscope.main(["--no-defaults", "--active-path", f"A={t}", "--out", out, "--translations", out + "/tr"])
        data = json.loads((Path(out) / "skills.json").read_text(encoding="utf-8"))
        s = data["skills"][0]
        self.assertIn("score", s["quality"])
        self.assertIn("flow", s["xray"])
        self.assertIn("missing_ref", s["lint"])
        html = (Path(out) / "scope-your-skills.html").read_text(encoding="utf-8")
        self.assertIn('"quality"', html)
        self.assertIn("function routeMatch(", html)   # in-browser routing simulator


if __name__ == "__main__":
    unittest.main()
