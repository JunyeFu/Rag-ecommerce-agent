"""评测接口 — 对接 evaluator 服务"""
import json
import logging
from pathlib import Path
from fastapi import APIRouter, BackgroundTasks
from app.schemas.common import ApiResponse
from app.services.evaluator import run_evaluation

logger = logging.getLogger("evaluation_api")
router = APIRouter()


@router.post("/evaluation/run")
async def run_eval(background_tasks: BackgroundTasks):
    """触发评测任务（后台异步执行）"""
    # 同步模式：直接执行并返回结果
    try:
        result = await run_evaluation()
        return ApiResponse(data=result, message="评测完成")
    except Exception as e:
        logger.exception("Evaluation failed")
        return ApiResponse(
            data={"error": "评测执行失败，请稍后重试"},
            message="评测执行失败"
        )


@router.get("/evaluation/report")
async def get_eval_report():
    """获取最新评测报告"""
    report_path = Path(__file__).resolve().parents[2] / "data" / "test_cases" / "eval_results.json"
    if report_path.exists():
        with open(report_path, encoding="utf-8") as f:
            report = json.load(f)
        return ApiResponse(data=report, message="评测报告")

    return ApiResponse(
        data={"status": "no_report"},
        message="暂无评测报告，请先执行 POST /evaluation/run"
    )
