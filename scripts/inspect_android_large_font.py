"""Capture actual QA screens at two font scales, restoring device configuration."""

import argparse
import json
import re
import subprocess
import xml.etree.ElementTree as ET
from pathlib import Path

PACKAGE = "com.ragcommerce.agent.safetytest"


def inspect(adb, serial, port, artifacts):
    def command(*args):
        return subprocess.check_output(
            [str(adb), "-P", str(port), "-s", serial, *args], text=True, encoding="utf-8"
        ).strip()

    if command("shell", "getprop", "ro.boot.qemu.avd_name") != "RagFinalSafety20261012":
        raise ValueError("Only the owned QA AVD is allowed")
    original_scale = command("shell", "settings", "get", "system", "font_scale")
    density = (
        int(re.search(r"Physical density:\s*(\d+)", command("shell", "wm", "density"))[1]) / 160
    )

    def tree():
        raw = command("exec-out", "uiautomator", "dump", "/dev/tty")
        xml = raw[raw.index("<?xml") : raw.index("</hierarchy>") + len("</hierarchy>")]
        return ET.fromstring(xml), xml

    def tap_label(label):
        root, _ = tree()
        parents = {child: parent for parent in root.iter() for child in parent}
        candidates = []
        for node in root.iter("node"):
            if node.get("text") != label and node.get("content-desc") != label:
                continue
            selected = node
            while selected is not None:
                if selected.get("selected") == "true" and selected.get("enabled") == "true":
                    return  # The actual tab is already selected; no click action is exposed.
                selected = parents.get(selected)
            while node is not None and (
                node.get("clickable") != "true" or node.get("enabled") != "true"
            ):
                node = parents.get(node)
            if node is not None and node not in candidates:
                candidates.append(node)
        if len(candidates) != 1:
            raise ValueError(
                f"Expected one enabled actual action for {label}; found {len(candidates)}"
            )
        node = candidates[0]
        left, top, right, bottom = map(int, re.findall(r"\d+", node.get("bounds")))
        command("shell", "input", "tap", str((left + right) // 2), str((top + bottom) // 2))

    records = []
    try:
        root, _ = tree()
        if any(node.get("text") == "继续任务" for node in root.iter("node")):
            tap_label("继续任务")
        root, _ = tree()
        if any(node.get("content-desc") == "返回 Mission 对话" for node in root.iter("node")):
            tap_label("返回 Mission 对话")
        for scale in ("1.0", "2.0"):
            command("shell", "settings", "put", "system", "font_scale", scale)
            for tab in ("任务", "决策", "我的"):
                tap_label(tab)
                root, xml = tree()
                name = f"font-{scale}-{tab}"
                artifacts.joinpath(name + ".xml").write_text(xml, encoding="utf-8")
                pixels = subprocess.check_output(
                    [str(adb), "-P", str(port), "-s", serial, "exec-out", "screencap", "-p"]
                )
                artifacts.joinpath(name + ".png").write_bytes(pixels)
                controls = []
                for node in root.iter("node"):
                    if (
                        node.get("package") != PACKAGE
                        or node.get("clickable") != "true"
                        or node.get("enabled") != "true"
                    ):
                        continue
                    left, top, right, bottom = map(int, re.findall(r"\d+", node.get("bounds")))
                    if right <= left or bottom <= top:
                        continue
                    label = node.get("content-desc") or " / ".join(
                        child.get("text", "") for child in node.iter("node") if child.get("text")
                    )
                    controls.append(
                        {
                            "label": label,
                            "width_dp": round((right - left) / density, 2),
                            "height_dp": round((bottom - top) / density, 2),
                        }
                    )
                records.append(
                    {
                        "scale": scale,
                        "tab": tab,
                        "controls": controls,
                        "small_visible_bounds": [
                            c for c in controls if c["width_dp"] < 48 or c["height_dp"] < 48
                        ],
                        "screenshot": name + ".png",
                        "xml": name + ".xml",
                    }
                )
        tap_label("任务")
    finally:
        command("shell", "settings", "put", "system", "font_scale", original_scale)
    return {
        "scope": "Read-only native three-screen captures, not full accessibility signoff",
        "records": records,
        "original_font_scale": original_scale,
        "restored_font_scale": command("shell", "settings", "get", "system", "font_scale"),
        "density": density,
        "new_turns_submitted": 0,
        "talkback_traversal": "NOT_RUN",
    }


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--adb", required=True, type=Path)
    parser.add_argument("--serial", required=True)
    parser.add_argument("--adb-server-port", type=int, default=20884)
    parser.add_argument("--artifacts", required=True, type=Path)
    args = parser.parse_args()
    if args.artifacts.exists():
        parser.error("Preserve previous capture folder")
    args.artifacts.mkdir(parents=True)
    report = inspect(args.adb, args.serial, args.adb_server_port, args.artifacts)
    args.artifacts.joinpath("summary.json").write_text(
        json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    print(
        json.dumps(
            {
                "screens": len(report["records"]),
                "font_restored": report["restored_font_scale"],
                "small_visible_controls": sum(
                    len(r["small_visible_bounds"]) for r in report["records"]
                ),
            },
            ensure_ascii=False,
        )
    )


if __name__ == "__main__":
    main()
