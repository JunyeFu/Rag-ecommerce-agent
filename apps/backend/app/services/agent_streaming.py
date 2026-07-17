"""
SSE 流式输出辅助函数 - 从 agent.py 提取

负责:
- 真流式交错输出 (token 逐字发送 + 卡片插入点检测)
- 完整文本交错输出 (分块发送 + 卡片边界定位)
- 缓存 key 构建
- 流文本标记清理
"""
import json
import re
from typing import AsyncGenerator

from app.schemas.sse_events import TextDeltaEvent, ProductCardEvent
from app.services import cache


def _safe_emit_boundary(unemitted: str) -> int:
    """返回 unemitted 中可以安全输出的位置 - 保留最后一句完整句子用于三特征检测。"""
    if len(unemitted) < 40:
        return 0
    boundaries = []
    for sep in ("。", "！", "？"):
        pos = -1
        while True:
            pos = unemitted.find(sep, pos + 1)
            if pos < 0:
                break
            boundaries.append(pos + 1)  # 包含标点
    if len(boundaries) < 2:
        return 0
    boundaries.sort()
    return boundaries[-2]  # 保留最后一句，输出倒数第二句之前的所有内容


async def _stream_interleaved(stream, cards: list) -> AsyncGenerator:
    """真流式交错输出 - 逐 token 发送文字，边收边检测卡片插入点。

    检测策略：
    1. 「商品N」标记扫描 - 最精确，立即在标记处插入卡片
    2. 三特征检测 - 匹配依据/品质亮点/适用场景 全部出现在第N款商品时，
       等待适用场景句号到达后插入第N张卡片
    3. 安全输出：只输出倒数第二句号之前的文本，保留最后一句在缓冲区中
       以确保卡片边界检测能完整捕获"适用场景。"的句号。
    """
    buffer = ""           # 全部已接收文本
    emitted_pos = 0       # 已发送到客户端的缓冲位置
    emitted_indices = set()
    closing_seen = False

    marker_re = re.compile(r"「商品\s*(\d+)\s*」|\[PRODUCT_(\d+)\]|【PRODUCT_(\d+)】")
    tag_re = re.compile(r"「(?:商品\s*\d+\s*」|结语」)|\[(?:SUMMARY|PRODUCT_\d+|CLOSING)\]|【(?:SUMMARY|PRODUCT_\d+|CLOSING)】", re.IGNORECASE)
    closing_re = re.compile(r"「结语」|\[CLOSING\]|【CLOSING】", re.IGNORECASE)

    def _card(idx: int):
        if idx >= len(cards):
            return None
        c = cards[idx]
        return {
            "event": "product_cards",
            "data": ProductCardEvent(
                product_id=c.get("product_id", c.get("id", "")),
                title=c.get("title", ""), price=c.get("price", 0),
                rating=c.get("rating", 0),
                match_score=c.get("match_score", c.get("score", 0.5)),
                highlights=c.get("highlights", []),
                image_url=c.get("image_url"), image_urls=c.get("image_urls", []),
                brand=c.get("brand"), category=c.get("category", ""),
                index=idx + 1, total=len(cards),
            ).model_dump_json(),
        }

    def _emit_up_to(pos: int):
        """输出 emitted_pos 到 pos 之间的文本（清理标记后）。"""
        nonlocal emitted_pos
        if pos <= emitted_pos:
            return
        seg = buffer[emitted_pos:pos]
        clean = tag_re.sub("", seg)
        if clean.strip():
            yield_me = {"event": "text_delta", "data": TextDeltaEvent(content=clean).model_dump_json()}
            emitted_pos = pos
            return yield_me
        emitted_pos = pos
        return None

    async for chunk in stream:
        delta = chunk.choices[0].delta
        if not delta.content:
            continue

        buffer += delta.content

        # ── Closing 之后：直接透传 ──
        if closing_seen:
            evt = _emit_up_to(len(buffer))
            if evt:
                yield evt
            continue

        # ── Closing 检测 ──
        cm = closing_re.search(buffer, emitted_pos)
        if cm:
            evt = _emit_up_to(cm.start())
            if evt:
                yield evt
            next_idx = len(emitted_indices)
            if next_idx < len(cards):
                ce = _card(next_idx)
                if ce:
                    emitted_indices.add(next_idx)
                    yield ce
            emitted_pos = cm.end()
            closing_seen = True
            continue

        # ── 策略1: 「商品N」标记 ──
        # 标记表示下一款商品的开头，不是当前卡片的插入点。
        # 因此在「商品2」处发送商品1卡片，在「商品3」处发送商品2卡片。
        m = marker_re.search(buffer, emitted_pos)
        if m:
            evt = _emit_up_to(m.start())
            if evt:
                yield evt
            card_num = int(m.group(1) or m.group(2) or m.group(3))
            prev_idx = card_num - 2
            if 0 <= prev_idx < len(cards) and prev_idx not in emitted_indices:
                ce = _card(prev_idx)
                if ce:
                    emitted_indices.add(prev_idx)
                    yield ce
            elif card_num > 1:
                next_idx = len(emitted_indices)
                if next_idx < min(card_num - 1, len(cards)):
                    ce = _card(next_idx)
                    if ce:
                        emitted_indices.add(next_idx)
                        yield ce
            emitted_pos = m.end()
            continue

        # ── 策略2: 三特征检测（匹配依据 + 品质亮点 + 适用场景） ──
        count_a = buffer.count("匹配依据")
        count_b = buffer.count("品质亮点")
        count_c = buffer.count("适用场景")
        min_count = min(count_a, count_b, count_c)

        while min_count > len(emitted_indices):
            # 找到第 len(emitted_indices)+1 次"适用场景"后的句号位置
            target = len(emitted_indices) + 1
            nth = _nth_occurrence(buffer, "适用场景", target)
            end = buffer.find("。", nth)
            if end < 0:
                break  # 句号还没到，继续等

            card_pos = end + 1  # 卡片插在句号之后
            evt = _emit_up_to(card_pos)
            if evt:
                yield evt

            # 按顺序发下一张未发送的卡片
            next_idx = len(emitted_indices)
            if next_idx < len(cards):
                ce = _card(next_idx)
                if ce:
                    emitted_indices.add(next_idx)
                    yield ce
            else:
                break

        # ── 安全输出：只发倒数第二句号之前的文本，保留最后一句在缓冲中 ──
        unemitted = buffer[emitted_pos:]
        safe = _safe_emit_boundary(unemitted)
        if safe > 0:
            evt = _emit_up_to(emitted_pos + safe)
            if evt:
                yield evt

    # ── 流结束：输出剩余文本 + 兜底卡片 ──
    evt = _emit_up_to(len(buffer))
    if evt:
        yield evt

    for idx in range(len(cards)):
        if idx not in emitted_indices:
            ce = _card(idx)
            if ce:
                yield ce


def _find_card_boundaries(text: str, cards: list) -> list:
    """在完整响应文本中定位每张卡片的插入点，返回 [(position, card_idx), ...] 按位置排序。

    策略优先级：
    1. 「商品N」标记 - 最精确
    2. 三特征检测（匹配依据 + 品质亮点 + 适用场景）- LLM 几乎一定会输出
    3. 标题模糊匹配 - 兜底
    """
    marker_re = re.compile(r"「商品\s*(\d+)\s*」|\[PRODUCT_(\d+)\]|【PRODUCT_(\d+)】")

    # 策略1: 标记
    # 「商品N」是第 N 款商品详情的开头。卡片应出现在上一款详情文本之后：
    # 「商品2」前插商品1卡，「商品3」前插商品2卡，最后一款放在正文末尾。
    boundaries = []
    marker_matches = list(marker_re.finditer(text))
    for m in marker_matches:
        card_num = int(m.group(1) or m.group(2) or m.group(3))
        card_idx = card_num - 2
        if 0 <= card_idx < len(cards):
            boundaries.append((m.start(), card_idx))
    if marker_matches:
        last_card_num = int(marker_matches[-1].group(1) or marker_matches[-1].group(2) or marker_matches[-1].group(3))
        last_card_idx = last_card_num - 1
        if 0 <= last_card_idx < len(cards):
            boundaries.append((len(text), last_card_idx))
    if boundaries:
        boundaries.sort(key=lambda x: x[0])
        return boundaries

    # 策略2: 三特征检测 - 匹配依据、品质亮点、适用场景 同时出现第N次 -> 第N张卡片
    # 卡片放在适用场景段落末尾（句号之后）
    for card_idx in range(len(cards)):
        target = card_idx + 1
        pos_a = _nth_occurrence(text, "匹配依据", target)
        pos_b = _nth_occurrence(text, "品质亮点", target)
        pos_c = _nth_occurrence(text, "适用场景", target)
        if pos_a < 0 or pos_b < 0 or pos_c < 0:
            break
        # 卡片插入点：适用场景后第一个句号之后
        end = text.find("。", pos_c)
        if end >= 0:
            boundaries.append((end + 1, card_idx))
        else:
            boundaries.append((pos_c + 4, card_idx))  # len("适用场景") = 4

    if boundaries:
        boundaries.sort(key=lambda x: x[0])
        return boundaries

    # 策略3: 标题模糊匹配
    for card_idx, card in enumerate(cards):
        title = card.get("title", "").strip()
        if not title or len(title) < 3:
            continue
        pos = text.find(title)
        if pos < 0:
            tokens = re.findall(r'[一-鿿]+|[a-zA-Z0-9]+', title)
            if len(tokens) >= 2:
                for start in range(1, min(3, len(tokens))):
                    sub = ''.join(tokens[start:])
                    if len(sub) >= 4:
                        pos = text.find(sub)
                        if pos >= 0:
                            break
        if pos < 0:
            prefix = title[:6].strip()
            if len(prefix) >= 4:
                pos = text.find(prefix)
        if pos >= 0:
            boundaries.append((pos, card_idx))

    boundaries.sort(key=lambda x: x[0])
    return boundaries


def _nth_occurrence(text: str, pattern: str, n: int) -> int:
    """返回 pattern 在 text 中第 n 次出现的位置（0-indexed），未找到返回 -1。"""
    pos = -1
    for _ in range(n):
        pos = text.find(pattern, pos + 1)
        if pos == -1:
            return -1
    return pos


async def _emit_interleaved(response_text: str, cards: list) -> AsyncGenerator:
    """基于完整文本的交错输出：文本分段 -> 清理标记 -> 16字符分块输出 -> 插入卡片。

    卡片位置由 _find_card_boundaries 预计算，基于完整文本，定位准确。
    """
    tag_re = re.compile(r"「(?:商品\s*\d+\s*」|结语」)|\[(?:SUMMARY|PRODUCT_\d+|CLOSING)\]|【(?:SUMMARY|PRODUCT_\d+|CLOSING)】", re.IGNORECASE)
    closing_re = re.compile(r"「结语」|\[CLOSING\]|【CLOSING】", re.IGNORECASE)

    def _card(idx: int) -> dict:
        if idx >= len(cards):
            return None
        c = cards[idx]
        return {
            "event": "product_cards",
            "data": ProductCardEvent(
                product_id=c.get("product_id", c.get("id", "")),
                title=c.get("title", ""), price=c.get("price", 0),
                rating=c.get("rating", 0),
                match_score=c.get("match_score", c.get("score", 0.5)),
                highlights=c.get("highlights", []),
                image_url=c.get("image_url"), image_urls=c.get("image_urls", []),
                brand=c.get("brand"), category=c.get("category", ""),
                index=idx + 1, total=len(cards),
            ).model_dump_json(),
        }

    # 1. 分离结语：结语标记之后的内容不再插入卡片
    body_text = response_text
    closing_text = ""
    cm_body = closing_re.search(response_text)
    if cm_body:
        body_text = response_text[: cm_body.start()]
        closing_text = response_text[cm_body.start():]

    # 2. 找到每张卡片的插入点
    boundaries = _find_card_boundaries(body_text, cards)

    # 3. 按卡片边界切分文本 -> 逐段输出文本 + 卡片
    emitted = set()
    prev_pos = 0
    for pos, card_idx in boundaries:
        if card_idx in emitted:
            continue
        seg_text = tag_re.sub("", body_text[prev_pos:pos])
        # 输出文本
        for i in range(0, len(seg_text), 16):
            chunk = seg_text[i : i + 16]
            if chunk:
                yield {"event": "text_delta", "data": TextDeltaEvent(content=chunk).model_dump_json()}
        # 输出卡片
        evt = _card(card_idx)
        if evt:
            emitted.add(card_idx)
            yield evt
        prev_pos = pos

    # 4. 剩余正文文本（卡片之后、结语之前）
    remaining_body = tag_re.sub("", body_text[prev_pos:])
    for i in range(0, len(remaining_body), 16):
        chunk = remaining_body[i : i + 16]
        if chunk:
            yield {"event": "text_delta", "data": TextDeltaEvent(content=chunk).model_dump_json()}

    # 5. 结语文本
    closing_text = tag_re.sub("", closing_text)
    for i in range(0, len(closing_text), 16):
        chunk = closing_text[i : i + 16]
        if chunk:
            yield {"event": "text_delta", "data": TextDeltaEvent(content=chunk).model_dump_json()}

    # 6. 兜底：未发送的卡片附在末尾
    for idx in range(len(cards)):
        if idx not in emitted:
            evt = _card(idx)
            if evt:
                yield evt


def _build_cache_key(message: str, conversation_id: str | None, history: list[dict]) -> str:
    """Build a context-aware cache key so short multi-turn replies do not collide."""
    recent = [
        {"role": h.get("role", ""), "content": (h.get("content", "") or "")[:200]}
        for h in history[-4:]
    ]
    return json.dumps(
        {
            "v": cache.CACHE_VERSION,
            "conversation_id": conversation_id or "",
            "message": message.strip(),
            "history": recent,
        },
        ensure_ascii=False,
        sort_keys=True,
    )


def _clean_stream_text(text: str) -> str:
    """Remove internal structure markers before streaming text to the client."""
    text = re.sub(r"「(?:商品\s*\d+\s*」|结语」)|\[(?:SUMMARY|PRODUCT_\d+|CLOSING)\]|【(?:SUMMARY|PRODUCT_\d+|CLOSING)】", "", text, flags=re.IGNORECASE)
    return text
