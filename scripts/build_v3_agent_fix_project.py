"""Build a Microsoft Project XML schedule for the audited V3 Agent gaps."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime, time, timedelta
from pathlib import Path
from xml.etree import ElementTree as ET

ROOT = Path(__file__).resolve().parents[1]
OUTPUT = ROOT / "docs/project/V3-agent-gap-fix.xml"
NS = "http://schemas.microsoft.com/project"
ET.register_namespace("", NS)


@dataclass(frozen=True)
class FixTask:
    code: str
    name: str
    days: int
    priority: str
    defect: str
    acceptance: str


TASKS = (
    FixTask("F01", "冻结缺陷与验收样例", 1, "P0", "D01-D06", "每个缺陷有可复现失败样例和验收断言"),
    FixTask("F02", "Agent 清单工具真实写入", 2, "P0", "D01", "审批后写入本人清单, API 刷新可见"),
    FixTask(
        "F03", "Agent 待购工具真实写入", 2, "P0", "D01", "审批后写入本人待购, 重复调用不重复写入"
    ),
    FixTask(
        "F04",
        "写操作审批与幂等集成测试",
        2,
        "P0",
        "D01",
        "拒绝、恢复和 Worker 重复领取均不产生越权写入",
    ),
    FixTask(
        "F05",
        "报价证据字段与缺失证据语义",
        2,
        "P0",
        "D02",
        "金额、商家、库存和来源有报价证据, 时效有本次采集元数据",
    ),
    FixTask("F06", "报价事实回归和 P0 门禁", 1, "P0", "D02", "无来源或过期报价不能显示为已验证"),
    FixTask(
        "F07",
        "真实 Provider 澄清与规划",
        2,
        "P1",
        "D03",
        "模型能按目标选择澄清或工具, 事实读取边界仍有效",
    ),
    FixTask(
        "F08",
        "重规划与审批恢复场景",
        2,
        "P1",
        "D03",
        "新增澄清、重新询价和审批恢复场景有独立真实评测",
    ),
    FixTask(
        "F09",
        "真实 Embedding 接入持久化检索",
        2,
        "P1",
        "D04",
        "显式真实模式使用 Embedding 与 Qdrant 投影",
    ),
    FixTask("F10", "RAG 消融和 P1 门禁", 2, "P1", "D04", "BM25、向量、融合结果分别留存并校验来源"),
    FixTask(
        "F13", "文档与 Java 21 证据对齐", 1, "P1", "D06", "三入口、工具链和发布状态与当前实现一致"
    ),
    FixTask(
        "F14",
        "P0/P1 全链回归与验收",
        2,
        "P0",
        "D01-D04,D06",
        "API、Worker、RAG、Android 与文档验收通过",
    ),
    FixTask(
        "F11",
        "弱权威演示查价接入",
        2,
        "P2",
        "D05",
        "仅使用 THIRD_PARTY_DEMO, 失败明确可见, 需沙箱凭据",
    ),
    FixTask(
        "F12", "Android 报价级别与错误状态", 1, "P2", "D05", "区分 fixture、第三方演示、过期和失败"
    ),
)

HOLIDAYS = {
    date(2026, 9, 25): "中秋节",
    **{date(2026, 10, day): "国庆节" for day in range(1, 8)},
}
EXTRA_WORKDAYS = {date(2026, 10, 10): "国庆节调休工作日"}
START = date(2026, 9, 22)


def tag(name: str) -> str:
    return f"{{{NS}}}{name}"


def add(parent: ET.Element, name: str, value: object) -> ET.Element:
    element = ET.SubElement(parent, tag(name))
    element.text = str(value)
    return element


def stamp(day: date, hour: int) -> str:
    return datetime.combine(day, time(hour)).isoformat()


def working(day: date) -> bool:
    return day in EXTRA_WORKDAYS or (day not in HOLIDAYS and day.weekday() < 5)


def next_workday(day: date) -> date:
    day += timedelta(days=1)
    while not working(day):
        day += timedelta(days=1)
    return day


def calendar(root: ET.Element) -> None:
    calendars = ET.SubElement(root, tag("Calendars"))
    cal = ET.SubElement(calendars, tag("Calendar"))
    add(cal, "UID", 1)
    add(cal, "Name", "V3 修复单人工作日历")
    add(cal, "IsBaseCalendar", 1)
    add(cal, "BaseCalendarUID", -1)
    weekdays = ET.SubElement(cal, tag("WeekDays"))
    for day_type in range(1, 8):  # 1=Sunday, 2=Monday, ..., 7=Saturday
        weekday = ET.SubElement(weekdays, tag("WeekDay"))
        is_workday = 2 <= day_type <= 6
        add(weekday, "DayType", day_type)
        add(weekday, "DayWorking", int(is_workday))
        if is_workday:
            working_times(weekday)
    exceptions = ET.SubElement(cal, tag("Exceptions"))
    for day, name in sorted(HOLIDAYS.items()):
        exception(exceptions, day, name, False)
    for day, name in sorted(EXTRA_WORKDAYS.items()):
        exception(exceptions, day, name, True)


def working_times(parent: ET.Element) -> None:
    times = ET.SubElement(parent, tag("WorkingTimes"))
    for start, finish in (("08:00:00", "12:00:00"), ("13:00:00", "17:00:00")):
        period = ET.SubElement(times, tag("WorkingTime"))
        add(period, "FromTime", start)
        add(period, "ToTime", finish)


def exception(parent: ET.Element, day: date, name: str, is_workday: bool) -> None:
    item = ET.SubElement(parent, tag("Exception"))
    add(item, "EnteredByOccurrences", 0)
    period = ET.SubElement(item, tag("TimePeriod"))
    add(period, "FromDate", stamp(day, 0))
    add(period, "ToDate", f"{day.isoformat()}T23:59:00")
    add(item, "Occurrences", 1)
    add(item, "Name", name)
    add(item, "Type", 1)
    add(item, "DayWorking", int(is_workday))
    if is_workday:
        working_times(item)


def task_element(
    parent: ET.Element,
    uid: int,
    name: str,
    start: date,
    finish: date,
    days: int,
    priority: str,
    notes: str,
    predecessor: int | None,
    milestone: bool = False,
) -> None:
    task = ET.SubElement(parent, tag("Task"))
    for field, value in (
        ("UID", uid),
        ("ID", uid),
        ("Name", name),
        ("OutlineLevel", 1),
        ("Priority", {"P0": 1000, "P1": 750, "P2": 500}[priority]),
        ("Start", stamp(start, 17 if milestone else 8)),
        ("Finish", stamp(finish, 17)),
        ("Duration", f"PT{days * 8}H0M0S"),
        ("DurationFormat", 7),
        ("Work", f"PT{days * 8}H0M0S"),
        ("Milestone", int(milestone)),
        ("Summary", 0),
        ("PercentComplete", 0),
        ("CalendarUID", 1),
        ("Notes", notes),
    ):
        add(task, field, value)
    if predecessor is not None:
        link = ET.SubElement(task, tag("PredecessorLink"))
        add(link, "PredecessorUID", predecessor)
        add(link, "Type", 1)  # Finish-to-start


def build() -> tuple[ET.Element, list[tuple[int, int]]]:
    root = ET.Element(tag("Project"))
    for field, value in (
        ("SaveVersion", 14),
        ("Name", "V3 Agent 差距修复排期"),
        ("ScheduleFromStart", 1),
        ("StartDate", stamp(START, 8)),
        ("FinishDate", stamp(date(2026, 10, 30), 17)),
        ("FYStartDate", 1),
        ("CurrencyDigits", 2),
        ("CurrencySymbol", "¥"),
        ("CurrencyCode", "CNY"),
        ("CurrencySymbolPosition", 0),
        ("CalendarUID", 1),
        ("DefaultStartTime", "08:00:00"),
        ("DefaultFinishTime", "17:00:00"),
        ("MinutesPerDay", 480),
        ("MinutesPerWeek", 2400),
        ("DaysPerMonth", 20),
    ):
        add(root, field, value)
    calendar(root)
    tasks = ET.SubElement(root, tag("Tasks"))
    assignments: list[tuple[int, int]] = []
    day = START
    uid = 1
    predecessor = None
    for item in TASKS:
        start = day
        for _ in range(item.days - 1):
            day = next_workday(day)
        finish = day
        task_element(
            tasks,
            uid,
            f"{item.code} {item.name}",
            start,
            finish,
            item.days,
            item.priority,
            f"缺陷: {item.defect}。验收: {item.acceptance}。",
            predecessor,
        )
        assignments.append((uid, item.days))
        predecessor = uid
        uid += 1
        if item.code in {"F06", "F10", "F14", "F12"}:
            stage = {
                "F06": "P0 状态与报价事实门禁",
                "F10": "P1 Agent 与 RAG 门禁",
                "F14": "P0/P1 高优先级验收",
                "F12": "P2 演示查价补充验收",
            }[item.code]
            task_element(
                tasks,
                uid,
                stage,
                finish,
                finish,
                0,
                item.priority,
                item.acceptance,
                predecessor,
                True,
            )
            predecessor = uid
            uid += 1
        day = next_workday(day)
    if finish != date(2026, 10, 30) or sum(item.days for item in TASKS) != 24:
        raise ValueError("schedule no longer matches the reviewed plan")

    resources = ET.SubElement(root, tag("Resources"))
    resource = ET.SubElement(resources, tag("Resource"))
    for field, value in (
        ("UID", 1),
        ("ID", 1),
        ("Name", "单人开发"),
        ("Type", 1),
        ("MaxUnits", 1),
        ("CalendarUID", 1),
    ):
        add(resource, field, value)
    assigned = ET.SubElement(root, tag("Assignments"))
    for assignment_uid, (task_uid, days) in enumerate(assignments, start=1):
        assignment = ET.SubElement(assigned, tag("Assignment"))
        for field, value in (
            ("UID", assignment_uid),
            ("TaskUID", task_uid),
            ("ResourceUID", 1),
            ("Units", 1),
            ("Work", f"PT{days * 8}H0M0S"),
        ):
            add(assignment, field, value)
    return root, assignments


if __name__ == "__main__":
    project, assigned = build()
    ET.indent(project)
    OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    ET.ElementTree(project).write(OUTPUT, encoding="utf-8", xml_declaration=True)
    print(
        f"{OUTPUT}: {len(TASKS)} work tasks, 4 milestones, {len(assigned)} assignments, 24 person-days"
    )
