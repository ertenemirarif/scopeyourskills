"""Regression tests for the pre-release correctness review (finding ids C1..C16)."""
import json
import tempfile
import unittest
from pathlib import Path

import sys
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
import scopeyourskills as skillscope  # noqa: E402


def write(p: Path, text: str) -> Path:
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(text, encoding="utf-8")
    return p


def skill(folder: Path, name: str, desc: str, body: str = "") -> Path:
    return write(folder / name / "SKILL.md", f"---\nname: {name}\ndescription: {desc}\n---\n{body}")


def run(*args):
    out = tempfile.mkdtemp()
    rc = skillscope.main(["--no-defaults", "--out", out, "--translations", out + "/tr", *args])
    assert rc == 0
    return json.loads((Path(out) / "skills.json").read_text(encoding="utf-8")), Path(out)


class Overlaps(unittest.TestCase):
    def test_c1_whitespace_difference_is_not_an_exact_copy(self):
        t = Path(tempfile.mkdtemp())
        skill(t / "a", "tool", "does things", "```py\nif x:\n    finish()\n```\n")
        skill(t / "b", "tool", "does things", "```py\nif x:\nfinish()\n```\n")
        data, _ = run("--path", f"R={t}")
        self.assertEqual(data["overlaps"]["copies"], [])
        self.assertEqual(len(data["overlaps"]["versions"]), 1)

    def test_c2_active_wins_when_same_file_seen_twice(self):
        t = Path(tempfile.mkdtemp())
        skill(t / "repo", "x", "makes slides")
        data, _ = run("--path", f"D={t / 'repo'}", "--active-path", f"A={t / 'repo'}")
        self.assertEqual(len(data["skills"]), 1)
        self.assertTrue(data["skills"][0]["active"])

    def test_c3_c4_two_skill_overlap_found_and_not_sibling(self):
        t = Path(tempfile.mkdtemp())
        skill(t / "p1" / "skills", "alpha", "deploy kubernetes cluster with helm charts")
        skill(t / "p2" / "skills", "beta", "deploy kubernetes cluster with helm charts")
        data, _ = run("--active-path", f"A={t / 'p1'}", "--active-path", f"B={t / 'p2'}")
        pairs = data["overlaps"]["pairs"]
        self.assertEqual(len(pairs), 1)
        self.assertFalse(pairs[0]["same_repo"])
        self.assertTrue(pairs[0]["live"])


class Packages(unittest.TestCase):
    def test_c6_repo_root_found_when_path_is_the_repo(self):
        t = Path(tempfile.mkdtemp())
        repo = t / "foo"
        write(repo / ".git" / "config", '[remote "origin"]\n\turl = https://github.com/me/foo.git\n')
        write(repo / "LICENSE", "MIT License\n\nPermission is hereby granted, free of charge, ...")
        skill(repo / "skills", "bar", "does bar")
        data, _ = run("--path", f"R={repo}")
        pkg = data["packages"][data["skills"][0]["pkg"]]
        self.assertEqual(pkg["url"], "https://github.com/me/foo")
        self.assertEqual(pkg["license"], "MIT")
        self.assertEqual(pkg["title"], "Foo")

    def test_c7_same_plugin_name_different_vendors_stay_apart(self):
        t = Path(tempfile.mkdtemp())
        for vendor in ("acme", "zeta"):
            write(t / vendor / ".claude-plugin" / "plugin.json",
                  json.dumps({"name": "tools", "author": {"name": vendor}, "repository": f"https://github.com/{vendor}/tools"}))
            skill(t / vendor / "skills", f"{vendor}-x", "x")
        data, _ = run("--path", f"R={t}")
        self.assertEqual(len({s["pkg"] for s in data["skills"]}), 2)


class Text(unittest.TestCase):
    def test_c12_uppercase_english_keywords_categorised(self):
        cats = skillscope.compile_categories(json.loads((ROOT / "categories.json").read_text(encoding="utf-8")))
        self.assertEqual(skillscope.categorize("x", "IMAGE GENERATION AND ICON DESIGN", cats)[0], "visual")
        self.assertEqual(skillscope.categorize("API", "REST API backend", cats)[0], "dev")

    def test_c13_yaml_comments(self):
        meta, _ = skillscope.parse_frontmatter("---\nname: foo # note\ndescription: > # c\n  real text\n  here\n---\n")
        self.assertEqual(meta["name"], "foo")
        self.assertEqual(meta["description"], "real text here")
        meta, _ = skillscope.parse_frontmatter("---\nname: \"a # b\"\n---\n")
        self.assertEqual(meta["name"], "a # b")
        meta, _ = skillscope.parse_frontmatter("---\ndescription: 'Use to define a brand''s pillars' # x\n---\n")
        self.assertEqual(meta["description"], "Use to define a brand's pillars")

    def test_c14_bad_translation_cache_ignored(self):
        t = Path(tempfile.mkdtemp())
        skill(t / "a", "x", "makes slides")
        out = tempfile.mkdtemp()
        write(Path(out) / "tr" / "tr.json", "[]")
        write(Path(out) / "tr" / "en.json", json.dumps({skillscope.desc_key("makes slides"): ""}))
        rc = skillscope.main(["--no-defaults", "--out", out, "--translations", out + "/tr", "--path", f"R={t}",
                              "--langs", "tr,en", "--lang", "tr", "--export-missing", out + "/todo"])
        self.assertEqual(rc, 0)
        self.assertTrue((Path(out) / "todo" / "missing-tr.json").is_file())


class Cli(unittest.TestCase):
    def test_c8_relative_out_with_open_does_not_crash(self):
        import webbrowser
        opened = []
        real = webbrowser.open
        webbrowser.open = lambda u, *a, **k: opened.append(u)
        try:
            t = Path(tempfile.mkdtemp())
            skill(t / "a", "x", "y")
            import os
            old = os.getcwd()
            os.chdir(t)
            try:
                rc = skillscope.main(["--no-defaults", "--path", f"R={t}", "--out", "rel-out", "--open",
                                      "--translations", str(t / "tr")])
            finally:
                os.chdir(old)
            self.assertEqual(rc, 0)
            self.assertTrue(opened and opened[0].startswith("file:"))
        finally:
            webbrowser.open = real

    def test_c9_c10_task_args_rebuilt_from_parsed_options(self):
        cmd = skillscope.task_command(["--path", "R=rel/repo", "--export-missing", "todo", "--out", "o",
                                       "--github", "--schedule", "weekly", "--open"])
        self.assertNotIn("todo", cmd)
        self.assertNotIn("--open", cmd)
        self.assertNotIn("--schedule", cmd)
        self.assertIn("--github", cmd)
        path_arg = cmd[cmd.index("--path") + 1]
        self.assertTrue(Path(path_arg.split("=", 1)[1]).is_absolute())
        self.assertTrue(Path(cmd[cmd.index("--out") + 1]).is_absolute())


class Template(unittest.TestCase):
    def test_c15_c16_template_fixes_present(self):
        tpl = (ROOT / "template.html").read_text(encoding="utf-8")
        self.assertIn("function viewRepos(rows)", tpl)
        self.assertIn("search(/[-/]/)", tpl)          # split route at the first separator only
        self.assertIn("catch(e){h=\"\"}", tpl)        # bad percent-encoding does not break boot


if __name__ == "__main__":
    unittest.main()


class PackagesRound2(unittest.TestCase):
    def test_zip_repo_root_without_git(self):
        t = Path(tempfile.mkdtemp())
        repo = t / "unzipped-repo"
        skill(repo / "skills", "x", "does x")
        data, _ = run("--path", f"R={repo}")
        self.assertEqual(data["packages"][data["skills"][0]["pkg"]]["title"], "Unzipped Repo")

    def test_same_homepage_different_authors_stay_apart(self):
        t = Path(tempfile.mkdtemp())
        for vendor in ("acme", "zeta"):
            write(t / vendor / ".claude-plugin" / "plugin.json",
                  json.dumps({"name": "tools", "author": vendor, "homepage": "https://example.com"}))
            skill(t / vendor / "skills", f"{vendor}-x", "x")
        data, _ = run("--path", f"R={t}")
        self.assertEqual(len({s["pkg"] for s in data["skills"]}), 2)
