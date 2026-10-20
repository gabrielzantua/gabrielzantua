from __future__ import annotations

import hashlib
import html
import json
import re
import subprocess
import sys
import tempfile
import time
from pathlib import Path
from urllib.error import HTTPError
from urllib.request import Request, urlopen


USERNAME = "pinggu0x"
API_URL = f"https://tryhackme.com/api/v2/public-profile?username={USERNAME}"
REPO = Path(__file__).resolve().parents[1]
README = REPO / "README.md"
README_RELATIVE = "README.md"
BADGE_PATH = re.compile(r"^assets/tryhackme-profile(?:-[0-9a-f]{12})?\.svg$")
BADGE_REFERENCE = re.compile(r'src="(assets/tryhackme-profile(?:-[0-9a-f]{12})?\.svg)"')
REFRESH_COMMIT = "chore: refresh TryHackMe badge"

LEVEL_NAMES = {
    1: "Neophyte",
    2: "Apprentice",
    3: "Pathfinder",
    4: "Seeker",
    5: "Visionary",
    6: "Voyager",
    7: "Adept",
    8: "Hacker",
    9: "Mage",
    10: "Wizard",
    11: "Master",
    12: "Guru",
    13: "Legend",
    14: "Guardian",
    15: "Titan",
    16: "Sage",
    17: "Vanguard",
    18: "Shogun",
    19: "Ascended",
    20: "Mythic",
    21: "Grandmaster",
}


def badge_asset_path(svg: str) -> str:
    digest = hashlib.sha256(svg.encode("utf-8")).hexdigest()[:12]
    return f"assets/tryhackme-profile-{digest}.svg"


def replace_badge_reference(readme: str, new_path: str) -> tuple[str, str]:
    if not BADGE_PATH.fullmatch(new_path):
        raise ValueError("Invalid TryHackMe badge image path")
    matches = list(BADGE_REFERENCE.finditer(readme))
    if len(matches) != 1:
        raise ValueError("README must contain exactly one TryHackMe badge image")
    match = matches[0]
    old_path = match.group(1)
    updated = readme[:match.start(1)] + new_path + readme[match.end(1):]
    return updated, old_path


def normalize_profile(data: dict) -> dict:
    if data.get("username") != USERNAME or data.get("isPrivateProfile") is not False:
        raise ValueError("TryHackMe returned a different or private profile")

    metrics = {}
    for field in ("level", "totalPoints", "completedRoomsNumber", "badgesNumber", "streak"):
        value = data.get(field)
        if type(value) is not int or value < 0:
            raise ValueError(f"TryHackMe returned an invalid {field}")
        metrics[field] = value

    if metrics["level"] < 1:
        raise ValueError("TryHackMe returned an invalid level")
    metrics["levelCode"] = f"0x{metrics['level']:X}"
    metrics["levelName"] = LEVEL_NAMES.get(metrics["level"], f"Level {metrics['levelCode']}")

    for field, minimum in (("rank", 1), ("topPercentage", 0)):
        value = data.get(field)
        if value is not None and (type(value) is not int or value < minimum):
            raise ValueError(f"TryHackMe returned an invalid {field}")
        metrics[field] = value

    tier = data.get("leagueTier")
    if tier is not None and (not isinstance(tier, str) or len(tier) > 24):
        raise ValueError("TryHackMe returned an invalid league tier")
    metrics["leagueTier"] = tier or "unranked"
    return metrics


def render_badge(data: dict) -> str:
    profile = normalize_profile(data)
    level_name = html.escape(profile["levelName"])
    level_code = profile["levelCode"]
    rank_label = f"RANK #{profile['rank']:,}" if profile["rank"] else "UNRANKED"
    top_label = (
        f"TOP {profile['topPercentage']}%"
        if profile["topPercentage"]
        else "UNRANKED"
    )
    tier = html.escape(profile["leagueTier"].upper())
    metrics = (
        ("LEVEL", level_name, level_code),
        ("ROOMS", f"{profile['completedRoomsNumber']:,}", None),
        ("POINTS", f"{profile['totalPoints']:,}", None),
        ("BADGES", f"{profile['badgesNumber']:,}", None),
        ("STREAK", f"{profile['streak']:,} DAYS", None),
    )

    cards = []
    for index, (label, value, detail) in enumerate(metrics):
        x = 28 + index * 184
        value_text = (
            f'<text x="15" y="48" class="level-name">{value}</text>'
            f'<text x="15" y="66" class="level-code">{detail}</text>'
            if detail
            else f'<text x="15" y="58" class="value">{value}</text>'
        )
        cards.append(
            f'''<g transform="translate({x} 133)">
  <rect width="168" height="76" rx="12" fill="#111a24" stroke="#283746"/>
  <text x="15" y="25" class="label">{label}</text>
  {value_text}
</g>'''
        )

    title = html.escape(f"TryHackMe profile badge for {USERNAME}: {level_name} ({level_code})", quote=True)
    return f'''<svg xmlns="http://www.w3.org/2000/svg" width="960" height="226" viewBox="0 0 960 226" role="img" aria-labelledby="title desc">
<title id="title">{title}</title>
<desc id="desc">{level_name}, level {level_code}, {profile['completedRoomsNumber']} rooms, {profile['totalPoints']} points, {profile['badgesNumber']} badges, and a {profile['streak']} day streak.</desc>
<defs>
  <linearGradient id="accent" x1="0" y1="0" x2="1" y2="1">
    <stop offset="0" stop-color="#a8e63f"/>
    <stop offset="1" stop-color="#65b80a"/>
  </linearGradient>
</defs>
<rect x="1" y="1" width="958" height="224" rx="18" fill="#0b1119" stroke="#263543" stroke-width="2"/>
<path d="M19 2h220v4H19z" fill="url(#accent)"/>
<circle cx="34" cy="35" r="5" fill="#88cc14"/>
<text x="48" y="40" class="eyebrow">TRYHACKME <tspan fill="#566777">/</tspan> PROFILE</text>
<text x="28" y="85" class="name">{USERNAME}</text>
<text x="29" y="111" class="summary">{top_label} <tspan fill="#566777">·</tspan> {rank_label} <tspan fill="#566777">·</tspan> {tier} LEAGUE</text>
<rect x="778" y="23" width="154" height="34" rx="17" fill="#15220e" stroke="#36551a"/>
<circle cx="796" cy="40" r="4" fill="#88cc14"/>
<text x="808" y="44" class="sync">TRYHACKME STATS</text>
{''.join(cards)}
<style>
  .eyebrow {{ fill:#88cc14; font:700 12px 'Segoe UI',Arial,sans-serif; letter-spacing:2px; }}
  .name {{ fill:#e7edf3; font:700 30px 'Segoe UI',Arial,sans-serif; }}
  .summary {{ fill:#9aa9b7; font:600 12px 'Segoe UI',Arial,sans-serif; letter-spacing:1px; }}
  .sync {{ fill:#a9c889; font:700 10px 'Segoe UI',Arial,sans-serif; letter-spacing:1px; }}
  .label {{ fill:#8393a2; font:700 10px 'Segoe UI',Arial,sans-serif; letter-spacing:1.5px; }}
  .level-name {{ fill:#e7edf3; font:700 16px 'Segoe UI',Arial,sans-serif; }}
  .level-code {{ fill:#a9c889; font:600 10px 'Segoe UI',Arial,sans-serif; letter-spacing:1px; }}
  .value {{ fill:#e7edf3; font:700 20px 'Segoe UI',Arial,sans-serif; }}
</style>
</svg>
'''


def git(*args: str, check: bool = True) -> subprocess.CompletedProcess:
    result = subprocess.run(args, cwd=REPO, text=True, capture_output=True)
    if check and result.returncode:
        raise RuntimeError(result.stderr.strip() or f"git {' '.join(args)} failed")
    return result


def sync_main() -> bool:
    branch = git("git", "branch", "--show-current").stdout.strip()
    if branch != "main":
        print(f"skip: expected main branch, found {branch or 'detached HEAD'}")
        return False

    if git("git", "status", "--porcelain").stdout.strip():
        print("skip: repository has local changes")
        return False

    git("git", "fetch", "origin", "main")
    local_head = git("git", "rev-parse", "HEAD").stdout.strip()
    remote_head = git("git", "rev-parse", "origin/main").stdout.strip()
    if local_head == remote_head:
        return True

    local_is_behind = git("git", "merge-base", "--is-ancestor", "HEAD", "origin/main", check=False)
    if local_is_behind.returncode == 0:
        git("git", "merge", "--ff-only", "origin/main")
        return True

    remote_is_behind = git("git", "merge-base", "--is-ancestor", "origin/main", "HEAD", check=False)
    if remote_is_behind.returncode == 0:
        changed_paths = set(git("git", "diff", "--name-only", "origin/main...HEAD").stdout.splitlines())
        subjects = git("git", "log", "--format=%s", "origin/main..HEAD").stdout.splitlines()
        badge_paths = {path for path in changed_paths if BADGE_PATH.fullmatch(path)}
        allowed_paths = badge_paths | {README_RELATIVE}
        if badge_paths and changed_paths <= allowed_paths and all(subject == REFRESH_COMMIT for subject in subjects):
            push()
            return True

    print("skip: local and remote main have unrelated changes")
    return False


def push() -> None:
    git(
        "git",
        "-c",
        "credential.helper=!gh auth git-credential",
        "push",
        "origin",
        "HEAD:main",
    )


def fetch_profile() -> dict:
    request_url = f"{API_URL}&_={time.time_ns()}"
    request = Request(
        request_url,
        headers={
            "Accept": "application/json, text/plain, */*",
            "Accept-Language": "en-US,en;q=0.9",
            "Cache-Control": "no-cache",
            "Pragma": "no-cache",
            "Origin": "https://tryhackme.com",
            "Referer": f"https://tryhackme.com/p/{USERNAME}",
            "Sec-Fetch-Dest": "empty",
            "Sec-Fetch-Mode": "cors",
            "Sec-Fetch-Site": "same-origin",
            "User-Agent": "Mozilla/5.0 (X11; Linux x86_64; rv:143.0) Gecko/20100101 Firefox/143.0",
        },
    )
    try:
        with urlopen(request, timeout=20) as response:
            payload = json.load(response)
    except HTTPError as error:
        if error.code != 429:
            raise
        print("TryHackMe challenged the request; fetching public stats via Jina Reader")
        reader = Request(
            f"https://r.jina.ai/{request_url}",
            headers={
                "Accept": "application/json",
                "X-No-Cache": "true",
                "X-Engine": "browser",
                "X-Timeout": "30",
                "X-Wait-For-Selector": "pre",
            },
        )
        with urlopen(reader, timeout=60) as response:
            envelope = json.load(response)
        result = envelope.get("data") if isinstance(envelope, dict) else None
        if (
            not isinstance(envelope, dict)
            or envelope.get("code") != 200
            or not isinstance(result, dict)
            or result.get("url") != request_url
            or result.get("httpStatus") != 200
            or not isinstance(result.get("content"), str)
        ):
            raise ValueError("Reader returned an invalid TryHackMe response")
        payload = json.loads(result["content"])
    if not isinstance(payload, dict) or payload.get("status") != "success" or not isinstance(payload.get("data"), dict):
        raise ValueError("TryHackMe returned an invalid public profile response")
    return payload["data"]


def update_badge() -> bool:
    if not sync_main():
        return False

    svg = render_badge(fetch_profile())
    new_relative_path = badge_asset_path(svg)
    new_badge = REPO / new_relative_path
    readme_text = README.read_text()
    updated_readme, old_relative_path = replace_badge_reference(readme_text, new_relative_path)
    old_badge = REPO / old_relative_path

    if old_relative_path == new_relative_path and new_badge.exists() and new_badge.read_text() == svg:
        print("TryHackMe badge is unchanged")
        return False

    new_badge.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile("w", encoding="utf-8", dir=new_badge.parent, delete=False) as temp:
        temp.write(svg)
        temp_path = Path(temp.name)
    temp_path.replace(new_badge)
    README.write_text(updated_readme)

    paths = [README_RELATIVE, new_relative_path]
    if old_relative_path != new_relative_path and old_badge.exists():
        old_badge.unlink()
        paths.append(old_relative_path)

    git("git", "add", "--", *paths)
    git("git", "commit", "--only", "-m", REFRESH_COMMIT, "--", *paths)
    push()
    print("TryHackMe badge updated and pushed")
    return True


def main() -> int:
    try:
        update_badge()
    except Exception as error:
        print(f"TryHackMe badge refresh failed: {error}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
