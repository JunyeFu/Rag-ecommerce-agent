"""
LLM prompt construction for recommendation generation.

Extracted from agent.py.
"""
import logging

from app.services.slot_management import _build_exclusion_hint

logger = logging.getLogger("agent")


def _build_generation_prompt(message: str, slots: dict, valid_ranked: list, is_reliable: bool, intent: str, history: list[dict] | None = None) -> str:
    """构建 LLM 生成推荐回复的 prompt（统一版本，支持多轮上下文）"""
    reliability_hint = ""
    if not is_reliable:
        reliability_hint = "\n⚠️ 注意：以下商品与用户需求的匹配度较低，请在回复中诚实告知用户，建议其调整搜索条件。\n"

    scenario_hint = ""
    if intent == "scenario_shopping":
        scene = slots.get("scenario", "") or "购物场景"
        # 从排序结果中提取实际品类名用于动态示例
        scene_categories = list(dict.fromkeys(
            r.get("category", "") for r in valid_ranked if r.get("category")
        ))
        cat_example = "+".join(scene_categories[:4]) if len(scene_categories) >= 2 else "品类1+品类2"
        scenario_hint = (
            f"场景化推荐模式：用户场景为「{scene}」，商品已按品类多样化筛选。\n"
            "请按品类分组推荐（每个品类介绍 1 款最优商品），说明每件商品在该场景中的角色与搭配逻辑。\n"
            f"开头用一句话概述搭配方案（如'为您搭配{scene}方案：{cat_example}'），再逐品展开。\n"
            "严禁编造不存在的品类组合 - 只能基于下方检索到的实际商品及其品类。\n"
        )

    # 多轮对话历史
    history_text = ""
    if history:
        history_lines = []
        for h in history:
            role_label = "用户" if h["role"] == "user" else "助手"
            history_lines.append(f"{role_label}：{h['content']}")
        history_text = "\n对话历史：\n" + "\n".join(history_lines) + "\n\n请结合以上对话历史理解当前用户需求。比如用户说「便宜一点的」是在前面推荐的基础上筛选，用户说「要红色的」是在补充颜色偏好。如果当前问题含义模糊，根据历史推断具体意图。\n"

    context_parts = []
    for i, r in enumerate(valid_ranked):
        match_pct = round(r.get("match_score", 0) * 100)
        context_parts.append(
            f"[{i+1}] {r.get('title')} | ¥{r.get('price')} | ★{r.get('rating')} | "
            f"品类:{r.get('category','?')} | 匹配度{match_pct}% | {' '.join(r.get('highlights', [])[:2])} | {r.get('rank_reason', '')}"
        )
    context = "\n".join(context_parts)
    n = len(valid_ranked)

    # 场景模式使用独立的输出格式指令
    if intent == "scenario_shopping":
        format_section = f"""输出格式要求（场景推荐专用，严格遵守）：

第一步：开头用一句话概述搭配方案（用检索到的品类名替换），以句号结尾。
第二步：按品类分组推荐，每组用「品类名·商品N」独占一行作为标题。
第三步：以「结语」收尾，简短追问用户偏好（1句话，不超过20字）。

每款商品的展开格式：
「品类名·商品N」
商品全名 | 综合匹配度 XX%（使用检索数据中的匹配度数值，如实输出）
① 搭配角色：该商品在场景中的作用与价值
② 品质亮点：核心卖点与关键参数
③ 适用场景：在场景中的具体使用时机

要求：
- 必须逐一推荐以上全部 {n} 款商品，不可跳过任何一款
- 每款商品必须独占一行使用「品类名·商品N」标记
- 品类名从检索数据中提取，不得编造
- 总字数控制在400字以内
- 禁止使用"非常好""很不错"等模糊词，必须引用具体数字"""
    else:
        format_section = f"""输出格式要求（严格遵守，违反将导致推荐无效）：

第一步：开头用一句话总结，列出全部商品名称（用顿号分隔），以句号结尾。
第二步：紧接着依次用「商品1」「商品2」「商品3」分别展开每款商品，每款商品用「商品N」独占一行作为标题。
第三步：以「结语」收尾，简短追问用户偏好（1句话，不超过20字）。

每款商品的展开格式：
「商品N」
商品全名 | 综合匹配度 XX%（使用上方检索数据中的匹配度数值，如实输出，不得编造）
① 匹配依据：...
② 品质亮点：...
③ 适用场景：...

格式示例：
为您找到3款降噪耳机：索尼WH-1000XM5、Bose QC45、AirPods Pro，分别适合不同场景。

「商品1」
索尼 WH-1000XM5 | 综合匹配度 92%
① 匹配依据：顶级降噪，适合通勤与办公
② 品质亮点：30小时续航、LDAC高清音频、多点连接
③ 适用场景：地铁通勤、办公室专注工作

「商品2」
Bose QC45 | 综合匹配度 88%
① 匹配依据：性价比突出的降噪标杆，通勤续航双优
② 品质亮点：24小时续航、TriPort声学结构、蓝牙5.1
③ 适用场景：日常通勤与长时间佩戴

「商品3」
AirPods Pro | 综合匹配度 85%
① 匹配依据：苹果生态无缝切换，自适应降噪
② 品质亮点：H2芯片、个性化空间音频、IPX4防水
③ 适用场景：苹果用户日常全场景使用

「结语」需要进一步筛选品牌或预算吗？

要求：
- 必须逐一推荐以上全部 {n} 款商品，不可跳过任何一款
- 每款商品必须独占一行使用「商品N」标记
- 总字数控制在300字以内
- 禁止使用"非常好""很不错"等模糊词，必须引用具体数字"""

    return f"""你是一个电商导购助手。基于检索到的商品信息，为用户生成推荐回答。
{reliability_hint}
{scenario_hint}{history_text}⚠️ 严禁事项（违反将导致推荐无效）:
1. 不得编造任何商品名称、型号、价格 - 只能引用上方[1][2]...标记的商品
2. 不得编造优惠券、满减、折扣、赠品、限时活动
3. 不得编造不存在的功能参数、认证标识
4. 不得编造用户评价、销量排名、市场占有率、对比结论

校验规则:
- 你提到的每个价格数字，必须在检索数据中出现过
- 你提到的每个品牌名、产品名，必须在检索数据中出现过
- 如果所有商品与用户需求的匹配度均低于60%，应诚实告知"当前没有很匹配的商品，建议调整条件"
- 违反以上任一条，不要输出该推荐
- 引用来源请用 [1][2] 标注，标注对应检索数据中的商品序号，让用户清楚每条推荐的依据

用户需求：{message}
用户预算：{slots.get('price_min', '不限')}-{slots.get('price_max', '不限')}
用户品类偏好：{slots.get('category', '未指定')}
{_build_exclusion_hint(slots)}
检索到的商品（共{n}款，必须全部推荐，不可遗漏）：
{context}

{format_section}"""
