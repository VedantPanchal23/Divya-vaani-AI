"""
Validate and prepare a YouTube cookies.txt file for deployment.
Checks format, freshness, and provides Railway deployment instructions.

Usage:
    python scripts/validate_cookies.py                          # Validate existing cookies.txt
    python scripts/validate_cookies.py path/to/cookies.txt      # Validate specific file
    python scripts/validate_cookies.py --export-env              # Output for YOUTUBE_COOKIES_CONTENT env var
"""
import sys
import os
from pathlib import Path
from datetime import datetime


def validate_cookies(cookie_path: str) -> dict:
    """Validate a Netscape-format cookies.txt file."""
    path = Path(cookie_path)
    result = {
        "valid": False,
        "path": str(path.absolute()),
        "errors": [],
        "warnings": [],
        "stats": {"total_lines": 0, "cookie_lines": 0, "youtube_cookies": 0, "expired": 0},
    }

    if not path.exists():
        result["errors"].append(f"File not found: {path}")
        return result

    try:
        content = path.read_text(encoding="utf-8", errors="strict")
    except UnicodeDecodeError:
        result["errors"].append("File is binary/corrupted — not a valid text cookie file.")
        return result

    lines = content.strip().split("\n")
    result["stats"]["total_lines"] = len(lines)

    has_header = False
    now = datetime.now().timestamp()

    for line in lines:
        line = line.strip()
        if not line:
            continue
        if line.startswith("# Netscape HTTP Cookie File"):
            has_header = True
            continue
        if line.startswith("#"):
            continue

        parts = line.split("\t")
        if len(parts) < 7:
            continue

        result["stats"]["cookie_lines"] += 1
        domain = parts[0].lower()

        if "youtube" in domain or "google" in domain or "googlevideo" in domain:
            result["stats"]["youtube_cookies"] += 1

        # Check expiration (field index 4)
        try:
            expiry = int(parts[4])
            if 0 < expiry < now:
                result["stats"]["expired"] += 1
        except (ValueError, IndexError):
            pass

    if not has_header:
        result["warnings"].append("Missing '# Netscape HTTP Cookie File' header — may still work.")

    if result["stats"]["youtube_cookies"] == 0:
        result["errors"].append("No YouTube/Google cookies found! Make sure you export from youtube.com while logged in.")
    elif result["stats"]["youtube_cookies"] < 5:
        result["warnings"].append(f"Only {result['stats']['youtube_cookies']} YouTube cookies — may be incomplete.")

    if result["stats"]["expired"] > result["stats"]["cookie_lines"] * 0.5:
        result["warnings"].append(f"{result['stats']['expired']}/{result['stats']['cookie_lines']} cookies are expired — re-export recommended.")

    if not result["errors"]:
        result["valid"] = True

    return result


def print_report(result: dict):
    print("\n" + "=" * 60)
    print("  YouTube Cookie File Validation")
    print("=" * 60)
    print(f"  File: {result['path']}")
    print(f"  Status: {'VALID' if result['valid'] else 'INVALID'}")
    print(f"  Total lines: {result['stats']['total_lines']}")
    print(f"  Cookie entries: {result['stats']['cookie_lines']}")
    print(f"  YouTube/Google cookies: {result['stats']['youtube_cookies']}")
    print(f"  Expired cookies: {result['stats']['expired']}")
    print()

    if result["errors"]:
        print("  ERRORS:")
        for e in result["errors"]:
            print(f"    {e}")
        print()

    if result["warnings"]:
        print("  WARNINGS:")
        for w in result["warnings"]:
            print(f"    {w}")
        print()

    if result["valid"]:
        print("  Cookie file looks good for YouTube downloads!")
    print("=" * 60)


def export_for_env(cookie_path: str):
    """Print cookie content ready for Railway env var."""
    path = Path(cookie_path)
    content = path.read_text(encoding="utf-8")
    print("\n--- Copy EVERYTHING below this line into Railway env var YOUTUBE_COOKIES_CONTENT ---\n")
    print(content)
    print("\n--- End of cookie content ---")
    print(f"\nContent length: {len(content)} characters")


if __name__ == "__main__":
    default_path = Path(__file__).parent.parent / "cookies.txt"

    if "--export-env" in sys.argv:
        cookie_path = sys.argv[1] if len(sys.argv) > 1 and not sys.argv[1].startswith("--") else str(default_path)
        result = validate_cookies(cookie_path)
        if result["valid"]:
            export_for_env(cookie_path)
        else:
            print_report(result)
            print("\nFix errors before exporting for Railway.")
        sys.exit(0)

    cookie_path = sys.argv[1] if len(sys.argv) > 1 and not sys.argv[1].startswith("--") else str(default_path)
    result = validate_cookies(cookie_path)
    print_report(result)

    if result["valid"]:
        print("\n  NEXT STEPS for Railway deployment:")
        print("  ──────────────────────────────────")
        print(f"  Run: python scripts/validate_cookies.py --export-env")
        print("  Then paste the output into Railway Dashboard:")
        print("    → Service → Variables → New Variable")
        print("    → Name: YOUTUBE_COOKIES_CONTENT")
        print("    → Value: <paste the cookie content>")
        print()

    sys.exit(0 if result["valid"] else 1)
