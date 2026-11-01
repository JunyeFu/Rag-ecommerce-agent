"""Download exact public Docker Hub images via the host when daemon auth returns EOF.

No daemon/global proxy changes; verified OCI blobs are loaded into local Docker.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import subprocess
import tarfile
import urllib.parse
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
ACCEPT = ", ".join(
    [
        "application/vnd.oci.image.index.v1+json",
        "application/vnd.docker.distribution.manifest.list.v2+json",
        "application/vnd.oci.image.manifest.v1+json",
        "application/vnd.docker.distribution.manifest.v2+json",
    ]
)


def fetch(url: str, headers: dict[str, str] | None = None) -> bytes:
    # Windows curl succeeds where daemon/Python TLS returns EOF on this host.
    config = f"url = {json.dumps(url)}\n" + "".join(
        f"header = {json.dumps(f'{key}: {value}')}\n" for key, value in (headers or {}).items()
    )
    return subprocess.run(
        [
            "curl.exe",
            "--fail",
            "--location",
            "--silent",
            "--show-error",
            "--max-time",
            "120",
            "--retry",
            "2",
            "--retry-all-errors",
            "--config",
            "-",
        ],
        input=config.encode(),
        stdout=subprocess.PIPE,
        check=True,
    ).stdout


def pull(image: str, directory: Path) -> None:
    repository, tag = image.rsplit(":", 1)
    quay = repository.startswith("quay.io/")
    if quay:
        repository = repository.removeprefix("quay.io/")
    if "/" not in repository:
        repository = f"library/{repository}"
    params = urllib.parse.urlencode(
        {
            "service": "quay.io" if quay else "registry.docker.io",
            "scope": f"repository:{repository}:pull",
        }
    )
    auth_url = "https://quay.io/v2/auth" if quay else "https://auth.docker.io/token"
    token = json.loads(fetch(f"{auth_url}?{params}"))["token"]
    headers = {"Authorization": f"Bearer {token}", "Accept": ACCEPT}
    base = (
        f"https://quay.io/v2/{repository}"
        if quay
        else f"https://registry-1.docker.io/v2/{repository}"
    )
    manifest_bytes = fetch(f"{base}/manifests/{tag}", headers)
    manifest = json.loads(manifest_bytes)
    if "manifests" in manifest:
        descriptor = next(
            m
            for m in manifest["manifests"]
            if m.get("platform", {}).get("os") == "linux"
            and m.get("platform", {}).get("architecture") == "amd64"
        )
        manifest_bytes = fetch(f"{base}/manifests/{descriptor['digest']}", headers)
        manifest = json.loads(manifest_bytes)
    directory.mkdir(parents=True, exist_ok=True)
    blobs = directory / "blobs/sha256"
    blobs.mkdir(parents=True, exist_ok=True)
    for descriptor in [manifest["config"], *manifest["layers"]]:
        digest = descriptor["digest"].split(":", 1)[1]
        target = blobs / digest
        if target.exists() and hashlib.sha256(target.read_bytes()).hexdigest() == digest:
            continue
        print(f"{image}: downloading {descriptor['size']} bytes", flush=True)
        content = fetch(f"{base}/blobs/sha256:{digest}", headers)
        if hashlib.sha256(content).hexdigest() != digest:
            raise RuntimeError("official registry blob digest mismatch")
        target.write_bytes(content)
    digest = hashlib.sha256(manifest_bytes).hexdigest()
    (blobs / digest).write_bytes(manifest_bytes)
    (directory / "oci-layout").write_text('{"imageLayoutVersion":"1.0.0"}', encoding="utf-8")
    index = {
        "schemaVersion": 2,
        "manifests": [
            {
                "mediaType": manifest["mediaType"],
                "size": len(manifest_bytes),
                "digest": f"sha256:{digest}",
                "annotations": {"org.opencontainers.image.ref.name": image},
            }
        ],
    }
    (directory / "index.json").write_text(json.dumps(index), encoding="utf-8")
    archive = directory.parent / f"{directory.name}.tar"
    with tarfile.open(archive, "w") as tar:
        tar.add(directory / "oci-layout", arcname="oci-layout")
        tar.add(directory / "index.json", arcname="index.json")
        tar.add(directory / "blobs", arcname="blobs")
    subprocess.run(["docker", "load", "--input", str(archive)], check=True)
    print(f"loaded exact official image {image}", flush=True)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("images", nargs="+")
    args = parser.parse_args()
    for image in args.images:
        if image.startswith(("http", "ghcr.")) or (
            image.startswith("quay.") and not image.startswith("quay.io/minio/minio:")
        ):
            raise ValueError(
                "only exact public Docker Hub and official MinIO Quay references are accepted"
            )
        pull(image, ROOT / "output/official-images" / image.replace("/", "_").replace(":", "_"))


if __name__ == "__main__":
    main()
