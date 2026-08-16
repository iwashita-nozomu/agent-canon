#!/usr/bin/env python3
"""Apply the one-time Issue #706 container preflight documentation correction."""

from __future__ import annotations

from pathlib import Path

PATH = Path("agents/skills/environment-maintenance.md")


def main() -> int:
    """Restore static owner preflight without changing the acceptance pair."""
    text = PATH.read_text(encoding="utf-8")
    old = '''## Validation

```bash
docker build -f docker/Dockerfile -t <rootrepo> .
docker run --rm <rootrepo> testrunner.sh
```

- command pair は target repository Git root を current directory として、同じ `<rootrepo>`
'''
    new = '''## Validation

```bash
docker build -f docker/Dockerfile -t <rootrepo> .
docker run --rm <rootrepo> testrunner.sh
```

- static owner preflight は `python3 tools/ci/container_config.py` で Dockerfile、public runner、
  container configuration の静的な責務関係を検査します。この preflight は上記 exact command
  pair の一部でも代替でもなく、acceptance evidence は fresh image の build と run だけです。
- command pair は target repository Git root を current directory として、同じ `<rootrepo>`
'''
    count = text.count(old)
    if count != 1:
        raise SystemExit(f"validation section: expected one match, found {count}")
    PATH.write_text(text.replace(old, new, 1), encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
