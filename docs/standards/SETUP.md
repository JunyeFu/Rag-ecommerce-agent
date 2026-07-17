# 从零开始运行项目 — 完整指南

> **⚠️ 辅助文档** - 开发权威入口为 [`DEV-CONTROL.md`](../DEV-CONTROL.md)，如有冲突以权威文档为准。
>
> 目标：从 `git clone` 到后端跑通 + Android 编译成功，覆盖所有必需步骤。

---

## 一、环境要求

| 依赖 | 最低版本 | 验证命令 |
|------|:--:|------|
| Python | 3.11+ | `python --version` |
| Docker | 24+ (含 compose) | `docker compose version` |
| Git | 2.40+ | `git --version` |
| Android Studio | Hedgehog+ | `sdkmanager --version` |
| JDK | 17 | `java -version` |

> **Windows 用户注意**：如果本机已安装 PostgreSQL，其 5432 端口会与 Docker 容器冲突，需先停止本机 postgres 服务（`services.msc` → PostgreSQL → 停止）。

---

## 二、克隆仓库

```bash
git clone https://github.com/fujunye-company/rag-ecommerce-agent.git
# 或 SSH: git clone git@github.com:fujunye-company/rag-ecommerce-agent.git
cd rag-ecommerce-agent
```

---

## 三、配置环境变量

```bash
# 1. 复制模板
cp apps/backend/.env.example apps/backend/.env

# 2. 编辑 .env，填入真实 API Key（至少填一个 LLM Key）
# API Key 由比赛主办方提供，请联系主办方获取。
# 编辑器打开 apps/backend/.env，修改以下两行：
#
#   DOUBAO_API_KEY=ark-xxxxxx     ← 比赛提供的豆包 Key
#   DEEPSEEK_API_KEY=sk-xxxxxx    ← 或者用 DeepSeek Key
```

`.env.example` 中的其他配置项（数据库地址、Qdrant 地址、模型名）均已有合理默认值，本地开发无需修改。

---

## 四、Python 环境

```bash
# 创建虚拟环境
python3 -m venv ~/.hermes-venv

# 激活（Linux/Mac）
source ~/.hermes-venv/bin/activate

# 激活（Windows Git Bash）
source ~/.hermes-venv/Scripts/activate

# 安装依赖
cd apps/backend
pip install -r requirements.txt
```

验证依赖安装成功：

```bash
python -c "import fastapi, sentence_transformers, qdrant_client, langgraph; print('All OK')"
```

---

## 五、下载 HuggingFace 模型

> 两个模型合计约 **3.5GB**，首次下载需 5-15 分钟（取决于网速）。

```bash
# 确保虚拟环境已激活
source ~/.hermes-venv/bin/activate

# 下载 Embedding 模型（必须）
python -c "
from sentence_transformers import SentenceTransformer
m = SentenceTransformer('BAAI/bge-large-zh-v1.5')
print('Embedding model OK, dim =', m.get_sentence_embedding_dimension())
"

# 下载 Reranker 模型（可选，无模型时自动降级为原始分数排序）
python -c "
from sentence_transformers import CrossEncoder
m = CrossEncoder('BAAI/bge-reranker-v2-m3')
print('Reranker model OK')
"
```

**缓存位置：** `~/.cache/huggingface/hub/models--BAAI--<模型名>/`

验证下载成功（离线模式加载不报错即成功）：

```bash
python -c "
from sentence_transformers import SentenceTransformer, CrossEncoder
m1 = SentenceTransformer('BAAI/bge-large-zh-v1.5', local_files_only=True)
m2 = CrossEncoder('BAAI/bge-reranker-v2-m3')
print('Both models ready')
"
```

---

## 六、启动基础设施（Docker）

```bash
# 回到项目根目录
cd ../..  # 回到 rag-ecommerce-agent/

# 仅启动 PostgreSQL + Qdrant（backend 手动启动以方便调试）
docker compose -f infrastructure/docker-compose.yml up -d postgres qdrant

# 等待容器就绪（约 10-15 秒）
docker compose -f infrastructure/docker-compose.yml ps
```

预期看到 2 个容器 running：`shopping-pg`、`shopping-qdrant`。

验证基础设施：

```bash
# PostgreSQL 连接测试
docker exec shopping-pg pg_isready -U shopping -d shopping_agent

# Qdrant 健康检查
curl http://localhost:6333/healthz
```

---

## 七、数据入库

```bash
cd apps/backend

# 执行入库（首次约 30 秒，含 embedding 编码）
python -c "from app.startup import ensure_qdrant_data; import asyncio; asyncio.run(ensure_qdrant_data())"
```

预期输出：

```
Loading embedding model: BAAI/bge-large-zh-v1.5
Embedding model ready, dim=1024
Creating collection: products 1024-dim
Upserting 190 products with reviews...
Done: 190 vectors ingested
```

验证入库成功：

```bash
# 直接查询 Qdrant 向量数
curl -s http://localhost:6333/collections/products | python -c "import sys,json; d=json.load(sys.stdin); print(f'Points: {d[\"result\"][\"points_count\"]}')"
# 预期输出：Points: 190
```

---

## 八、启动后端

```bash
cd apps/backend && uvicorn app.main:app --reload --host 0.0.0.0 --port 8080
```

预期输出：

```
INFO:     Started server process [xxxxx]
INFO:main: 数据库表创建/验证完成
INFO:reranker: Reranker model loaded (CPU)
INFO:main: Reranker model warmed up
INFO:main: Query cache cleared on startup
INFO:     Uvicorn running on http://0.0.0.0:8080
```

### 验证后端 API

```bash
# 1. 健康检查
curl http://localhost:8080/health

# 2. 检索验证
curl -X POST http://localhost:8080/api/v1/search \
  -H "Content-Type: application/json" \
  -d '{"query": "降噪耳机", "top_k": 3}'

# 3. 发送第一条对话
curl -X POST http://localhost:8080/api/v1/chat \
  -H "Content-Type: application/json" \
  -d '{"message": "推荐一款降噪耳机", "conversation_id": "test-001"}'

# 4. 查看 API 文档
# 浏览器打开 http://localhost:8080/docs
```

---

## 九、编译运行 Android

### 9.1 配置 Android SDK

Android Studio → Settings → Languages & Frameworks → Android SDK → 安装 **API 34** + **Build Tools 34.0.0**。

### 9.2 配置后端地址

后端地址通过 Gradle 属性 `apiUrl` 配置，默认 `http://10.0.2.2:8080`（Android 模拟器）。定义在 `NetworkConfig.kt` 中，编译时注入 `BuildConfig.API_BASE_URL`。

```
http://10.0.2.2:8080        ← Android 模拟器访问宿主机（默认）
http://<你的局域网IP>:8080   ← 真机访问，通过 -PapiUrl 覆盖
http://127.0.0.1:8080       ← 真机通过 adb reverse 连接
```

### 9.3 编译安装

```bash
cd apps/android

# Debug 构建（默认连接模拟器，无需签名配置）
./gradlew assembleDebug

# 真机 Debug 构建（指定后端 IP）
./gradlew assembleDebug -PapiUrl=http://192.168.1.100:8080

# Windows
gradlew.bat assembleDebug
```

APK 输出路径：`app/build/outputs/apk/debug/app-debug.apk`

或在 Android Studio 中直接点击 Run。

---

## 十、常见问题

### Q1: PostgreSQL 端口冲突

```bash
# Windows 查看占用 5432 端口的进程
netstat -ano | findstr :5432
# 停止本机 postgres 服务（管理员 PowerShell）
Stop-Service postgresql* -Force
```

### Q2: Qdrant 连接失败

```bash
docker logs shopping-qdrant
# 确保容器正在运行且端口 6333 可访问
```

### Q3: 入库脚本报 "model not found"

下载 Embedding 模型（见第五节）后再重试。

### Q4: 后端启动报 "DATABASE_URL not configured"

检查 `apps/backend/.env` 是否存在且包含 `DATABASE_URL` 配置。

### Q5: LLM 调用报 401/403

检查 `.env` 中的 `DOUBAO_API_KEY` 或 `DEEPSEEK_API_KEY` 是否正确。

### Q6: Android 编译失败 "SDK not found"

在 Android Studio 中打开 `apps/android/` 目录，等待 Gradle Sync 完成后自动下载缺失 SDK。

### Q7: Reranker 报 "model unavailable"

无害，重排序会自动降级为原始向量分数排序。如需完整精排功能，执行第五节的下载命令。

---

## 流程总结

```
git clone → .env 配置 → venv + pip install → 下载模型 → docker up → 数据入库 → 后端启动 → Android 编译
                                                                                              ↑
                                                                    (可选) → 验证 API → 联调测试
```
