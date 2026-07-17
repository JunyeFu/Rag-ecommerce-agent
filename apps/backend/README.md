# Backend — 电商 AI 导购系统

FastAPI + LangGraph + pgvector + PostgreSQL

## 快速启动

```bash
# 1. 启动基础设施
docker compose up -d

# 2. 安装依赖
uv pip install -r requirements.txt

# 3. 数据库迁移
alembic upgrade head

# 4. 种子数据
python scripts/seed_data.py

# 5. 启动服务
uvicorn app.main:app --reload --port 8080
```

## API 文档

启动后访问 http://localhost:8000/docs

## 项目结构

详见 `../项目结构说明.md`
