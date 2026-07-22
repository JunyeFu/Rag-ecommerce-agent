"""知识库管理接口 - 文档上传入库"""
import uuid
from fastapi import APIRouter, UploadFile, File, Form
from app.schemas.common import ApiResponse
from app.services.ingestion import ingest_knowledge_document, parse_document_file

router = APIRouter(prefix="/knowledge", tags=["knowledge"])


@router.post("/ingest")
async def ingest_knowledge(
    file: UploadFile = File(...),
    doc_name: str = Form(""),
):
    """上传文档 -> 解析 -> 切分 -> 向量化 -> 写入 knowledge_chunks"""
    contents = await file.read()
    text = parse_document_file(contents, file.filename)
    doc_id = f"kb_{uuid.uuid4().hex[:12]}"
    chunk_count = await ingest_knowledge_document(
        doc_id, text, file.filename,
        {"filename": file.filename, "doc_name": doc_name},
    )
    return ApiResponse(
        data={"doc_id": doc_id, "chunks": chunk_count, "filename": file.filename}
    )
