# API 接口文档 — Hermes 电商AI导购系统

> **⚠️ 辅助文档** - 开发权威入口为 [`DEV-CONTROL.md`](DEV-CONTROL.md)，如有冲突以权威文档为准。
>
> Base URL: `http://localhost:8080/api/v1`
> 所有业务端点挂载在 `/api/v1` 前缀下。

---

## 对话接口

### POST /chat

SSE 流式对话，支持多轮上下文（通过 `conversation_id`）。

**请求**：
```json
{
  "message": "推荐降噪耳机",
  "conversation_id": "uuid-optional"
}
```

**SSE 事件类型**：

| 事件 | 说明 |
|------|------|
| `progress` | 处理进度通知（message 字段） |
| `text_delta` | AI 文本回复片段（content 字段） |
| `product_cards` | 商品卡片（product_id, title, price, image_url, match_score, highlights 等） |
| `clarify` | 反问澄清（question, missing_slots, options） |
| `web_search_result` | 联网搜索结果（title, url, snippet） |
| `compare` | 商品对比维度（dimensions 数组） |
| `error` | 错误事件（message, code） |
| `done` | 流结束（latency_ms, total_cards, slots） |

---

## 商品接口

### GET /products

商品列表，支持筛选/排序/分页。

| 参数 | 类型 | 说明 |
|------|------|------|
| category | string | 品类过滤 |
| brand | string | 品牌过滤 |
| price_min | float | 最低价 |
| price_max | float | 最高价 |
| keyword | string | 标题搜索 |
| sort_by | string | price_asc / price_desc / rating / sales |
| page | int | 页码 (default 1) |
| size | int | 每页条数 (default 20, max 100) |

### GET /products/{product_id}

商品详情。

### POST /products

创建商品。

### PUT /products/{product_id}

更新商品（仅更新传入字段）。

### DELETE /products/{product_id}

删除商品。

---

## 购物车接口

### GET /cart

获取购物车（含商品图片/品牌/品类）。Query: `?session_id=<uuid>`

### POST /cart/items

添加商品。Body: `{ "session_id": "...", "product_id": "..." }`  
服务端查商品表取真实价格，不信任客户端传入的 price/title。

### POST /cart/add

[Android 兼容别名] 同 POST /cart/items。

### DELETE /cart/items

删除商品。Body: `{ "session_id": "...", "product_id": "..." }`

### POST /cart/remove

[Android 兼容别名] 同 DELETE /cart/items。

### PUT /cart/items

修改数量。Body: `{ "session_id": "...", "product_id": "...", "quantity": 2 }`

### PUT /cart/quantity

[Android 兼容别名] 同 PUT /cart/items。

### DELETE /cart

清空购物车。Query: `?session_id=<uuid>`

### POST /cart/clear

[Android 兼容别名] 清空购物车。Body: `{ "session_id": "..." }`

---

## 订单接口

### POST /orders

下单（读取购物车 → 创建订单 → 清空购物车）。

Body: `{ "session_id": "...", "address": "收货地址" }`

### GET /orders

订单列表。Query: `?session_id=<uuid>&status=pending`

### GET /orders/{order_id}

订单详情。

### POST /orders/{order_id}/cancel

取消订单。

---

## 拍照找货接口

### POST /upload/image

上传图片，本地保存。multipart/form-data: `file`

### POST /upload/vision-search

拍照找货（SSE 流式）。multipart/form-data: `file`  
返回: `progress`（vision_parsed）→ `product_cards` → `done`

### GET /upload/vision-status

视觉检索 readiness 检查（检查 Doubao 视觉 API 配置，不触发本地模型加载）。

## 语音输入接口

### POST /voice/recognize

语音转文字。multipart/form-data: `file`
返回: `{ text, provider }`，优先使用 Doubao Chat API `input_audio`，失败时回退 `whisper-1`。

### POST /voice/chat

语音导购。multipart/form-data: `file`，先转写语音，再进入 RAG 检索管道并通过 SSE 流式返回推荐。

### POST /documents/upload

知识文档上传。multipart/form-data: `file`

---

## 对比接口

### POST /products/compare

多商品横向对比。

```json
{
  "product_ids": ["id1", "id2"],
  "dimensions": ["价格", "功能", "口碑"]
}
```

---

## 反馈接口

### POST /feedback

点赞/点踩。

```json
{
  "message_id": "uuid",
  "rating": 1,
  "reason": "推荐准确"
}
```

---

## 用户接口

### GET /users/me — 当前用户信息
### PUT /users/me — 更新个人信息（昵称/头像）
### GET /users/me/favorites — 收藏列表
### POST /users/me/favorites — 添加收藏
### DELETE /users/me/favorites/{product_id} — 取消收藏
### GET /users/me/footprints — 浏览足迹
### GET /users/me/reviews — 我的评价
### POST /products/{id}/reviews — 提交商品评价

---

## 评测接口

### POST /evaluation/run

触发评测任务（后台异步执行）。

### GET /evaluation/report

获取最新评测报告。

---

## 知识库接口

### POST /knowledge/ingest

知识库入库。

---

## 缓存管理

### POST /api/cache/clear

清空查询缓存（参数变更后使用）。

---

## 健康检查

### GET /health

```json
{
  "status": "ok",
  "version": "1.0.0",
  "database": "connected",
   "pgvector": "ok"
}
```

### GET /ready

部署就绪检查（返回初始化进度）。

### GET /version

系统版本及技术栈信息。
