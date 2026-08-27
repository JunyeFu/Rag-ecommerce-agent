#!/usr/bin/env python3
"""Generate a deterministic cross-ecosystem CycloneDX inventory and license ledger."""

from __future__ import annotations

import argparse
import json
import re
import tomllib
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
SBOM = ROOT / "docs/security/evidence/sbom.json"
LICENSES = ROOT / "docs/security/evidence/license-report.json"


def component(ecosystem: str, name: str, version: str, license_id: str = "NOASSERTION") -> dict:
    purl_type = {"python": "pypi", "node": "npm", "gradle": "maven", "container": "oci"}[ecosystem]
    return {
        "type": "container" if ecosystem == "container" else "library",
        "group": ecosystem,
        "name": name,
        "version": version,
        "licenses": [{"license": {"id": license_id}}],
        "purl": f"pkg:{purl_type}/{name}@{version}",
    }


def python_components() -> list[dict]:
    lock = tomllib.loads((ROOT / "uv.lock").read_text(encoding="utf-8"))
    return [component("python", item["name"], item["version"]) for item in lock["package"]]


def node_components() -> list[dict]:
    lock = json.loads((ROOT / "package-lock.json").read_text(encoding="utf-8"))
    result = []
    for path, item in lock["packages"].items():
        if not path.startswith("node_modules/") or "version" not in item:
            continue
        name = path.removeprefix("node_modules/")
        result.append(component("node", name, item["version"], item.get("license", "NOASSERTION")))
    return result


def gradle_components() -> list[dict]:
    files = (ROOT / "apps/android/app/build.gradle.kts", ROOT / "apps/android/build.gradle.kts")
    pattern = re.compile(r'"([A-Za-z0-9_.-]+):([A-Za-z0-9_.-]+)(?::([^"$]+))?"')
    found = set()
    for path in files:
        for group, artifact, version in pattern.findall(path.read_text(encoding="utf-8")):
            found.add((f"{group}/{artifact}", version or "BOM-managed"))
    return [component("gradle", name, version) for name, version in sorted(found)]


def container_components() -> list[dict]:
    versions = json.loads((ROOT / "toolchain.versions.json").read_text(encoding="utf-8"))
    result = []
    for image in versions["containers"].values():
        name, version = image.rsplit(":", 1)
        result.append(component("container", name, version))
    return result


def render() -> tuple[str, str]:
    components = (
        python_components() + node_components() + gradle_components() + container_components()
    )
    components.sort(key=lambda item: item["purl"])
    bom: dict[str, Any] = {
        "bomFormat": "CycloneDX",
        "specVersion": "1.6",
        "version": 1,
        "metadata": {
            "component": {
                "type": "application",
                "name": "rag-commerce-v2",
                "version": "0.1.0",
            },
            "properties": [
                {"name": "evidence.scope", "value": "locked local dependency inventory"},
                {
                    "name": "evidence.boundary",
                    "value": "not a vulnerability, provenance, or legal license conclusion",
                },
            ],
        },
        "components": components,
    }
    counts: dict[str, int] = {}
    unknown = []
    for item in components:
        license_id = item["licenses"][0]["license"]["id"]
        counts[license_id] = counts.get(license_id, 0) + 1
        if license_id == "NOASSERTION":
            unknown.append(item["purl"])
    licenses = {
        "schema_version": 1,
        "source": "docs/security/evidence/sbom.json",
        "component_count": len(components),
        "license_counts": dict(sorted(counts.items())),
        "noassertion_components": unknown,
        "commercial_release_eligible": False,
        "external_gate": "Resolve NOASSERTION entries and complete legal review",
    }
    return (
        json.dumps(bom, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        json.dumps(licenses, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
    )


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--check", action="store_true")
    args = parser.parse_args()
    sbom, licenses = render()
    expected = {SBOM: sbom, LICENSES: licenses}
    if args.check:
        drift = [
            path
            for path, value in expected.items()
            if not path.is_file() or path.read_text(encoding="utf-8") != value
        ]
        if drift:
            for path in drift:
                print(f"DRIFT {path.relative_to(ROOT).as_posix()}")
            return 1
        print(f"sbom=verified components={len(json.loads(sbom)['components'])} files=2")
        return 0
    for path, value in expected.items():
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(value, encoding="utf-8", newline="\n")
        print(f"generated {path.relative_to(ROOT).as_posix()}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
