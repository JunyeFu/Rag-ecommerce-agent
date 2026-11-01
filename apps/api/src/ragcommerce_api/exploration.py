"""Explicit, catalog-grounded discovery transitions; never commercial writes."""

from dataclasses import replace

from ragcommerce_contracts import ExplorationAction, ExplorationDirection, ExplorationState


def catalog_directions(rows) -> list[ExplorationDirection]:
    groups = {}
    for row in rows:
        for scenario in row["scenarios"]:
            groups.setdefault((row["category"], scenario), []).append(row)
    result = []
    for (category, scenario), products in groups.items():
        try_first, to_confirm = {
            "手机": (
                "先用现有手机尝试一次这个场景，记下真正不方便的地方。",  # noqa: RUF001
                "已有设备是否已经够用；预算和便携要求待你确认。",  # noqa: RUF001
            ),
            "电脑": (
                "先用现有电脑完成一段实际任务，记录卡在哪里。",  # noqa: RUF001
                "软件需求、携带频率和预算待你确认，不推断性能。",  # noqa: RUF001
            ),
            "耳机": (
                "先观察一次通勤或工作时最影响你的声音和佩戴问题。",
                "佩戴形式、舒适度和使用环境待你确认。",
            ),
            "相机": (
                "先用手头手机拍一次同样的场景，再决定是否需要额外设备。",  # noqa: RUF001
                "是否愿意学习操作和携带设备；预算待你确认。",  # noqa: RUF001
            ),
        }[category]
        result.append(
            ExplorationDirection(
                direction_id=f"{category}:{scenario}",
                title=scenario,
                category=category,
                experience_tags=[
                    "novelty"
                    if scenario in {"移动摄影", "视频创作", "旅行记录"}
                    else "life_improvement"
                ],
                evidence_refs=list(
                    dict.fromkeys(ref for p in products[:3] for ref in p["evidence_refs"])
                ),
                supporting_product_ids=[p["product_id"] for p in products[:3]],
                scenario_hint=f"从{scenario}这个使用场景开始探索，不必立即购买{category}。",  # noqa: RUF001 — Chinese product copy
                try_first=try_first,
                to_confirm=to_confirm,
            )
        )
    return result


def transition(thread, action: ExplorationAction, expected_version: int, directions):
    from .service import DecisionConflict

    if expected_version != thread.mission_version:
        raise DecisionConflict("Exploration belongs to an earlier Mission version")
    kind = action.kind
    if action.outcome is not None and kind != "end":
        raise ValueError("outcome is allowed only when ending exploration")
    needs_direction = kind in {"feedback", "select_for_purchase"}
    if (action.direction_id is not None) != needs_direction:
        raise ValueError("direction_id is required only for feedback and selection")
    if (action.value is not None) != (kind == "feedback"):
        raise ValueError("value is required only for feedback")
    if action.experience_tags and kind != "start":
        raise ValueError("experience_tags are allowed only at start")
    if len(set(action.experience_tags)) != len(action.experience_tags):
        raise ValueError("experience_tags must be unique")
    state = ExplorationState.model_validate(thread.exploration or {})
    if kind == "start":
        if thread.mode == "DISCOVERY" and not state.ended:
            raise ValueError("Exploration is already active")
        state = ExplorationState(experience_tags=action.experience_tags)
    elif thread.mode != "DISCOVERY" or state.ended:
        raise ValueError("Start exploration before using its actions")
    available = {d.direction_id: d for d in directions}
    if needs_direction and (
        action.direction_id
        not in {*state.shown_direction_ids, *(d.direction_id for d in state.directions)}
        or action.direction_id not in available
    ):
        raise ValueError("Direction was not offered in this conversation")
    if kind == "feedback":
        if action.value == "neutral":
            state.feedback.pop(action.direction_id, None)
            # Undo makes this direction eligible again, but unseen directions remain first.
            if action.direction_id in state.shown_direction_ids:
                state.shown_direction_ids.remove(action.direction_id)
        else:
            state.feedback[action.direction_id] = action.value
    if kind in {"start", "next"}:
        eligible = [
            d
            for d in directions
            if state.feedback.get(d.direction_id) != "not_interested"
            and d.direction_id not in state.shown_direction_ids
            and (not state.experience_tags or set(d.experience_tags) & set(state.experience_tags))
        ]
        # Prefer a different category and uncovered products within each page.
        picked = []
        liked_categories = {
            available[key].category
            for key, value in state.feedback.items()
            if value == "interested" and key in available
        }
        while eligible and len(picked) < 3:
            eligible.sort(
                key=lambda d: (
                    any(p.category == d.category for p in picked),
                    all(p in state.shown_product_ids for p in d.supporting_product_ids),
                    bool(picked)
                    and all(
                        tag in {t for p in picked for t in p.experience_tags}
                        for tag in d.experience_tags
                    ),
                    bool(liked_categories) and d.category not in liked_categories,
                )
            )
            picked.append(eligible.pop(0))
        state.directions = picked
        state.exhausted = not picked
        state.shown_direction_ids.extend(d.direction_id for d in picked)
        state.shown_product_ids = list(
            dict.fromkeys(
                [
                    *state.shown_product_ids,
                    *(p for d in picked for p in d.supporting_product_ids),
                ]
            )
        )
    mode, goal = "DISCOVERY", "随便看看: 发现适合自己的使用方向"
    if kind == "select_for_purchase":
        if state.feedback.get(action.direction_id) == "not_interested":
            raise ValueError("Undo negative feedback before selecting this direction")
        selected = available[action.direction_id]
        state.selected_direction_id = selected.direction_id
        mode, goal = "PURCHASE", f"想选{selected.category}, 主要用途是{selected.title}"
    if kind == "end":
        state.ended = True
        state.outcome = action.outcome or "UNDECIDED"
    return replace(
        thread,
        goal=goal,
        mode=mode,
        exploration=state.model_dump(mode="json"),
        mission_version=thread.mission_version + 1,
        selected_product_ids=(),
    )


def result_for(thread):
    return {
        "mode": thread.mode,
        "exploration": thread.exploration,
        "mission_version": thread.mission_version,
    }
