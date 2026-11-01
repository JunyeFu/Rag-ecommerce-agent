"""Installed TalkBack acceptance using emulator hardware input and a passive native observer."""

from __future__ import annotations

import argparse
import json
import re
import subprocess
import time
from datetime import UTC, datetime
from pathlib import Path
from urllib.request import Request, urlopen
from uuid import uuid4

from emulator_hardware import EmulatorHardware
from run_android_instrumentation_case import instrumentation_result

ADB = "C:/Users/fujunye/AppData/Local/Android/Sdk/platform-tools/adb.exe"
PACKAGE = "com.ragcommerce.agent.talkbackreview"
SERVICE = "com.google.android.marvin.talkback/com.google.android.marvin.talkback.TalkBackService"


class TalkBack:
    def __init__(self, serial: str, output: Path, input_mode: str = "touchscreen"):
        self.serial = serial
        self.output = output
        self.session = "qa_" + uuid4().hex
        self.relative = f"files/talkback/{self.session}"
        self.actions: list[dict] = []
        self.checks: list[dict] = []
        self.input_mode = input_mode
        self._hardware = None

    @property
    def hardware(self):
        if self._hardware is None:
            self._hardware = EmulatorHardware()
        return self._hardware

    def adb(self, *args: str, check: bool = True, binary: bool = False):
        result = subprocess.run(
            [ADB, "-s", self.serial, *args],
            capture_output=True,
            text=not binary,
            encoding=None if binary else "utf-8",
            timeout=30,
        )
        if check and result.returncode:
            raise RuntimeError(f"ADB failed: {' '.join(args[:4])}: {result.stderr}")
        return result

    def snapshot(self) -> dict:
        result = self.adb(
            "shell", "run-as", PACKAGE, "cat", f"{self.relative}/state.json", check=False
        )
        return json.loads(result.stdout) if result.returncode == 0 and result.stdout else {}

    def wait(self, predicate, message: str, seconds: float = 15) -> dict:
        deadline = time.monotonic() + seconds
        while time.monotonic() < deadline:
            state = self.snapshot()
            if state and predicate(state):
                return state
            time.sleep(0.2)
        raise AssertionError(message)

    def start(self, launch: bool):
        avd = self.adb("emu", "avd", "name").stdout.splitlines()[0]
        if avd != "Pixel_9a":
            raise RuntimeError(f"QA belongs to Pixel_9a, not {avd}")
        self.output.mkdir(parents=True, exist_ok=False)
        self.process = subprocess.Popen(
            [
                ADB,
                "-s",
                self.serial,
                "shell",
                "am",
                "instrument",
                "-w",
                "-r",
                "-e",
                "class",
                "com.ragcommerce.agent.TalkBackTraversalTest#observeNativeTalkBack",
                "-e",
                "talkBackQa",
                "1",
                "-e",
                "qaSession",
                self.session,
                "-e",
                "launchApp",
                "1" if launch else "0",
                f"{PACKAGE}.test/androidx.test.runner.AndroidJUnitRunner",
            ],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            encoding="utf-8",
        )
        self.wait(
            lambda s: (
                any(n.get("package") == PACKAGE for n in s["nodes"])
                if launch
                else bool(s.get("nodes"))
            ),
            "Native observer did not reach its target window",
        )
        if launch:
            self.wait(
                lambda s: any(self.visible(label, s) for label in ("已连接", "已恢复", "连接中断")),
                "Initial connection and task restoration did not settle",
            )

    def key(self, *keys: str, delay: float = 0.45) -> dict:
        hardware = self.hardware
        codes = {
            "LEFTALT": 56,
            "LEFTCTRL": 29,
            "LEFT": 105,
            "RIGHT": 106,
            "ENTER": 28,
            "BACKSPACE": 14,
        }
        try:
            for key in keys:
                hardware.key(codes[key], True)
            time.sleep(0.04)
        finally:
            for key in reversed(keys):
                hardware.key(codes[key], False)
        time.sleep(delay)
        state = self.snapshot()
        self.actions.append(
            {
                "input": "emulator_hardware_keyboard",
                "keys": keys,
                "focus": state.get("focus"),
                "event_count": state.get("event_count"),
            }
        )
        return state

    def mouse(self, x: int, y: int, pressed: bool):
        self.hardware.touch([(0, x, y, 1024 if pressed else 0)])

    def focus_after_input(self, before: dict):
        start = before.get("event_count", 0)
        deadline = time.monotonic() + 3
        state = before
        while time.monotonic() < deadline:
            state = self.snapshot()
            focus = state.get("focus") or {}
            focused_events = [e for e in state.get("events", [])[start:] if e["type"] == 32768]
            if focused_events:
                source = focused_events[-1].get("source") or {}
                if all(focus.get(key) == source.get(key) for key in ("label", "class", "bounds")):
                    return state
            time.sleep(0.1)
        # End-of-window produces no new focus. The caller records that boundary.
        return state

    def next(self, reverse: bool = False) -> dict:
        before = self.snapshot()
        if self.input_mode == "keyboard":
            self.key("LEFTALT", "LEFT" if reverse else "RIGHT", delay=0)
            return self.focus_after_input(before)
        start, end = (720, 360) if reverse else (360, 720)
        for x in (start, (start + end) // 2, end):
            self.mouse(x, 1100, True)
            time.sleep(0.025)
        self.mouse(end, 1100, False)
        state = self.focus_after_input(before)
        self.actions.append(
            {
                "input": "emulator_hardware_touchscreen",
                "gesture": "previous" if reverse else "next",
                "focus": state.get("focus"),
                "event_count": state.get("event_count"),
            }
        )
        return state

    def first(self):
        if self.input_mode == "keyboard":
            before = self.snapshot()
            self.key("LEFTALT", "LEFTCTRL", "LEFT", delay=0)
            return self.focus_after_input(before)
        # Touch exploration starts at the top visible native text; no direct focus action.
        nodes = [
            n
            for n in self.snapshot()["nodes"]
            if n.get("package") == PACKAGE
            and n.get("label")
            and n.get("class") == "android.widget.TextView"
            and n["bounds"][3] > n["bounds"][1]
            and n["bounds"][1] >= 60
        ]
        first = min(nodes, key=lambda n: (n["bounds"][1], n["bounds"][0]))
        left, top, right, bottom = first["bounds"]
        self.mouse((left + right) // 2, (top + bottom) // 2, True)
        self.mouse((left + right) // 2, (top + bottom) // 2, False)
        time.sleep(0.5)
        return self.snapshot()

    def seek(
        self, label: str, *, contains: bool = False, limit: int = 100, actionable: bool = False
    ):
        reverse = False
        unchanged = 0
        previous = None
        for _ in range(limit):
            state = self.snapshot()
            focus = state.get("focus") or {}
            value = focus.get("label", "")
            if (
                focus.get("enabled")
                and (not actionable or 16 in focus.get("actions", []))
                and (label in value if contains else label == value)
            ):
                return state
            identity = (value, tuple(focus.get("bounds", [])), focus.get("class"))
            unchanged = unchanged + 1 if identity == previous else 0
            if unchanged >= 2:
                if reverse:
                    break
                reverse, unchanged = True, 0
            previous = identity
            self.next(reverse=reverse)
        raise AssertionError(f"TalkBack could not naturally reach {label!r}")

    def activate(self, label: str, *, contains: bool = False):
        before = self.seek(label, contains=contains, actionable=True)
        if self.input_mode == "keyboard":
            self.key("LEFTALT", "ENTER")
        else:
            self.mouse(540, 1100, True)
            self.mouse(540, 1100, False)
            time.sleep(0.07)
            self.mouse(540, 1100, True)
            self.mouse(540, 1100, False)
            time.sleep(0.6)
        after = self.snapshot()
        self.checks.append(
            {
                "action": "TalkBack activate",
                "target": label,
                "focused_before": before.get("focus"),
                "focus_after": after.get("focus"),
            }
        )
        return after

    def visible(self, text: str, state: dict | None = None):
        return any(
            text in node.get("label", "")
            and (
                node.get("clickable")
                or node.get("editable")
                or node.get("class") == "android.widget.TextView"
            )
            for node in (state or self.snapshot()).get("nodes", [])
        )

    def tab(self, label: str):
        if any(n.get("label") == label and n.get("selected") for n in self.snapshot()["nodes"]):
            return
        self.activate(label)

    def start_task(self):
        self.tab("任务")
        if self.visible("已恢复"):
            if not self.visible("继续任务"):
                self.page()
            self.activate("继续任务")
            self.wait(lambda s: not self.visible("安全恢复点", s), "Recovery was not continued")
        if self.visible("返回 Mission 对话"):
            self.activate("返回 Mission 对话")
        if self.visible("新建任务"):
            self.activate("新建任务")

    def rank(self, label: str, state: dict):
        return any(
            n.get("class") == "android.widget.TextView"
            and label in [part.strip() for part in n.get("label", "").split("·")]
            for n in state["nodes"]
        )

    def owner(self):
        payload = self.adb(
            "exec-out",
            "run-as",
            PACKAGE,
            "cat",
            "files/datastore/shopping_settings.preferences_pb",
            binary=True,
        ).stdout
        return (
            re.search(
                rb"[a-f0-9]{8}-(?:[a-f0-9]{4}-){3}[a-f0-9]{12}",
                payload[payload.index(b"install_user_id") :],
            )
            .group()
            .decode()
        )

    def api(self, path: str):
        request = Request("http://127.0.0.1:20882/" + path, headers={"X-User-ID": self.owner()})
        with urlopen(request, timeout=10) as response:
            return json.load(response)

    def page(self, down: bool = False):
        hardware = self.hardware
        targets = [
            n
            for n in self.snapshot()["nodes"]
            if n.get("scrollable") and n.get("class") != "android.widget.HorizontalScrollView"
        ]
        pagers = [n for n in targets if 16908359 in n["actions"]]
        target = max(pagers or targets, key=lambda n: n["bounds"][3] - n["bounds"][1])
        left, top, right, bottom = target["bounds"]
        x1, x2 = left + (right - left) * 3 // 8, left + (right - left) * 5 // 8
        low, high = top + (bottom - top) // 10, bottom - (bottom - top) // 10
        start, end = (low, high) if down else (high, low)
        positions = [round(start + (end - start) * i / 5) for i in range(6)]
        try:
            for y in positions:
                hardware.touch([(7, x1, y, 1024), (8, x2, y, 1024)])
                time.sleep(0.06)
        finally:
            hardware.touch([(7, x1, positions[-1], 0), (8, x2, positions[-1], 0)])
        time.sleep(0.8)
        self.actions.append(
            {
                "input": "emulator_hardware_multitouch",
                "gesture": "two-finger down" if down else "two-finger up",
                "target_bounds": target["bounds"],
                "y_positions": positions,
            }
        )

    def to_rank(self, label: str, down: bool = False):
        for _ in range(4):
            state = self.snapshot()
            if (
                self.rank(label, state)
                and sum(self.rank(r, state) for r in ("主推荐", "次推荐", "再次推荐")) == 1
            ):
                return state
            self.page(down=down)
        return self.wait(
            lambda s: self.rank(label, s), f"Two-finger scrolling did not reach {label}"
        )

    def capture(self, name: str):
        self.adb("shell", "run-as", PACKAGE, "touch", f"{self.relative}/capture")
        time.sleep(0.7)
        result = self.adb(
            "exec-out", "run-as", PACKAGE, "cat", f"{self.relative}/screen.png", binary=True
        )
        (self.output / f"{name}.png").write_bytes(result.stdout)
        (self.output / f"{name}.json").write_text(
            json.dumps(self.snapshot(), ensure_ascii=False, indent=2), encoding="utf-8"
        )

    def finish(self):
        final = self.snapshot()
        if self.process.poll() is None:
            self.adb("shell", "run-as", PACKAGE, "touch", f"{self.relative}/stop")
        stdout, stderr = self.process.communicate(timeout=15)
        result = instrumentation_result(stdout + stderr, self.process.returncode)
        failure_summary = (
            [
                line
                for line in (stdout + stderr).splitlines()
                if any(
                    token in line
                    for token in ("shortMsg=", "Exception", "Error", "Caused by:", "\tat ")
                )
            ][:24]
            if not result["passed"]
            else []
        )
        if self._hardware is not None:
            self._hardware.channel.close()
        (self.output / "observer.json").write_text(
            json.dumps(
                {
                    "result": result,
                    "exit_code": self.process.returncode,
                    "failure_summary": failure_summary,
                    "observation_is_not_business_pass": True,
                    "last_state": final,
                },
                ensure_ascii=False,
                indent=2,
            ),
            encoding="utf-8",
        )
        return result


def probe(qa: TalkBack):
    qa.adb(
        "shell",
        "am",
        "start",
        "-a",
        "android.settings.APPLICATION_DETAILS_SETTINGS",
        "-d",
        f"package:{PACKAGE}",
    )
    qa.wait(
        lambda s: any(n.get("package") == "com.android.settings" for n in s["nodes"]),
        "Settings not visible",
    )
    qa.wait(
        lambda s: bool((s.get("focus") or {}).get("label")), "Settings initial focus did not settle"
    )
    time.sleep(1)
    before = qa.snapshot()
    qa.adb("shell", "input", "keycombination", "57", "22")
    time.sleep(1)
    injected = qa.snapshot()
    hardware = qa.next()
    qa.next()
    qa.next(reverse=True)
    qa.capture("system-input-comparison")
    assert hardware.get("focus") != injected.get("focus"), (
        "Hardware input also failed to advance TalkBack"
    )
    qa.checks.append(
        {
            "action": "input_AB_comparison",
            "before": before.get("focus"),
            "shell_injected": injected.get("focus"),
            "hardware": hardware.get("focus"),
            "shell_event_count": injected.get("event_count"),
            "hardware_event_count": hardware.get("event_count"),
        }
    )
    qa.activate("Storage", contains=True)
    qa.wait(
        lambda s: qa.visible("Clear storage", s),
        "Settings activation did not open storage controls",
    )
    qa.adb("shell", "input", "keyevent", "4")  # System Back, not a TalkBack activation claim.


def navigation(qa: TalkBack):
    # All app transitions below use TalkBack's focused activation.
    qa.start_task()
    for tab, expected in (
        ("决策", "决策工作台"),
        ("我的", "商业来源"),
        ("任务", "SHOPPING MISSION"),
    ):
        qa.activate(tab)
        qa.wait(lambda s, expected=expected: qa.visible(expected, s), f"{tab} did not open")
        initial = qa.first()
        labels = [(initial.get("focus") or {}).get("label", "")]
        focuses = [initial.get("focus") or {}]
        for _ in range(80):
            state = qa.next()
            focus = state.get("focus") or {}
            labels.append(focus.get("label", ""))
            focuses.append(focus)
            if focus.get("label") == "我的":
                break
        required = {
            "决策": ["已保存方案", "比较已选商品", "待购计划", "任务", "决策", "我的"],
            "我的": [
                "商业来源",
                "模型与数据声明",
                "删除我的数据",
                "匿名质量数据",
                "连接与恢复",
                "任务",
                "决策",
                "我的",
            ],
            "任务": [
                "最近任务",
                "添加商品图片",
                "添加语音",
                "发送",
                "改善生活",
                "发现新玩法",
                "随便看看",
                "任务",
                "决策",
                "我的",
            ],
        }[tab]
        missing = [wanted for wanted in required if not any(wanted in label for label in labels)]
        scrolls = 0
        while missing and scrolls < 4:
            # A screen-reader user scrolls the content with two fingers when
            # linear navigation reaches the fixed bottom bar before clipped content.
            qa.page()
            scrolls += 1
            initial = qa.first()
            focus = initial.get("focus") or {}
            labels.append(focus.get("label", ""))
            focuses.append(focus)
            for _ in range(80):
                focus = qa.next().get("focus") or {}
                labels.append(focus.get("label", ""))
                focuses.append(focus)
                if focus.get("label") == "我的":
                    break
            missing = [
                wanted for wanted in required if not any(wanted in label for label in labels)
            ]
        assert not missing, f"{tab}: traversal missed {missing}"
        if tab == "任务":
            for label in ("改善生活", "发现新玩法"):
                assert all(n.get("checkable") for n in focuses if n.get("label") == label), (
                    f"{label} has a redundant text focus target"
                )
        qa.next(reverse=True)
        qa.next()
        qa.checks.append(
            {
                "screen": tab,
                "forward_labels": labels,
                "required_labels": required,
                "hardware_two_finger_scrolls": scrolls,
                "reverse_then_forward": True,
            }
        )
        qa.capture("navigation-" + tab)


def dialogs(qa: TalkBack):
    qa.start_task()
    qa.tab("我的")
    qa.activate("删除我的数据")
    qa.wait(lambda s: qa.visible("确认删除", s), "Delete confirmation did not open")
    labels = []
    for _ in range(8):
        focus = qa.next().get("focus") or {}
        assert focus.get("package") == PACKAGE, "Dialog focus escaped the application"
        assert focus.get("label") not in ("任务", "决策", "我的"), (
            "Dialog focus escaped to background navigation"
        )
        labels.append(focus.get("label"))
    assert "取消" in labels and "确认删除" in labels, "Dialog actions are not reachable"
    qa.capture("delete-dialog")
    qa.activate("取消")
    qa.wait(
        lambda s: not qa.visible("确认删除", s) and qa.visible("商业来源", s),
        "Cancel did not restore profile",
    )
    restored = qa.wait(
        lambda s: bool((s.get("focus") or {}).get("label")),
        "Dialog dismissal lost accessibility focus",
    )
    qa.checks.append(
        {
            "screen": "delete-confirmation",
            "focused_labels": labels,
            "cancelled": True,
            "deletion_executed": False,
            "restored_focus": restored.get("focus"),
        }
    )
    qa.tab("任务")
    for label in ("改善生活", "发现新玩法"):
        qa.activate(label)
        qa.wait(
            lambda s: (s.get("focus") or {}).get("checkable") and not s["focus"]["checked"],
            f"{label} did not toggle off",
        )
        qa.activate(label)
        qa.wait(lambda s: (s.get("focus") or {}).get("checked"), f"{label} did not toggle on")
        qa.checks.append({"screen": "exploration", "checkbox": label, "toggle_off_on": True})
    qa.capture("exploration-single-targets")
    qa.activate("添加语音", contains=True)
    state = qa.wait(
        lambda s: qa.visible("Only this time", s) or qa.visible("用语音说出你的需求", s),
        "Voice entry or permission dialog did not open",
    )
    if qa.visible("Only this time", state):
        qa.activate("Only this time")
    qa.wait(lambda s: qa.visible("用语音说出你的需求", s), "Native voice dialog did not open")
    voice_labels = []
    for _ in range(7):
        state = qa.next()
        voice_labels.append((state.get("focus") or {}).get("label", ""))
    assert "按住录音" in voice_labels and "发送识别" in voice_labels and "取消" in voice_labels
    assert any(
        n.get("label") == "发送识别" and not n.get("enabled") and 16 not in n.get("actions", [])
        for n in state["nodes"]
    )
    qa.capture("voice-dialog-no-recording")
    qa.activate("取消")
    qa.wait(lambda s: not qa.visible("用语音说出你的需求", s), "Voice cancel did not close dialog")
    qa.checks.append(
        {
            "screen": "native-voice-dialog",
            "focused_labels": voice_labels,
            "recorded": False,
            "uploaded": False,
            "send_disabled_without_recording": True,
            "not_human_voice_acceptance": True,
        }
    )


def core(qa: TalkBack):
    before_threads = {item["thread_id"] for item in qa.api("v1/threads")}
    qa.start_task()
    qa.activate("例如", contains=True)
    qa.adb("shell", "input", "text", "Nova%sMobile%sPulse%s01%s3000")
    qa.adb("shell", "input", "keyevent", "4")
    qa.activate("发送")
    qa.wait(
        lambda s: qa.rank("主推荐", s),
        "Real HTTP fixture did not produce recommendations",
        seconds=30,
    )
    new_threads = [item for item in qa.api("v1/threads") if item["thread_id"] not in before_threads]
    assert len(new_threads) == 1, "Native submission did not create exactly one owned thread"
    thread_id = new_threads[0]["thread_id"]
    qa.activate("加入比较", contains=True)
    qa.wait(lambda s: (s.get("focus") or {}).get("checked"), "Primary product was not selected")
    qa.capture("primary-selected")
    first_selection = set(qa.api("v1/threads/" + thread_id)["selected_product_ids"])
    assert len(first_selection) == 1
    qa.to_rank("次推荐")
    qa.activate("加入比较", contains=True)
    qa.wait(lambda s: (s.get("focus") or {}).get("checked"), "Secondary product was not selected")
    qa.capture("secondary-selected")
    second_selection = set(qa.api("v1/threads/" + thread_id)["selected_product_ids"])
    assert len(second_selection) == 2 and len(second_selection - first_selection) == 1
    secondary_id = next(iter(second_selection - first_selection))
    variant_id = qa.api("v1/products/" + secondary_id)["variant_id"]
    qa.activate("查看来源与依据")
    qa.wait(lambda s: qa.visible("证据来源", s), "Evidence dialog did not open")
    qa.activate("关闭依据")
    before_save = qa.api("v1/lists")
    qa.activate("保存候选")
    qa.activate("取消")
    assert qa.api("v1/lists") == before_save, "Cancelling save changed the owned list"
    qa.activate("保存候选")
    qa.activate("确认保存")
    qa.activate("加入待购")
    qa.activate("确认加入")
    qa.to_rank("再次推荐")
    qa.capture("tertiary")
    qa.to_rank("次推荐", down=True)
    qa.wait(
        lambda s: qa.rank("次推荐", s) and not qa.rank("再次推荐", s),
        "Reverse scroll did not return to secondary",
    )
    qa.activate("返回 Mission 对话")
    qa.activate("决策")
    qa.wait(lambda s: qa.visible("决策工作台", s), "Decision screen did not restore comparison")
    snapshot = qa.api("v1/threads/" + thread_id)
    assert snapshot["status"] == "COMPLETED" and len(snapshot["selected_product_ids"]) == 2
    lists = qa.api("v1/lists")["lists"]
    cart = qa.api("v1/cart")["items"]
    assert any(variant_id in item["variant_ids"] for item in lists) and any(
        item["product"]["product_id"] == secondary_id for item in cart
    ), "Confirmed writes are absent from the same owner's API state"
    qa.checks.append(
        {
            "owner_id": qa.owner(),
            "thread_id": snapshot["thread_id"],
            "status": snapshot["status"],
            "selected_product_ids": snapshot["selected_product_ids"],
            "saved_variants": sum(len(item["variant_ids"]) for item in lists),
            "waiting_items": len(cart),
            "backend": "in-memory HTTP fixture; not PostgreSQL",
        }
    )
    qa.capture("comparison-return")
    qa.checks.append(
        {
            "screen": "vertical-recommendations",
            "primary_secondary_tertiary_reverse": True,
            "primary_and_secondary_selected": True,
            "returned_to_decisions": True,
            "backend": "explicit fake HTTP fixture; no PostgreSQL durability claim",
        }
    )


def main():
    global PACKAGE
    parser = argparse.ArgumentParser()
    parser.add_argument("--serial", required=True)
    parser.add_argument("--package", default=PACKAGE)
    parser.add_argument("--flow", choices=["probe", "navigation", "dialogs", "core"], required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--scale", choices=["1.0", "2.0"], default="1.0")
    parser.add_argument("--input", choices=["touchscreen", "keyboard"], default="touchscreen")
    args = parser.parse_args()
    PACKAGE = args.package
    if args.output.exists():
        parser.error("Choose a new output directory; previous attempts must be retained")
    qa = TalkBack(args.serial, args.output, args.input)
    started = datetime.now(UTC).isoformat()
    passed, error = False, None
    observer = None
    original_scale = None
    try:
        original_scale = qa.adb("shell", "settings", "get", "system", "font_scale").stdout.strip()
        qa.adb("shell", "settings", "put", "system", "font_scale", args.scale)
        qa.start(launch=args.flow != "probe")
        {"probe": probe, "navigation": navigation, "dialogs": dialogs, "core": core}[args.flow](qa)
        passed = True
    except Exception as exc:
        error = f"{type(exc).__name__}: {exc}"
        if qa.snapshot():
            qa.capture("failure")
    finally:
        if hasattr(qa, "process"):
            observer = qa.finish()
        if original_scale is not None:
            qa.adb("shell", "settings", "put", "system", "font_scale", original_scale)
        report = {
            "schema_version": 1,
            "started_at": started,
            "finished_at": datetime.now(UTC).isoformat(),
            "flow": args.flow,
            "serial": args.serial,
            "package": PACKAGE,
            "passed": passed and bool(observer and observer["passed"]),
            "error": error,
            "observer": observer,
            "checks": qa.checks,
            "actions": qa.actions,
            "mimo_calls": 0,
            "input": "emulator hardware events; installed TalkBack",
        }
        report.update(
            font_scale=args.scale, restored_font_scale=original_scale, input_mode=args.input
        )
        args.output.mkdir(parents=True, exist_ok=True)
        (args.output / "result.json").write_text(
            json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8"
        )
        print(
            json.dumps(
                {k: report[k] for k in ("flow", "passed", "error", "observer", "mimo_calls")},
                ensure_ascii=False,
            )
        )
    return 0 if report["passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
