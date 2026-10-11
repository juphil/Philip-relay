"""Fail a Philip Relay public release when manifests, docs, or privacy boundaries drift."""

from __future__ import annotations

import json
import hashlib
import re
import subprocess
import sys
from collections import defaultdict
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
PLUGIN = ROOT / "plugins" / "philip"
TEXT_SUFFIXES = {".md", ".json", ".py", ".template", ".txt", ".yml", ".yaml", ".html", ".css", ".js", ".bat"}
REQUIRED = {
    "README.md",
    "README.ko.md",
    "LICENSE",
    "NOTICE",
    "VERSION",
    ".claude-plugin/marketplace.json",
    ".agents/plugins/marketplace.json",
    "plugins/philip/plugin.json",
    "plugins/philip/.claude-plugin/plugin.json",
    "plugins/philip/.codex-plugin/plugin.json",
}
SENSITIVE_NAMES = {".env", "id_rsa", "id_ed25519", "credentials.json", "secrets.json"}
SECRET_PATTERNS = {
    "private key": re.compile(r"-----BEGIN (?:RSA |EC |OPENSSH )?PRIVATE KEY-----"),
    "GitHub token": re.compile(r"\b(?:gh[pousr]_[A-Za-z0-9_]{20,}|github_pat_[A-Za-z0-9_]{20,})\b"),
    "OpenAI token": re.compile(r"\bsk-[A-Za-z0-9_-]{20,}\b"),
    "AWS access key": re.compile(r"\bAKIA[0-9A-Z]{16}\b"),
    "Slack token": re.compile(r"\bxox[baprs]-[A-Za-z0-9-]{20,}\b"),
}


def load_json(rel: str) -> dict:
    return json.loads((ROOT / rel).read_text(encoding="utf-8-sig"))


def repository_files() -> list[str]:
    result = subprocess.run(
        ["git", "ls-files", "--cached", "--others", "--exclude-standard", "-z"],
        cwd=ROOT,
        capture_output=True,
        text=True,
        encoding="utf-8",
    )
    if result.returncode:
        raise RuntimeError(result.stderr.strip() or "git ls-files failed")
    return sorted(item for item in result.stdout.split("\0") if item)


def local_links(path: Path):
    text = path.read_text(encoding="utf-8-sig")
    for raw in re.findall(r"\]\(([^)]+)\)", text):
        target = raw.split("#", 1)[0].strip()
        if not target or target == "파일.md" or target.startswith(("http://", "https://", "mailto:", "/", "#")):
            continue
        yield raw, (path.parent / target).resolve()


def main() -> int:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    errors: list[str] = []

    for rel in sorted(REQUIRED):
        if not (ROOT / rel).is_file():
            errors.append(f"필수 파일 없음: {rel}")

    version_match = re.match(r"v(\d+\.\d+\.\d+)", (ROOT / "VERSION").read_text(encoding="utf-8-sig"))
    version = version_match.group(1) if version_match else ""
    manifests = [
        load_json("plugins/philip/plugin.json"),
        load_json("plugins/philip/.claude-plugin/plugin.json"),
        load_json("plugins/philip/.codex-plugin/plugin.json"),
    ]
    marketplace = load_json(".claude-plugin/marketplace.json")
    market_plugin = next((item for item in marketplace.get("plugins", []) if item.get("name") == "philip"), {})
    versions = [item.get("version", "") for item in manifests] + [market_plugin.get("version", ""), version]
    if not version or len(set(versions)) != 1:
        errors.append(f"버전 표기 불일치: {versions}")
    if any(item.get("name") != "philip" for item in manifests):
        errors.append("플러그인 매니페스트 name은 모두 philip이어야 합니다.")
    if marketplace.get("name") != "philip-relay":
        errors.append("Claude marketplace name은 philip-relay여야 합니다.")

    agent_marketplace = load_json(".agents/plugins/marketplace.json")
    agent_plugins = agent_marketplace.get("plugins", [])
    if agent_marketplace.get("name") != "philip-relay" or not any(p.get("name") == "philip" for p in agent_plugins):
        errors.append("Codex marketplace의 philip-relay/philip 식별자가 올바르지 않습니다.")

    readme = (ROOT / "README.md").read_text(encoding="utf-8-sig")
    readme_ko = (ROOT / "README.ko.md").read_text(encoding="utf-8-sig") if (ROOT / "README.ko.md").is_file() else ""
    if "README.ko.md" not in readme or "README.md" not in readme_ko:
        errors.append("영어 README.md와 한국어 README.ko.md는 서로 링크해야 합니다.")

    tag = f"v{version}" if version else ""
    tag_list = subprocess.run(["git", "tag", "--list", tag], cwd=ROOT, capture_output=True, text=True, encoding="utf-8")
    if not tag or not tag_list.stdout.strip():
        errors.append(f"현재 버전 태그 없음: {tag or 'VERSION 해석 실패'}")
    else:
        head = subprocess.run(["git", "rev-parse", "HEAD"], cwd=ROOT, capture_output=True, text=True, encoding="utf-8").stdout.strip()
        tagged = subprocess.run(["git", "rev-list", "-n", "1", tag], cwd=ROOT, capture_output=True, text=True, encoding="utf-8").stdout.strip()
        if head and tagged and head != tagged:
            errors.append(f"현재 버전 태그 {tag}가 HEAD를 가리키지 않습니다.")

    skill_names = sorted(path.parent.name for path in (PLUGIN / "skills").glob("*/SKILL.md"))
    procedure_names = sorted(path.stem for path in (PLUGIN / "procedures").glob("*.md"))
    if skill_names != procedure_names:
        errors.append("procedure와 생성된 skill 목록이 다릅니다.")

    try:
        files = repository_files()
    except RuntimeError as exc:
        errors.append(str(exc))
        files = []
    inbound: defaultdict[Path, int] = defaultdict(int)
    hashes: defaultdict[str, list[str]] = defaultdict(list)
    for rel in files:
        path = ROOT / rel
        if not path.is_file():
            continue
        if path.name.lower() in SENSITIVE_NAMES or path.suffix.lower() in {".pem", ".key", ".p12", ".pfx"}:
            errors.append(f"민감 파일 후보: {rel}")
        if path.suffix.lower() not in TEXT_SUFFIXES and path.name not in {"LICENSE", "NOTICE", "VERSION"}:
            continue
        try:
            text = path.read_text(encoding="utf-8-sig")
        except UnicodeDecodeError:
            errors.append(f"텍스트 파일 UTF-8 해석 실패: {rel}")
            continue
        if re.search(r"(?i)[A-Z]:[\\/]Users[\\/](?!<|user(?:name)?\b|a\b|test\b)[^\\/\s]+", text):
            errors.append(f"개인 Windows 절대경로 발견: {rel}")
        if re.search(r"(?i)(?:^|[\s`'\"])/(?:home|Users)/(?!<|user(?:name)?\b|a\b|test\b)[^/\s]+", text):
            errors.append(f"개인 POSIX 절대경로 발견: {rel}")
        for label, pattern in SECRET_PATTERNS.items():
            if pattern.search(text):
                errors.append(f"{label} 후보 발견: {rel}")
        for email in re.findall(r"(?i)\b[A-Z0-9._%+-]+@[A-Z0-9.-]+\.[A-Z]{2,}\b", text):
            domain = email.rsplit("@", 1)[-1].lower()
            if (not email.lower().endswith(("@example.com", "@example.invalid", "@users.noreply.github.com"))
                    and not domain.endswith((".md", ".json", ".py", ".yml", ".yaml"))):
                errors.append(f"개인 이메일 후보 발견: {rel}")
        if re.search(r"(?<![\d.])(?:10\.|192\.168\.|172\.(?:1[6-9]|2\d|3[01])\.)\d{1,3}(?:\.\d{1,3}){2}(?![\d.])", text):
            errors.append(f"사설 IP 후보 발견: {rel}")
        if re.search(r"(?<![.\w])/?p" + "sp:", text):
            errors.append(f"옛 명령 네임스페이스 발견: {rel}")
        if path.suffix.lower() == ".md":
            for raw, target in local_links(path):
                if not target.exists():
                    errors.append(f"죽은 링크: {rel} -> {raw}")
                else:
                    inbound[target] += 1
        if "/skills/" not in f"/{rel}" and path.name != "LICENSE":
            hashes[hashlib.sha256(path.read_bytes()).hexdigest()].append(rel)

    for rel in files:
        path = ROOT / rel
        if rel.startswith("docs/") and rel.endswith(".md") and "/update_reviews/" not in f"/{rel}":
            if inbound[path.resolve()] == 0:
                errors.append(f"진입 링크가 없는 고아 문서: {rel}")
    for duplicates in hashes.values():
        manifest_pair = {"plugins/philip/plugin.json", "plugins/philip/.claude-plugin/plugin.json"}
        if len(duplicates) > 1 and set(duplicates) != manifest_pair:
            errors.append("수동 중복 파일: " + ", ".join(duplicates))

    generated = subprocess.run(
        [sys.executable, str(PLUGIN / "tools" / "build_skills.py"), "--check"],
        cwd=ROOT,
        capture_output=True,
        text=True,
        encoding="utf-8",
    )
    if generated.returncode:
        errors.append("생성된 skill 드리프트: " + (generated.stdout.strip() or generated.stderr.strip()))

    if errors:
        print("공개 릴리스 검사 실패:\n- " + "\n- ".join(dict.fromkeys(errors)))
        return 1
    print(f"공개 릴리스 검사 통과: Philip Relay v{version}, skill {len(skill_names)}개, 파일 {len(files)}개")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
