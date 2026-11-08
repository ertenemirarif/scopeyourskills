"""Regression tests for the pre-release security review (finding ids S1..S12)."""
import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
import scopeyourskills as skillscope  # noqa: E402


def write(p: Path, text: str) -> Path:
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(text, encoding="utf-8")
    return p


def run_main(*args):
    out = tempfile.mkdtemp()
    rc = skillscope.main(["--no-defaults", "--out", out, "--translations", out + "/tr", *args])
    data = json.loads((Path(out) / "skills.json").read_text(encoding="utf-8")) if rc == 0 else None
    return rc, out, data


class SanitizeUrl(unittest.TestCase):  # S2, S7
    def test_strips_credentials_query_fragment(self):
        self.assertEqual(skillscope.safe_url("https://user:ghp_SECRET@github.com/org/repo.git?x=1#y"),
                         "https://github.com/org/repo")

    def test_rejects_non_http(self):
        for bad in ("javascript:alert(1)", "file:///etc/passwd", "data:text/html,x", "  "):
            self.assertEqual(skillscope.safe_url(bad), "")

    def test_ssh_remote_converted(self):
        self.assertEqual(skillscope.safe_url("git@github.com:org/repo.git"), "https://github.com/org/repo")

    def test_token_never_reaches_output(self):
        tmp = Path(tempfile.mkdtemp())
        repo = tmp / "repos" / "evil"
        write(repo / ".git" / "config", '[remote "origin"]\n\turl = https://bob:ghp_TOPSECRET@github.com/bob/evil.git\n')
        write(repo / "skills" / "x" / "SKILL.md", "---\nname: x\ndescription: makes slides\n---\n")
        rc, out, data = run_main("--path", f"R={tmp / 'repos'}")
        self.assertEqual(rc, 0)
        for f in Path(out).glob("*"):
            if f.is_file():
                self.assertNotIn("TOPSECRET", f.read_text(encoding="utf-8", errors="replace"), f.name)


class EmbeddingAndArtifact(unittest.TestCase):  # S11
    def test_no_raw_lt_in_embedded_json_and_artifact_intact(self):
        tmp = Path(tempfile.mkdtemp())
        write(tmp / "a" / "skills" / "x" / "SKILL.md",
              "---\nname: x\ndescription: \"evil <!--<script> and text <html <body> </script>\"\n---\n")
        rc, out, _ = run_main("--path", f"R={tmp}")
        html = (Path(out) / "scope-your-skills.html").read_text(encoding="utf-8")
        start = html.index("const DATA = ") + len("const DATA = ")
        end = html.index(";\nconst LSTORE") if ";\nconst LSTORE" in html else html.index("\n", start)
        self.assertNotIn("<", html[start:end])
        art = (Path(out) / "scope-your-skills.artifact.html").read_text(encoding="utf-8")
        self.assertIn("function render()", art)          # app code survived the skeleton strip
        self.assertNotIn("<!doctype", art.lower())


class BadManifest(unittest.TestCase):  # S10
    def test_wrong_field_types_do_not_crash(self):
        tmp = Path(tempfile.mkdtemp())
        write(tmp / "p" / ".claude-plugin" / "plugin.json",
              json.dumps({"name": ["bad"], "description": ["bad"], "author": 5, "repository": {"url": 3}}))
        write(tmp / "p" / "skills" / "x" / "SKILL.md", "---\nname: x\ndescription: d\n---\n")
        rc, _, data = run_main("--path", f"R={tmp}")
        self.assertEqual(rc, 0)
        self.assertEqual(len(data["skills"]), 1)


class FileLimits(unittest.TestCase):  # S4, S9
    def test_huge_skill_file_skipped(self):
        tmp = Path(tempfile.mkdtemp())
        write(tmp / "a" / "skills" / "big" / "SKILL.md", "---\nname: big\n---\n" + "x" * (skillscope.MAX_FILE_BYTES + 10))
        write(tmp / "a" / "skills" / "ok" / "SKILL.md", "---\nname: ok\ndescription: d\n---\n")
        rc, _, data = run_main("--path", f"R={tmp}")
        self.assertEqual([s["name"] for s in data["skills"]], ["ok"])

    @unittest.skipIf(os.name == "nt", "symlinks need admin rights on Windows")
    def test_symlink_outside_root_ignored(self):
        tmp = Path(tempfile.mkdtemp())
        secret = write(tmp / "secret.env", "API_KEY=abc123\n")
        d = tmp / "root" / "skills" / "x"
        d.mkdir(parents=True)
        os.symlink(secret, d / "SKILL.md")
        rc, _, data = run_main("--path", f"R={tmp / 'root'}")
        self.assertEqual(data["skills"], [])

    def test_inside_root_helper(self):
        root = Path(tempfile.mkdtemp())
        self.assertTrue(skillscope.inside(root / "a" / "b", root))
        self.assertFalse(skillscope.inside(root.parent / "elsewhere", root))


class Tokens(unittest.TestCase):  # S5
    def test_clean_token(self):
        self.assertEqual(skillscope.clean_token("  abc\n"), "abc")
        self.assertIsNone(skillscope.clean_token("ab\x00c"))
        self.assertIsNone(skillscope.clean_token("a b"))


class Schedule(unittest.TestCase):  # S3, S6
    def test_cron_rejects_newlines_and_bad_time(self):
        self.assertNotEqual(skillscope.validate_schedule("SUN", "21:00", ["--path", "R=/tmp/a\n* * * * * id"]), None)
        self.assertNotEqual(skillscope.validate_schedule("SUN", "25:00", []), None)
        self.assertNotEqual(skillscope.validate_schedule("XYZ", "21:00", []), None)
        self.assertIsNone(skillscope.validate_schedule("sun", "21:00", ["--path", "R=/tmp/a"]))

    def test_cron_percent_escaped(self):
        self.assertIn("\\%", skillscope.cron_escape("/tmp/50%done"))

    def test_trusted_exe_ignores_cwd(self):
        tmp = Path(tempfile.mkdtemp())
        write(tmp / ("gh.exe" if os.name == "nt" else "gh"), "fake")
        old = os.getcwd()
        os.chdir(tmp)
        try:
            found = skillscope.trusted_exe("gh")
            self.assertTrue(found is None or Path(found).parent != tmp)
        finally:
            os.chdir(old)


class LangCode(unittest.TestCase):  # S12
    def test_merge_rejects_path_like_lang(self):
        tmp = Path(tempfile.mkdtemp())
        f = write(tmp / "t.json", json.dumps({"k": "v"}))
        self.assertNotEqual(skillscope.merge_translations("../categories", f, tmp / "tr"), 0)
        self.assertEqual(skillscope.merge_translations("de", f, tmp / "tr"), 0)


class InstallCommand(unittest.TestCase):  # S1 (template JS)
    def test_install_cmd_uses_literal_quoting(self):
        tpl = (ROOT / "template.html").read_text(encoding="utf-8")
        self.assertIn("-LiteralPath", tpl)
        self.assertIn("psq(", tpl)
        self.assertIn("shq(", tpl)
        # inside a JS template literal the Windows separator must be written as \\ or it disappears
        self.assertIn("'.claude\\\\skills'", tpl)


if __name__ == "__main__":
    unittest.main()


class RegressionsRound2(unittest.TestCase):  # findings from the re-review
    def test_unicode_quotes_escaped_for_powershell(self):
        tpl = (ROOT / "template.html").read_text(encoding="utf-8")
        self.assertIn("[‘’‚‛']", tpl)

    def test_deep_manifest_does_not_crash(self):
        tmp = Path(tempfile.mkdtemp())
        write(tmp / "p" / ".claude-plugin" / "plugin.json", "[" * 5000 + "]" * 5000)
        write(tmp / "p" / "skills" / "x" / "SKILL.md", "---\nname: x\ndescription: d\n---\n")
        rc, _, data = run_main("--path", f"R={tmp}")
        self.assertEqual(rc, 0)
        self.assertEqual(len(data["skills"]), 1)

    def test_ipv6_url_kept_valid(self):
        self.assertEqual(skillscope.safe_url("https://[::1]:8443/repo.git"), "https://[::1]:8443/repo")

    def test_repo_report_not_deduped_and_old_slash_routes(self):
        tpl = (ROOT / "template.html").read_text(encoding="utf-8")
        self.assertIn("filtered(true)", tpl)            # repo report sees every copy
        self.assertIn("search(/[-/]/)", tpl)             # #catalog/docs still works


class RegressionsRound3(unittest.TestCase):
    def test_category_lookup_ignores_object_prototype(self):
        tpl = (ROOT / "template.html").read_text(encoding="utf-8")
        self.assertIn("const CAT=Object.create(null);", tpl)   # #catalog-constructor must not match
