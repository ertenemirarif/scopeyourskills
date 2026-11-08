#!/usr/bin/env python3
"""SkillScope: scan every agent skill (SKILL.md) on this machine, group the
skills by theme and find the ones that overlap.

Standard library only. Usage:

    python skillscope.py                         # auto-detect known locations
    python skillscope.py --path "Repos=D:/repos" # add folders (label=path)
    python skillscope.py --lang en --open        # English UI, open when done

Output: output/skillscope.html (single offline file) and output/skills.json
"""
from __future__ import annotations

import argparse
import base64
import hashlib
import html
import json
import math
import os
import re
import sys
import webbrowser
from collections import Counter, defaultdict
from datetime import datetime
from pathlib import Path

HERE = Path(__file__).resolve().parent
HOME = Path.home()

SKIP_DIRS = {
    "node_modules", ".git", ".venv", "venv", "__pycache__", ".tmp", "tmp",
    "scheduled-tasks", "dist", "build", ".next", ".trash", "site-packages", "fixtures",
}

# Platforms: skills only compete with each other when they load into the same tool.
PLATFORM_LABEL = {
    "claude": "Claude (Code + Desktop)",
    "claude-science": "Claude Science",
    "codex": "Codex",
    "gemini": "Gemini / Antigravity",
    "none": "-",
}


# --------------------------------------------------------------------------- #
# Sources
# --------------------------------------------------------------------------- #
def default_sources() -> list[dict]:
    """Known install locations. Missing ones are skipped silently."""
    local = Path(os.environ.get("LOCALAPPDATA", HOME / "AppData" / "Local"))
    roaming = Path(os.environ.get("APPDATA", HOME / "AppData" / "Roaming"))
    mac_support = HOME / "Library" / "Application Support"
    cands = [
        ("Claude Code: personal skills", HOME / ".claude" / "skills", "claude", True),
        ("Claude Code: plugins", HOME / ".claude" / "plugins", "claude", True),
        ("Claude Desktop: plugins", local / "Claude-Data", "claude", True),
        ("Claude Desktop: plugins", roaming / "Claude", "claude", True),
        ("Claude Desktop: plugins", mac_support / "Claude", "claude", True),
        ("Claude Science", HOME / ".claude-science", "claude-science", True),
        ("Codex: skills", HOME / ".codex" / "skills", "codex", True),
        ("Codex: plugins", HOME / ".codex" / "plugins", "codex", True),
        ("Gemini / Antigravity", HOME / ".gemini", "gemini", True),
        ("Agents (shared)", HOME / ".agents" / "skills", "codex", True),
    ]
    seen, out = set(), []
    for label, path, platform, active in cands:
        if path.is_dir() and str(path) not in seen:
            seen.add(str(path))
            out.append({"label": label, "path": path, "platform": platform, "active": active})
    return out


def iter_skill_files(root: Path):
    for dirpath, dirnames, filenames in os.walk(root):
        dirnames[:] = [d for d in dirnames if d not in SKIP_DIRS]
        for f in filenames:
            if f.lower() == "skill.md":
                yield Path(dirpath) / f


# --------------------------------------------------------------------------- #
# Parsing
# --------------------------------------------------------------------------- #
def parse_frontmatter(text: str) -> tuple[dict, str]:
    """Minimal YAML front-matter reader (top-level scalar keys only)."""
    text = text.lstrip("\ufeff")
    if not text.startswith("---"):
        return {}, text
    end = re.search(r"^---\s*$", text[3:], re.M)
    if not end:
        return {}, text
    block = text[3:3 + end.start()]
    body = text[3 + end.end():]
    meta: dict[str, str] = {}
    lines = block.splitlines()
    i = 0
    while i < len(lines):
        m = re.match(r"^([A-Za-z0-9_-]+):\s*(.*)$", lines[i])
        if not m:
            i += 1
            continue
        key, val = m.group(1), m.group(2).strip()
        if val in (">", ">-", ">+", "|", "|-", "|+", ""):
            folded = val.startswith(">") or val == ""
            parts = []
            i += 1
            while i < len(lines) and (lines[i].startswith((" ", "\t")) or not lines[i].strip()):
                parts.append(lines[i].strip())
                i += 1
            val = (" " if folded else "\n").join(p for p in parts if p)
            if key not in meta and val:
                meta[key] = val
            continue
        if len(val) >= 2 and val[0] == val[-1] and val[0] in "\"'":
            val = val[1:-1].replace('\\"', '"')
        meta.setdefault(key, val)
        i += 1
    return meta, body


def find_plugin(skill_path: Path, stop: Path) -> tuple[str | None, dict]:
    """Nearest .claude-plugin/plugin.json (or Codex plugin.json) above the skill: (name, manifest)."""
    for parent in skill_path.parents:
        for cand in (parent / ".claude-plugin" / "plugin.json", parent / ".codex-plugin" / "plugin.json"):
            if cand.is_file():
                try:
                    man = json.loads(cand.read_text(encoding="utf-8", errors="replace"))
                    man["_dir"] = str(parent)
                    return man.get("name"), man
                except Exception:
                    return None, {}
        if parent == stop or parent == parent.parent:
            break
    return None, {}


ACRONYMS = {"pdf", "ui", "ux", "seo", "api", "cli", "docx", "pptx", "xlsx", "csv", "mcp", "ci", "cd", "tdd", "rna",
            "qc", "sql", "llm", "ai", "gpt", "html", "css", "sdk", "prd", "kpi", "apk", "ssh", "pr", "ugc", "3d",
            "tts", "ocr", "faq", "cip", "esm2", "evo2", "gsap", "url", "x", "r"}
SPECIAL = {"openai": "OpenAI", "github": "GitHub", "youtube": "YouTube", "tiktok": "TikTok", "linkedin": "LinkedIn",
           "chatgpt": "ChatGPT", "ffmpeg": "FFmpeg", "pubmed": "PubMed", "notebooklm": "NotebookLM", "seedance": "Seedance",
           "javascript": "JavaScript", "typescript": "TypeScript", "nextjs": "Next.js", "imrad": "IMRaD"}
SMALL = {"and", "or", "to", "of", "in", "for", "the", "a", "with", "on", "by", "vs"}


def humanize(slug: str) -> str:
    """'instrument-data-to-allotrope' -> 'Instrument Data to Allotrope'."""
    words = re.split(r"[-_\s]+", slug.strip())
    out = []
    for i, w in enumerate(words):
        lw = w.lower()
        if lw in SPECIAL:
            out.append(SPECIAL[lw])
        elif lw in ACRONYMS:
            out.append(w.upper())
        elif i and lw in SMALL:
            out.append(lw)
        elif w[:1].islower():
            out.append(w[:1].upper() + w[1:])
        else:
            out.append(w)
    return " ".join(out)


def git_remote(repo_dir: Path) -> str | None:
    cfg = repo_dir / ".git" / "config"
    try:
        m = re.search(r"url\s*=\s*(\S+)", cfg.read_text(encoding="utf-8", errors="replace"))
    except OSError:
        return None
    if not m:
        return None
    url = m.group(1)
    url = re.sub(r"^git@github\.com:", "https://github.com/", url)
    return re.sub(r"\.git$", "", url)


LICENSE_RULES = [
    ("MIT", r"\bMIT License\b|Permission is hereby granted, free of charge"),
    ("Apache-2.0", r"Apache License,?\s+Version 2\.0"),
    ("AGPL-3.0", r"GNU AFFERO GENERAL PUBLIC LICENSE"),
    ("LGPL", r"GNU LESSER GENERAL PUBLIC LICENSE"),
    ("GPL-3.0", r"GNU GENERAL PUBLIC LICENSE\s+Version 3"),
    ("GPL-2.0", r"GNU GENERAL PUBLIC LICENSE\s+Version 2"),
    ("MPL-2.0", r"Mozilla Public License,?\s+(v\.\s*|Version\s+)2\.0"),
    ("BSD-3-Clause", r"Redistribution and use in source and binary forms.*?Neither the name"),
    ("BSD-2-Clause", r"Redistribution and use in source and binary forms"),
    ("ISC", r"\bISC License\b|Permission to use, copy, modify, and/or distribute"),
    ("Unlicense", r"This is free and unencumbered software released into the public domain"),
    ("CC-BY-4.0", r"Creative Commons Attribution 4\.0"),
    ("CC0-1.0", r"CC0 1\.0"),
]


def detect_license(folder: str | Path | None) -> str:
    """SPDX-like id from a LICENSE/COPYING file in the folder ('' if none, 'Other' if unknown)."""
    if not folder:
        return ""
    folder = Path(folder)
    try:
        files = [f for f in folder.iterdir() if f.is_file() and re.match(r"(LICEN[CS]E|COPYING)", f.name, re.I)]
    except OSError:
        return ""
    for f in files:
        try:
            text = f.read_text(encoding="utf-8", errors="replace")[:6000]
        except OSError:
            continue
        for spdx, pat in LICENSE_RULES:
            if re.search(pat, text, re.I | re.S):
                return spdx
        return "Other"
    return ""


def github_slug(url: str) -> str | None:
    m = re.match(r"https?://github\.com/([^/\s]+)/([^/\s#?]+)", url or "")
    if not m:
        return None
    return m.group(1) + "/" + re.sub(r"\.git$", "", m.group(2))


def github_token() -> str | None:
    tok = os.environ.get("GITHUB_TOKEN") or os.environ.get("GH_TOKEN")
    if tok:
        return tok
    try:  # reuse an existing `gh` login if there is one
        import subprocess
        r = subprocess.run(["gh", "auth", "token"], capture_output=True, text=True, timeout=10)
        return r.stdout.strip() or None
    except Exception:
        return None


def enrich_github(packages: dict, cache_file: Path, ttl_hours: float = 24) -> None:
    """Add stars / license / last push from the GitHub API to packages that link to a GitHub repo."""
    import time
    import urllib.error
    import urllib.request
    cache = load_cache(cache_file)
    now = time.time()
    slugs = sorted({github_slug(p.get("url", "")) for p in packages.values()} - {None})
    todo = [sl for sl in slugs if now - cache.get(sl, {}).get("_at", 0) > ttl_hours * 3600]
    token = github_token() if todo else None
    for sl in todo:
        req = urllib.request.Request(f"https://api.github.com/repos/{sl}",
                                     headers={"Accept": "application/vnd.github+json", "User-Agent": "skillscope"})
        if token:
            req.add_header("Authorization", f"Bearer {token}")
        try:
            with urllib.request.urlopen(req, timeout=20) as r:
                d = json.loads(r.read())
            lic = (d.get("license") or {}).get("spdx_id") or ""
            cache[sl] = {"_at": now, "stars": d.get("stargazers_count"), "license": "" if lic == "NOASSERTION" else lic,
                         "license_raw": lic, "pushed": (d.get("pushed_at") or "")[:10], "archived": d.get("archived", False),
                         "full_name": d.get("full_name", sl)}
        except urllib.error.HTTPError as e:
            if e.code == 403:
                print("! GitHub rate limit reached; set GITHUB_TOKEN or log in with `gh auth login`", file=sys.stderr)
                break
            cache[sl] = {"_at": now, "missing": True}  # private, renamed or deleted
        except Exception as e:
            print(f"! GitHub lookup failed for {sl}: {e}", file=sys.stderr)
            break
    cache_file.parent.mkdir(parents=True, exist_ok=True)
    cache_file.write_text(json.dumps(cache, ensure_ascii=False, indent=1), encoding="utf-8")
    for p in packages.values():
        g = cache.get(github_slug(p.get("url", "")) or "", {})
        if g and not g.get("missing"):
            p["stars"] = g.get("stars")
            p["pushed"] = g.get("pushed", "")
            p["archived"] = g.get("archived", False)
            p["gh_license"] = g.get("license", "")
            if not p.get("license") and g.get("license"):
                p["license"] = g["license"]
                p["license_src"] = "github"
    print(f"github: {sum(1 for p in packages.values() if p.get('stars') is not None)} packages with stars "
          f"({len(todo)} fetched, rest from cache)")


def package_info(f: Path, root: Path, src: dict, plugin: str | None, man: dict) -> tuple[str, dict]:
    """Group key + display info for the package a skill came from."""
    if plugin:
        author = man.get("author")
        author = author.get("name") if isinstance(author, dict) else author
        url = man.get("repository") or man.get("homepage")
        url = url.get("url") if isinstance(url, dict) else url
        lic = detect_license(man.get("_dir"))
        declared = man.get("license") if isinstance(man.get("license"), str) else ""
        return "plugin:" + plugin, {"title": man.get("displayName") or humanize(plugin), "id": plugin,
                                    "description": man.get("description") or "", "author": author or "",
                                    "url": url or "", "kind": "plugin",
                                    "license": lic if lic and lic != "Other" else (declared or lic),
                                    "license_src": "file" if lic else ("manifest" if declared else "")}
    if not src["active"]:
        try:
            rel = f.relative_to(root)
            repo_dir = root / rel.parts[0] if len(rel.parts) > 2 else root
        except ValueError:
            repo_dir = root
        url = git_remote(repo_dir) or ""
        owner = url.rstrip("/").split("/")[-2] if url.count("/") >= 4 else ""
        lic = detect_license(repo_dir)
        return "repo:" + str(repo_dir), {"title": humanize(repo_dir.name), "id": repo_dir.name, "description": "",
                                         "author": owner, "url": url, "kind": "repo",
                                         "license": lic, "license_src": "file" if lic else ""}
    return "loc:" + str(root), {"title": src["label"], "id": root.name, "description": "", "author": "",
                                "url": "", "kind": "local"}


def repo_name(skill_path: Path, root: Path) -> str:
    """First folder under the source root, used as the 'repo' for downloaded folders."""
    try:
        rel = skill_path.relative_to(root)
        return rel.parts[0] if len(rel.parts) > 2 else root.name
    except ValueError:
        return root.name


# --------------------------------------------------------------------------- #
# Categorisation
# --------------------------------------------------------------------------- #
WORD = r"[0-9a-zçğıöşüâîû]"


def compile_categories(cfg: dict) -> list[dict]:
    cats = []
    for c in cfg["categories"]:
        pats = []
        for kw in c["keywords"]:
            k = re.escape(kw.lower())
            tail = rf"(?!{WORD})" if len(kw) <= 3 else ""
            pats.append(re.compile(rf"(?<!{WORD}){k}{tail}"))
        cats.append({**c, "patterns": pats})
    return cats


def tr_lower(s: str) -> str:
    return s.replace("I", "ı").replace("İ", "i").lower()


def categorize(name: str, desc: str, cats: list[dict]) -> tuple[str, list[str], dict]:
    n = tr_lower(name.replace("-", " ").replace("_", " "))
    d = tr_lower(desc)
    scores = {}
    for c in cats:
        s = 0
        for p in c["patterns"]:
            s += 3 * len(p.findall(n)) + min(len(p.findall(d)), 3)
        if s:
            scores[c["id"]] = s
    if not scores:
        return "other", [], {}
    best = max(scores, key=scores.get)
    secondary = [k for k, v in sorted(scores.items(), key=lambda x: -x[1])
                 if k != best and v >= max(2, scores[best] * 0.5)][:2]
    return best, secondary, scores


# --------------------------------------------------------------------------- #
# Similarity (TF-IDF over name + description)
# --------------------------------------------------------------------------- #
STOP = set("""
a an the and or of to in on for with by from at as is are be been this that these those it its into
use used using when whenever user users want wants asks ask says say any all also can may should must
not no do does via your you their them they then than such other more most only just like e g i e eg
skill skills claude code agent agents trigger triggers activate including include includes etc new
help helps make makes create creates build builds based about over across each per one two three
ve ile bir bu şu için gibi da de olarak kullan kullanıcı dediğinde ya veya ise ama çok her hem
""".split())
TOKEN_RE = re.compile(r"[a-zçğıöşü0-9][a-zçğıöşü0-9+#.-]*[a-zçğıöşü0-9+#]|[a-zçğıöşü]")


def tokens(text: str) -> list[str]:
    out = []
    for t in TOKEN_RE.findall(tr_lower(text)):
        if len(t) < 3 or t in STOP or t.isdigit():
            continue
        if len(t) > 4 and t.endswith("s") and not t.endswith("ss"):
            t = t[:-1]  # crude plural folding
        out.append(t)
    return out


def tfidf(docs: list[list[str]]) -> list[dict]:
    df = Counter()
    for d in docs:
        df.update(set(d))
    n = len(docs)
    common = max(2, n * 0.25)  # terms in more than a quarter of all skills say nothing
    vecs = []
    for d in docs:
        tf = Counter(d)
        v = {t: (1 + math.log(c)) * math.log((n + 1) / (df[t] + 1)) for t, c in tf.items() if df[t] <= common}
        norm = math.sqrt(sum(x * x for x in v.values())) or 1.0
        vecs.append({t: x / norm for t, x in v.items()})
    return vecs


def cosine(a: dict, b: dict) -> float:
    if len(a) > len(b):
        a, b = b, a
    return sum(x * b.get(t, 0.0) for t, x in a.items())


# --------------------------------------------------------------------------- #
# Main pipeline
# --------------------------------------------------------------------------- #
def scan(sources: list[dict], cats: list[dict]) -> tuple[list[dict], dict]:
    skills, seen_paths, packages = [], set(), {}
    for src in sources:
        root = Path(src["path"])
        for f in iter_skill_files(root):
            real = os.path.realpath(f)
            if real in seen_paths:
                continue
            seen_paths.add(real)
            try:
                raw = f.read_text(encoding="utf-8", errors="replace")
            except OSError:
                continue
            meta, body = parse_frontmatter(raw)
            name = (meta.get("name") or f.parent.name).strip()
            desc = re.sub(r"\s+", " ", meta.get("description", "")).strip()
            if not desc:  # fall back to the first prose line
                for line in body.splitlines():
                    line = line.strip()
                    if line and not line.startswith(("#", "```", "<", "|", "-", "!")):
                        desc = line[:300]
                        break
            plugin, man = find_plugin(f, root)
            pkg, info = package_info(f, root, src, plugin, man)
            packages.setdefault(pkg, info)
            norm_body = re.sub(r"\s+", " ", raw).strip()
            primary, secondary, scores = categorize(name, desc, cats)
            skills.append({
                "id": len(skills),
                "name": name,
                "plugin": plugin,
                "full": f"{plugin}:{name}" if plugin else name,
                "title": meta.get("title") or humanize(name),
                "pkg": pkg,
                "description": desc,
                "path": str(f.parent),
                "source": src["label"],
                # installed loose skills: name the location; downloaded folders: name the repo
                "repo": plugin or (root.name if src["active"] else repo_name(f, root)),
                "platform": src["platform"],
                "active": src["active"],
                "category": primary,
                "secondary": secondary,
                "scores": scores,
                "hash": hashlib.sha1(norm_body.encode("utf-8", "replace")).hexdigest()[:12],
                "size": len(raw),
            })
    return skills, packages


def find_overlaps(skills: list[dict], threshold: float, sibling_extra: float = 0.13) -> dict:
    # 1) Exact copies: identical SKILL.md content in several places.
    by_hash = defaultdict(list)
    for s in skills:
        by_hash[s["hash"]].append(s["id"])
    copies = [ids for ids in by_hash.values() if len(ids) > 1]

    # 2) Same name, different content: competing versions of one skill.
    by_name = defaultdict(set)
    for s in skills:
        by_name[s["name"].lower()].add(s["hash"])
    versions = []
    for name, hashes in by_name.items():
        if len(hashes) > 1:
            groups = [[s["id"] for s in skills if s["hash"] == h] for h in sorted(hashes)]
            # live: two different variants are loaded by the same tool
            plats = [{skills[i]["platform"] for i in g if skills[i]["active"]} for g in groups]
            live = sorted({p for x in range(len(plats)) for y in range(x + 1, len(plats))
                           for p in plats[x] & plats[y]})
            versions.append({"name": name, "variants": groups, "live": live})
    versions.sort(key=lambda v: (not v["live"], v["name"]))

    # 3) Functional overlap: different skills whose name+description say the same
    #    thing, so they compete for the same requests. One representative per hash.
    reps, rep_of = [], {}
    for ids in by_hash.values():
        rep = ids[0]
        reps.append(rep)
        for i in ids:
            rep_of[i] = rep
    docs = [tokens(skills[r]["name"].replace("-", " ") + " " + skills[r]["description"]) for r in reps]
    vecs = tfidf(docs)
    index = defaultdict(set)  # inverted index keeps the pair loop small
    for k, v in enumerate(vecs):
        for t in v:
            index[t].add(k)
    pairs = []
    for a in range(len(reps)):
        cand = set()
        for t in vecs[a]:
            cand |= index[t]
        for b in cand:
            if b <= a:
                continue
            sa, sb = skills[reps[a]], skills[reps[b]]
            if sa["name"].lower() == sb["name"].lower():
                continue  # already reported as versions
            same_repo = sa["repo"] == sb["repo"]
            sim = cosine(vecs[a], vecs[b])
            # Siblings in one repo share vocabulary by design; ask more of them.
            if sim < (threshold + sibling_extra if same_repo else threshold):
                continue
            shared = sorted(set(vecs[a]) & set(vecs[b]), key=lambda t: -(vecs[a][t] * vecs[b][t]))[:6]
            ga = [i for i in by_hash[sa["hash"]]]
            gb = [i for i in by_hash[sb["hash"]]]
            plat_a = {skills[i]["platform"] for i in ga if skills[i]["active"]}
            plat_b = {skills[i]["platform"] for i in gb if skills[i]["active"]}
            live = sorted(plat_a & plat_b)
            pairs.append({
                "a": reps[a], "b": reps[b], "sim": round(sim, 3), "shared": shared,
                "live": live, "same_repo": same_repo,
            })
    pairs.sort(key=lambda p: (-bool(p["live"]), p["same_repo"], -p["sim"]))
    return {"copies": copies, "versions": versions, "pairs": pairs}


def mark_installed(skills: list[dict]) -> None:
    """For downloaded (inactive) skills: is the same skill already installed somewhere?"""
    active_hash = {s["hash"] for s in skills if s["active"]}
    active_name = {s["name"].lower() for s in skills if s["active"]}
    for s in skills:
        if s["active"]:
            s["installed"] = "yes"
        elif s["hash"] in active_hash:
            s["installed"] = "same"
        elif s["name"].lower() in active_name:
            s["installed"] = "other-version"
        else:
            s["installed"] = "no"


# --------------------------------------------------------------------------- #
# Translations (description in the reader's language)
# --------------------------------------------------------------------------- #
TR_WORDS = {"ve", "ile", "bir", "için", "bu", "olarak", "kullan", "dediğinde", "gibi", "veya", "ya"}
EN_WORDS = {"the", "and", "use", "when", "with", "for", "this", "user", "to", "of"}


LANG_NAMES = {"tr": "Turkish", "en": "English", "zh": "Simplified Chinese", "es": "Spanish", "de": "German",
              "fr": "French", "ar": "Arabic", "ru": "Russian", "ja": "Japanese", "pt": "Portuguese", "it": "Italian"}
ES_WORDS = {"el", "la", "los", "las", "para", "con", "que", "una", "del", "cuando", "usa", "usar"}


def guess_lang(text: str) -> str:
    if len(re.findall(r"[一-鿿]", text)) >= 4:
        return "zh"
    words = re.findall(r"\w+", tr_lower(text))
    es = sum(w in ES_WORDS for w in words) + 2 * len(re.findall(r"[ñ¿¡]", text))
    if es >= 4 and es > sum(w in EN_WORDS for w in words):
        return "es"
    tr = sum(w in TR_WORDS for w in words) + 2 * len(re.findall(r"[ğışĞİŞ]", text))
    en = sum(w in EN_WORDS for w in words)
    if tr >= 2 and tr >= en:
        return "tr"
    return "en" if en else "?"


def desc_key(text: str) -> str:
    return hashlib.sha1(text.encode("utf-8")).hexdigest()[:12]


def load_cache(path: Path) -> dict:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}


def translate_with_claude(items: dict, lang: str, model: str) -> dict:
    """Fill missing translations with the Claude API (needs ANTHROPIC_API_KEY). stdlib only."""
    import urllib.request
    key = os.environ.get("ANTHROPIC_API_KEY")
    if not key:
        print("! --translate needs ANTHROPIC_API_KEY; skipping", file=sys.stderr)
        return {}
    target = LANG_NAMES.get(lang, lang)
    out, keys = {}, list(items)
    for i in range(0, len(keys), 40):
        batch = {k: items[k] for k in keys[i:i + 40]}
        prompt = (f"Translate each value of this JSON object into natural, concise {target}. "
                  "Keep skill names, product names, file types and quoted trigger phrases readable; "
                  "do not add anything. Reply with only the JSON object, same keys.\n\n"
                  + json.dumps(batch, ensure_ascii=False))
        req = urllib.request.Request(
            "https://api.anthropic.com/v1/messages",
            data=json.dumps({"model": model, "max_tokens": 16000,
                             "messages": [{"role": "user", "content": prompt}]}).encode(),
            headers={"x-api-key": key, "anthropic-version": "2023-06-01", "content-type": "application/json"})
        try:
            with urllib.request.urlopen(req, timeout=300) as r:
                text = json.loads(r.read())["content"][0]["text"]
            got = json.loads(text[text.find("{"):text.rfind("}") + 1])
            out.update({k: v for k, v in got.items() if k in batch and isinstance(v, str)})
            print(f"  translated {min(i + 40, len(keys))}/{len(keys)}")
        except Exception as e:  # keep what we have; the rest stays untranslated
            print(f"! translation batch failed: {e}", file=sys.stderr)
    return out


def merge_translations(lang: str, src: Path, folder: Path) -> int:
    """Merge a {key: text} file (e.g. translated by Claude) into translations/<lang>.json."""
    new = json.loads(src.read_text(encoding="utf-8"))
    bad = [k for k, v in new.items() if not isinstance(v, str) or not v.strip()]
    target = folder / f"{lang}.json"
    cache = load_cache(target)
    cache.update({k: v.strip() for k, v in new.items() if k not in bad})
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(json.dumps(cache, ensure_ascii=False, indent=1), encoding="utf-8")
    print(f"merged {len(new) - len(bad)} translations into {target} ({len(cache)} total; skipped {len(bad)} empty)")
    return 0


TASK_NAME = "SkillScope weekly"


def setup_schedule(mode: str, argv: list[str], day: str, time_: str) -> int:
    """Register (or remove) a weekly OS task that re-runs this exact command without --open."""
    import shlex
    import subprocess
    keep, skip = [], 0
    for a in argv:
        if skip:
            skip -= 1
            continue
        if a in ("--schedule", "--schedule-day", "--schedule-time"):
            skip = 1
            continue
        if a.startswith(("--schedule", "--open", "--merge", "--export-missing")):
            continue
        keep.append(a)
    cmd = [sys.executable, str(Path(__file__).resolve())] + keep
    if os.name == "nt":
        if mode == "off":
            r = subprocess.run(["schtasks", "/Delete", "/TN", TASK_NAME, "/F"], capture_output=True, text=True)
        else:
            tr = subprocess.list2cmdline(cmd)
            r = subprocess.run(["schtasks", "/Create", "/TN", TASK_NAME, "/SC", "WEEKLY", "/D", day[:3].upper(),
                                "/ST", time_, "/TR", tr, "/F"], capture_output=True, text=True)
        print((r.stdout or r.stderr).strip())
        return r.returncode
    line = f"{time_[3:5]} {time_[:2]} * * {day[:3].lower()} " + " ".join(shlex.quote(c) for c in cmd) + f"  # {TASK_NAME}"
    if mode == "off":
        print(f"Remove the line ending with '# {TASK_NAME}' from `crontab -e`.")
    else:
        print("Add this line with `crontab -e` (macOS/Linux):\n" + line)
    return 0


def render(data: dict, lang: str) -> str:
    tpl = (HERE / "template.html").read_text(encoding="utf-8")
    payload = json.dumps(data, ensure_ascii=False).replace("</", "<\\/")
    logo = HERE / "assets" / "logo.webp"
    logo_uri = "data:image/webp;base64," + base64.b64encode(logo.read_bytes()).decode() if logo.is_file() else ""
    anim = HERE / "assets" / "logo-96.gif"
    anim_uri = "data:image/gif;base64," + base64.b64encode(anim.read_bytes()).decode() if anim.is_file() else logo_uri
    tpl = tpl.replace("__LOGO_ANIM__", anim_uri).replace("__LOGO__", logo_uri)
    return tpl.replace("__LANG__", html.escape(lang)).replace("/*__DATA__*/null", payload)


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="Map, categorise and de-duplicate your agent skills.")
    ap.add_argument("--path", action="append", default=[], metavar="LABEL=DIR",
                    help="extra folder to scan, e.g. 'Downloaded repos=D:/repos' (repeatable). "
                         "These count as downloaded, not installed.")
    ap.add_argument("--active-path", action="append", default=[], metavar="LABEL=DIR",
                    help="extra folder whose skills are loaded by Claude (e.g. a project's .claude/skills).")
    ap.add_argument("--no-defaults", action="store_true", help="skip auto-detected locations")
    ap.add_argument("--categories", default=str(HERE / "categories.json"))
    ap.add_argument("--threshold", type=float, default=0.25,
                    help="similarity cut-off for overlaps, 0-1 (skills from the same repo need +0.13)")
    ap.add_argument("--lang", default="tr", help="default dashboard language (tr, en, zh, es or any ISO code)")
    ap.add_argument("--langs", default="tr,en,zh,es",
                    help="comma-separated languages to prepare description translations for")
    ap.add_argument("--merge", nargs=2, metavar=("LANG", "FILE"),
                    help="merge a translated {key: text} JSON file into translations/LANG.json and exit")
    ap.add_argument("--out", default=str(HERE / "output"))
    ap.add_argument("--open", action="store_true", help="open the dashboard when done")
    ap.add_argument("--translations", default=str(HERE / "translations"),
                    help="folder with <lang>.json description translations (cache)")
    ap.add_argument("--translate", action="store_true",
                    help="translate missing descriptions into --lang with the Claude API (ANTHROPIC_API_KEY)")
    ap.add_argument("--model", default="claude-haiku-5-5", help="model for --translate")
    ap.add_argument("--github", action="store_true",
                    help="fetch stars and license of linked GitHub repos (uses GITHUB_TOKEN or `gh auth token`; cached 24h)")
    ap.add_argument("--schedule", choices=["weekly", "off"],
                    help="register a weekly OS task (Windows Task Scheduler; prints a cron line elsewhere) "
                         "that re-runs this same command, or remove it")
    ap.add_argument("--schedule-day", default="SUN", help="day for --schedule weekly (MON..SUN)")
    ap.add_argument("--schedule-time", default="21:00", help="time for --schedule weekly (HH:MM)")
    ap.add_argument("--export-missing", metavar="DIR",
                    help="write untranslated descriptions to DIR/missing-<lang>.json ({key: text}) for any translator")
    args = ap.parse_args(argv)
    if args.schedule:
        return setup_schedule(args.schedule, list(sys.argv[1:] if argv is None else argv),
                              args.schedule_day, args.schedule_time)
    if args.merge:
        return merge_translations(args.merge[0], Path(args.merge[1]), Path(args.translations))

    sources = [] if args.no_defaults else default_sources()
    for spec, active in [(p, False) for p in args.path] + [(p, True) for p in args.active_path]:
        label, _, path = spec.partition("=") if "=" in spec else (Path(spec).name, "", spec)
        p = Path(path).expanduser()
        if not p.is_dir():
            print(f"! not a folder: {p}", file=sys.stderr)
            continue
        sources.append({"label": label, "path": p, "platform": "claude" if active else "none", "active": active})
    if not sources:
        print("No folders to scan. Use --path LABEL=DIR.", file=sys.stderr)
        return 1

    cfg = json.loads(Path(args.categories).read_text(encoding="utf-8"))
    cats = compile_categories(cfg)
    skills, packages = scan(sources, cats)
    if args.github:
        enrich_github(packages, HERE / "cache" / "github.json")
    mark_installed(skills)
    overlaps = find_overlaps(skills, args.threshold)

    # descriptions in every dashboard language (cache: translations/<lang>.json)
    langs = list(dict.fromkeys([args.lang] + [l.strip() for l in args.langs.split(",") if l.strip()]))
    for s in skills:
        s["desc_key"] = desc_key(s["description"])
        s["desc_lang"] = guess_lang(s["description"])
    for info in packages.values():  # package descriptions follow the same toggle
        info["desc_key"] = desc_key(info["description"])
        info["desc_lang"] = guess_lang(info["description"])
    items = {}
    for x in list(skills) + list(packages.values()):
        if x["description"]:
            items.setdefault(x["desc_key"], (x["description"], x["desc_lang"]))
    translations, still_missing = {}, {}
    for lang in langs:
        cache_file = Path(args.translations) / f"{lang}.json"
        cache = load_cache(cache_file)
        missing = {k: t for k, (t, src) in items.items() if src != lang and k not in cache}
        if args.translate and missing:
            print(f"translating {len(missing)} descriptions into {lang}...")
            cache.update(translate_with_claude(missing, lang, args.model))
            cache_file.parent.mkdir(parents=True, exist_ok=True)
            cache_file.write_text(json.dumps(cache, ensure_ascii=False, indent=1), encoding="utf-8")
            missing = {k: v for k, v in missing.items() if k not in cache}
        if args.export_missing and missing:
            out_dir = Path(args.export_missing)
            out_dir.mkdir(parents=True, exist_ok=True)
            (out_dir / f"missing-{lang}.json").write_text(json.dumps(missing, ensure_ascii=False, indent=1), encoding="utf-8")
        still_missing[lang] = len(missing)
        translations[lang] = {k: v for k, v in cache.items() if k in items}
    print("translations missing: " + ", ".join(f"{l}={n}" for l, n in still_missing.items()))
    if args.export_missing:
        print(f"-> untranslated descriptions written to {args.export_missing}/missing-<lang>.json")

    data = {
        "lang": args.lang,
        "translations": translations,
        "missing": still_missing,
        "generated": datetime.now().strftime("%Y-%m-%d %H:%M"),
        "threshold": args.threshold,
        "sources": [{"label": s["label"], "path": str(s["path"]), "platform": s["platform"],
                     "active": s["active"]} for s in sources],
        "platforms": PLATFORM_LABEL,
        "categories": [{"id": c["id"], "label": c["label"], "color": c["color"]} for c in cfg["categories"]]
                      + [{"id": "other", "label": {"tr": "Diğer / Sınıflanamayan", "en": "Other / Unclassified",
                                                     "zh": "其他 / 未分类", "es": "Otros / Sin clasificar"},
                          "color": "#a4b0be"}],
        "packages": packages,
        "skills": skills,
        "overlaps": overlaps,
    }
    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)
    (out / "skills.json").write_text(json.dumps(data, ensure_ascii=False, indent=1), encoding="utf-8")
    page = out / "skillscope.html"
    full = render(data, args.lang)
    page.write_text(full, encoding="utf-8")
    # Claude artifact variant: claude.ai adds its own document skeleton, so drop ours
    frag = re.sub(r'(?is)<!doctype[^>]*>|</?html[^>]*>|</?head>|</?body>|<meta charset[^>]*>|<meta name="viewport"[^>]*>',
                  "", full)
    (out / "skillscope.artifact.html").write_text(frag.strip() + "\n", encoding="utf-8")

    uniq = len({s["hash"] for s in skills})
    live = sum(1 for p in overlaps["pairs"] if p["live"])
    print(f"{len(skills)} SKILL.md files ({uniq} unique) from {len(sources)} sources")
    print(f"overlaps: {live} live / {len(overlaps['pairs'])} functional pairs, "
          f"{len(overlaps['versions'])} name clashes, {len(overlaps['copies'])} copy groups")
    print(f"-> {page}")
    if args.open:
        webbrowser.open(page.as_uri())
    return 0


if __name__ == "__main__":
    sys.exit(main())
