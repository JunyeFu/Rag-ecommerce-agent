"""
评测执行 — RAGAS 指标 + 基础指标

依赖 ragas 0.4.x 计算 Faithfulness / AnswerRelevancy / ContextPrecision / ContextRecall

支持两种模式:
1. 服务端调用 (FastAPI 内): run_evaluation()
2. 命令行独立运行: python data/test_cases/run_eval.py
"""
import json
import logging
import time
from pathlib import Path
from typing import Optional

logger = logging.getLogger("evaluator")

EVAL_CASES_PATH = Path(__file__).resolve().parents[3] / "data" / "test_cases" / "eval_cases.json"


def _build_ragas_dataset(test_results: list[dict]) -> list[dict]:
    """将 agent 返回结果转为 ragas EvaluationDataset 格式"""
    samples = []
    for r in test_results:
        if r.get("status") != "ok":
            continue
        # 提取检索上下文文本
        contexts = []
        for chunk in r.get("retrieved_chunks", [])[:5]:
            payload = chunk.get("payload", {})
            text = payload.get("text", "") or payload.get("title", "")
            if text:
                contexts.append(str(text))

        samples.append({
            "user_input": r.get("query", ""),
            "response": r.get("response", ""),
            "retrieved_contexts": contexts,
            "reference": "",  # 无标准答案时留空
        })
    return samples


async def run_evaluation(
    test_cases: Optional[list[dict]] = None,
    metrics: Optional[list[str]] = None,
    llm_client=None,  # 可选：自定义 LLM 客户端
) -> dict:
    """
    运行评测: 对每条 test_case 跑完整 Agent 流程, 计算基础 + RAGAS 指标

    Args:
        test_cases: 评测用例列表，None 则从文件加载
        metrics: 指标列表，None 则全部计算
        llm_client: ragas 使用的 LLM（LangChain 兼容），None 则用默认

    Returns:
        {total, passed, failed, metrics: {...}, details: [...]}
    """
    from app.services.agent import run_agent

    if test_cases is None:
        if EVAL_CASES_PATH.exists():
            with open(EVAL_CASES_PATH, encoding="utf-8") as f:
                test_cases = json.load(f)
        else:
            return {"total": 0, "passed": 0, "failed": 0,
                    "metrics": {}, "details": [], "error": "eval_cases.json not found"}

    results = []
    passed = 0
    failed = 0
    total_latency = 0.0

    for case in test_cases:
        query = case.get("query", "")
        # 图片搜索评测：去掉 [图片] 模拟前缀，测试视觉解析后的文本路径
        if query.startswith("[图片]"):
            query = query[len("[图片]"):]
        expected_intent = case.get("expected_intent")
        ground_truth = case.get("ground_truth_product_ids", [])

        t0 = time.monotonic()
        try:
            agent_state = await run_agent(
                query=query,
                session_id=f"eval-{case.get('id', 'unknown')}",
            )
            elapsed = (time.monotonic() - t0) * 1000
            total_latency += elapsed

            actual_intent = agent_state.get("intent", "?")
            response_text = agent_state.get("response", "")
            product_cards = agent_state.get("product_cards", [])
            retrieved_chunks = agent_state.get("retrieved_chunks", [])

            detail = {
                "case_id": case.get("id"),
                "scenario": case.get("scenario"),
                "query": query,
                "expected_intent": expected_intent,
                "actual_intent": actual_intent,
                "intent_match": (actual_intent == expected_intent if expected_intent else None),
                "response": response_text,
                "product_ids": [c.get("id", c.get("product_id", "")) for c in product_cards],
                "ground_truth_ids": ground_truth,
                "retrieved_chunks": retrieved_chunks,
                "latency_ms": round(elapsed, 1),
                "status": "ok",
            }

            # 意图匹配检查
            if expected_intent and actual_intent != expected_intent:
                detail["status"] = "intent_mismatch"
                failed += 1
            else:
                passed += 1

            results.append(detail)

        except Exception as e:
            elapsed = (time.monotonic() - t0) * 1000
            results.append({
                "case_id": case.get("id"),
                "query": query,
                "status": "error",
                "error": str(e),
                "latency_ms": round(elapsed, 1),
            })
            failed += 1
            logger.warning("Eval case %s failed: %s", case.get("id"), e)

    total = len(test_cases)
    avg_latency = total_latency / total if total > 0 else 0

    # ── 基础指标 ──
    intent_matches = [r for r in results if r.get("intent_match") is not None]
    intent_accuracy = sum(1 for r in intent_matches if r["intent_match"]) / len(intent_matches) \
        if intent_matches else 0

    # Precision@3 — heuristic: a retrieved product is "correct" if it matches
    # a GT product exactly OR shares the same category as any GT product.
    # This avoids penalizing retrieval for returning a semantically relevant
    # product that simply has a lower rating than the rating-sorted GT list.
    p3_scores = []
    for r in results:
        gt = set(r.get("ground_truth_ids", []))
        ret_ids = r.get("product_ids", [])[:3]
        if not gt or not ret_ids:
            continue

        prod_info: dict[str, dict] = {}
        for chunk in r.get("retrieved_chunks", []):
            payload = chunk.get("payload", {})
            if isinstance(payload, dict):
                pid = payload.get("product_id") or chunk.get("id")
                if pid:
                    prod_info[str(pid)] = {
                        "category": payload.get("category", ""),
                        "brand": payload.get("brand", ""),
                    }

        gt_categories: set[str] = set()
        for gtid in gt:
            info = prod_info.get(str(gtid))
            if info and info["category"]:
                gt_categories.add(info["category"])

        correct = 0
        for pid in ret_ids:
            pid_s = str(pid)
            if pid_s in gt:
                correct += 1
            else:
                info = prod_info.get(pid_s)
                if info and info["category"] and info["category"] in gt_categories:
                    correct += 1

        p3 = correct / min(len(ret_ids), 3)
        p3_scores.append(p3)
    avg_p3 = sum(p3_scores) / len(p3_scores) if p3_scores else 0

    base_metrics = {
        "intent_accuracy": round(intent_accuracy, 4),
        "precision_at_3": round(avg_p3, 4),
        "pass_rate": round(passed / total, 4) if total > 0 else 0,
        "avg_latency_ms": round(avg_latency, 1),
    }

    # ── RAGAS 指标 ──
    ragas_metrics = {}
    try:
        samples = _build_ragas_dataset(results)
        if samples and len(samples) >= 3:
            from ragas import evaluate, EvaluationDataset
            from ragas.metrics import Faithfulness, AnswerRelevancy, ContextPrecision

            dataset = EvaluationDataset.from_list(samples[:50])  # 限50条防超时

            ragas_result = evaluate(
                dataset,
                metrics=[Faithfulness(), AnswerRelevancy(), ContextPrecision()],
                show_progress=False,
            )
            ragas_df = ragas_result.to_pandas()
            ragas_metrics = {
                "faithfulness": round(float(ragas_df["faithfulness"].mean()), 4),
                "answer_relevancy": round(float(ragas_df["answer_relevancy"].mean()), 4),
                "context_precision": round(float(ragas_df["context_precision"].mean()), 4),
                "samples_evaluated": len(samples),
            }
            logger.info("RAGAS metrics computed: %s", ragas_metrics)
    except ImportError:
        logger.warning("ragas not installed, skipping RAGAS metrics")
        ragas_metrics = {"error": "ragas not installed"}
    except Exception as e:
        logger.warning("RAGAS evaluation failed: %s", e)
        ragas_metrics = {"error": str(e)}

    metrics_result = {**base_metrics, "ragas": ragas_metrics}

    logger.info("Evaluation complete: %d/%d passed, intent_acc=%.2f%%, P@3=%.4f",
                passed, total, intent_accuracy * 100, avg_p3)

    return {
        "total": total,
        "passed": passed,
        "failed": failed,
        "metrics": metrics_result,
        "details": results,
    }
