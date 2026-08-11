#!/usr/bin/env python3
"""Gate: block a Dependabot PR from auto-merge until its target version has
been published on the upstream registry for at least MIN_AGE_DAYS.

This exists to blunt "flash" supply-chain incidents (a malicious or broken
release that gets yanked/fixed within hours) without needing an LLM or any
judgment call -- it's a single deterministic query against the registry
that already tracks publish time for every version.

Currently implements the gomod ecosystem only (queries proxy.golang.org,
which mirrors every module version's timestamp -- see
https://go.dev/ref/mod#goproxy-protocol). Other ecosystems fail closed
(exit 1, i.e. "not yet eligible") rather than silently skipping the gate,
because a missing check should never look like a passing one on an
auto-merge path.

Env vars (as produced by dependabot/fetch-metadata):
  ECOSYSTEM     steps.metadata.outputs.package-ecosystem
  DEP_NAME      steps.metadata.outputs.dependency-names
  NEW_VERSION   steps.metadata.outputs.new-version
  MIN_AGE_DAYS  minimum release age required to pass (default 3)
"""

import datetime
import json
import os
import sys
import urllib.request

GOPROXY = "https://proxy.golang.org"


def escape_module_path(path: str) -> str:
    """Go module proxy escaping: each uppercase letter X -> '!' + lower(x)."""
    out = []
    for ch in path:
        if ch.isupper():
            out.append("!" + ch.lower())
        else:
            out.append(ch)
    return "".join(out)


def fetch_publish_time(module: str, version: str) -> datetime.datetime:
    if not version.startswith("v"):
        version = "v" + version
    url = f"{GOPROXY}/{escape_module_path(module)}/@v/{escape_module_path(version)}.info"
    with urllib.request.urlopen(url, timeout=15) as resp:
        info = json.loads(resp.read())
    # RFC3339, e.g. "2026-03-19T10:16:37Z"
    return datetime.datetime.fromisoformat(info["Time"].replace("Z", "+00:00"))


def main() -> int:
    ecosystem = os.environ.get("ECOSYSTEM", "")
    dep_name = os.environ.get("DEP_NAME", "")
    new_version = os.environ.get("NEW_VERSION", "")
    min_age_days = int(os.environ.get("MIN_AGE_DAYS", "3"))

    if ecosystem != "gomod":
        print(f"age-gate: ecosystem {ecosystem!r} is not supported yet "
              f"(only gomod is implemented) -- failing closed.")
        return 1

    if "," in dep_name:
        print(f"age-gate: grouped update ({dep_name!r}) covers multiple "
              f"dependencies -- per-dependency age check is not implemented "
              f"yet -- failing closed.")
        return 1

    if not dep_name or not new_version:
        print("age-gate: missing DEP_NAME or NEW_VERSION -- failing closed.")
        return 1

    try:
        published = fetch_publish_time(dep_name, new_version)
    except Exception as exc:  # noqa: BLE001 -- any lookup failure fails closed
        print(f"age-gate: could not resolve publish time for {dep_name}@{new_version}: {exc}")
        return 1

    age = datetime.datetime.now(datetime.timezone.utc) - published
    print(f"age-gate: {dep_name}@{new_version} published {published.isoformat()} "
          f"({age.days} days ago; minimum is {min_age_days}).")

    if age.days < min_age_days:
        print("age-gate: FAIL -- release is too new.")
        return 1

    print("age-gate: PASS.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
