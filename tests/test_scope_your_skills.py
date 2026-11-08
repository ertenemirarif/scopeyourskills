import json
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
import scopeyourskills as skillscope  # noqa: E402

FIX = ROOT / "tests" / "fixtures"


class ScopeYourSkillsTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.TemporaryDirectory()
        rc = skillscope.main(["--no-defaults", "--path", f"fixtures={FIX}", "--out", cls.tmp.name])
        assert rc == 0
        cls.data = json.loads((Path(cls.tmp.name) / "skills.json").read_text(encoding="utf-8"))
        cls.by = {s["path"].split("\\")[-1].split("/")[-1] + "@" + s["repo"]: s for s in cls.data["skills"]}

    @classmethod
    def tearDownClass(cls):
        cls.tmp.cleanup()

    def test_frontmatter_folded_description(self):
        s = self.by["slide-deck@repo-b"]
        self.assertIn("Build presentation slide decks", s["description"])
        self.assertIn("Use when the user wants slides", s["description"])

    def test_categories(self):
        self.assertEqual(self.by["pptx-maker@repo-a"]["category"], "docs")
        self.assertEqual(self.by["podcast-voice@repo-b"]["category"], "audio")

    def test_functional_overlap_found(self):
        names = {frozenset((self.data["skills"][p["a"]]["name"], self.data["skills"][p["b"]]["name"]))
                 for p in self.data["overlaps"]["pairs"]}
        self.assertIn(frozenset(("pptx-maker", "slide-deck")), names)
        self.assertNotIn(frozenset(("pptx-maker", "podcast-voice")), names)

    def test_same_name_versions(self):
        self.assertEqual([v["name"] for v in self.data["overlaps"]["versions"]], ["pptx-maker"])

    def test_html_written(self):
        html = (Path(self.tmp.name) / "scope-your-skills.html").read_text(encoding="utf-8")
        self.assertNotIn("/*__DATA__*/null", html)


if __name__ == "__main__":
    unittest.main()
