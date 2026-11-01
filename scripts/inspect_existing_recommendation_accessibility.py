"""Read-only native review of an existing real recommendation, never a new Run."""

import argparse
import json
import re
import subprocess
import xml.etree.ElementTree as ET
from pathlib import Path

import httpx


def inspect(args):
    adb = [str(args.adb), "-P", "20884", "-s", args.serial]

    def command(*items):
        return subprocess.check_output(adb + list(items), text=True, encoding="utf-8").strip()

    if command("shell", "getprop", "ro.boot.qemu.avd_name") != "RagFinalSafety20261012":
        raise ValueError("Only the owned QA AVD is in scope")
    original_font = command("shell", "settings", "get", "system", "font_scale")
    if command("shell", "settings", "get", "secure", "enabled_accessibility_services") != "null":
        raise ValueError("UI Automation capture must not suppress an active accessibility service")

    def tree():
        raw = command("exec-out", "uiautomator", "dump", "/dev/tty")
        xml = raw[raw.index("<?xml") : raw.index("</hierarchy>") + 12]
        return ET.fromstring(xml), xml

    def bounds(node):
        return list(map(int, re.findall(r"\d+", node.get("bounds"))))

    def tap(label):
        root, _ = tree()
        parents = {child: parent for parent in root.iter() for child in parent}
        nodes = [
            n for n in root.iter("node") if n.get("text") == label or n.get("content-desc") == label
        ]
        if len(nodes) != 1:
            raise ValueError(f"Expected one visible actual label: {label}")
        node = nodes[0]
        while node is not None and node.get("clickable") != "true":
            node = parents.get(node)
        if node is None or node.get("enabled") != "true":
            raise ValueError(f"No actual enabled action: {label}")
        left, top, right, bottom = bounds(node)
        command("shell", "input", "tap", str((left + right) // 2), str((top + bottom) // 2))

    def swipe():
        root, _ = tree()
        scrolls = [n for n in root.iter("node") if n.get("scrollable") == "true"]
        left, top, right, bottom = bounds(scrolls[-1])
        x = (left + right) // 2
        command(
            "shell",
            "input",
            "swipe",
            str(x),
            str(int(top + 0.8 * (bottom - top))),
            str(x),
            str(int(top + 0.2 * (bottom - top))),
            "400",
        )

    def capture(name, required):
        root, xml = tree()
        labels = [n.get("text") or n.get("content-desc") for n in root.iter("node")]
        args.output.joinpath(name + ".xml").write_text(xml, encoding="utf-8")
        args.output.joinpath(name + ".png").write_bytes(
            subprocess.check_output([*adb, "exec-out", "screencap", "-p"])
        )
        for label in required:
            if not any(label in text for text in labels if text):
                raise AssertionError(f"Actual native content missing: {label}")
        return {"name": name, "required_native_labels": required}

    records = []
    with httpx.Client(
        base_url=args.api_url, headers={"X-User-ID": args.user_id}, timeout=30
    ) as client:
        before_response = client.get(f"/v1/threads/{args.thread_id}")
        before_response.raise_for_status()
        before = before_response.json()
        try:
            root, _ = tree()
            if any(n.get("text") == "继续任务" for n in root.iter("node")):
                tap("继续任务")
            for scale in ("1.0", "2.0"):
                command("shell", "settings", "put", "system", "font_scale", scale)
                records.append(
                    capture(
                        f"font-{scale}-main",
                        ["01 / 03", "查看来源与依据", "加入比较", "保存候选", "加入待购", "¥"],
                    )
                )
                tap("查看来源与依据")
                records.append(capture(f"font-{scale}-evidence-top", ["证据来源", "关闭依据"]))
                for _ in range(2):
                    swipe()
                records.append(capture(f"font-{scale}-evidence-facts", ["不代表真实库存"]))
                tap("关闭依据")
                swipe()
                records.append(
                    capture(f"font-{scale}-secondary", ["02 / 03", "加入比较", "保存候选"])
                )
                swipe()
                records.append(capture(f"font-{scale}-third", ["03 / 03", "加入比较", "保存候选"]))
                tap("返回 Mission 对话")
                tap("查看当前推荐")
        finally:
            command("shell", "settings", "put", "system", "font_scale", original_font)
        after_response = client.get(f"/v1/threads/{args.thread_id}")
        after_response.raise_for_status()
        after = after_response.json()
    if before != after:
        raise AssertionError("Native viewing changed the authoritative ThreadSnapshot")
    return {
        "scope": "Existing real API state; read-only navigation, not full Agent scenario or TalkBack signoff",
        "passed": True,
        "records": records,
        "snapshot_unchanged": True,
        "restored_font": command("shell", "settings", "get", "system", "font_scale"),
        "new_runs": 0,
        "model_calls": 0,
    }


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--adb", type=Path, required=True)
    parser.add_argument("--serial", required=True)
    parser.add_argument("--api-url", required=True)
    parser.add_argument("--user-id", required=True)
    parser.add_argument("--thread-id", required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    args.output.mkdir(parents=True, exist_ok=False)
    report = inspect(args)
    args.output.joinpath("summary.json").write_text(
        json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    print(
        json.dumps(
            {
                "passed": report["passed"],
                "captures": len(report["records"]),
                "snapshot_unchanged": report["snapshot_unchanged"],
            }
        )
    )


if __name__ == "__main__":
    main()
