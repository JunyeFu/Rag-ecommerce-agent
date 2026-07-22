# 编码规范（唯一权威）

> 最后更新：2026-07-20（P2 规范化落地）

## 1. Python 后端规范

### 1.1 文件与函数

| 规则 | 限制 | 工具 |
|------|------|------|
| 单文件行数 | ≤ 400 行 | ruff / PR review |
| 单函数行数 | ≤ 80 行 | ruff PLR0915 (max-statements=50) |
| 函数参数 | ≤ 5 个 | ruff PLR0913 (max-args=5) |
| 圈复杂度 | ≤ 15 | ruff C901 (max-complexity=15) |
| 分支数 | ≤ 12 | ruff PLR0912 |
| 返回语句 | ≤ 5 | ruff PLR0911 |

超限函数需在 PR 中标注 `# noqa: PLR0915` 并附拆分计划。

### 1.2 禁止项

- **禁模块级可变 dict 当缓存** -- 统一用 `core/cache/` 的 `CacheBackend` Protocol
- **禁函数内 lazy import**（除非真循环依赖）-- 用 `TYPE_CHECKING` 替代
- **禁 `_` 前缀函数 re-export** -- 调用方直接 import 真实位置
- **禁 `.model_dump()` 返回** -- 直接返回 `ApiResponse` 对象，让 FastAPI 序列化
- **禁裸 `except Exception: pass`** -- 至少 `logger.warning`

### 1.3 必须项

- 所有 service 必须有 `test_<name>.py`
- CI 覆盖率门禁 ≥ 70%
- 所有 API 端点返回 `ApiResponse` 信封（`/health` `/ready` `/version` 除外）
- `user_id` 从 `request.state.user_id` 读取（AuthMiddleware 注入），禁 Query 参数
- 状态突变用 POST body（`OrderStatusUpdateRequest`），禁 Query 参数

### 1.4 命名约定

| 类型 | 约定 | 示例 |
|------|------|------|
| 函数 | snake_case | `get_cart_total` |
| 类 | PascalCase | `CartService` |
| 常量 | UPPER_SNAKE | `MAX_CART_ITEMS` |
| 私有 | `_` 前缀 | `_validate_uuid` |
| 测试 | `test_<被测函数>_<场景>` | `test_get_cart_cached_hit` |

## 2. Kotlin 前端规范

### 2.1 文件与类

| 规则 | 限制 |
|------|------|
| 单文件行数 | ≤ 600 行 |
| ViewModel 行数 | ≤ 400 行 |
| Composable 函数行数 | ≤ 100 行 |

### 2.2 HTTP 调用

- 所有 HTTP 调用必须经 `ApiClient`（禁直接 `NetworkConfig.httpClient`）
- `ApiClient` 通过 `AuthInterceptor` 自动注入 `Authorization: Bearer <token>` 头
- 401 响应由 `AuthInterceptor` 自动处理（清 token -> 重新 login -> 重试一次）

### 2.3 ViewModel

- 重复计算抽 helper（如 `CartViewModel.recalculateTotals(items, selectedIds)`）
- State 用 `StateFlow`，禁直接 `MutableState`
- 网络调用在 `viewModelScope.launch`，禁主线程阻塞

### 2.4 命名约定

| 类型 | 约定 | 示例 |
|------|------|------|
| 函数 | camelCase | `addToCart` |
| 类 | PascalCase | `CartViewModel` |
| 常量 | UPPER_SNAKE | `MAX_QUANTITY` |
| Composable | PascalCase | `ProductCard` |

## 3. 测试金字塔

```
        /\
       /e2e\         5-10 个关键路径（pytest -m e2e, 需 DB）
      /------\
     /contract\      所有 API 端点契约（pytest -m contract）
    /----------\
   / integration\   68 个（含 contract + e2e，6 类关键路径全覆盖）
  /--------------\
  /     unit       \ 448 个（含 service 层测试）
/------------------\
```

### 3.1 单元测试规范

- 纯函数测试，无外部依赖（无 DB / 无 LLM / 无网络）
- Mock 用 `unittest.mock.AsyncMock` / `MagicMock`
- 命名：`test_<被测函数>_<场景>`
- 一个 test 函数只测一个行为
- 用 `pytest.mark.unit` 标记

### 3.2 契约测试规范

- 验证 API 端点返回 `ApiResponse` 信封（`{code, data, message}`）
- 验证鉴权门禁（无 token 返回 401）
- 用 `pytest.mark.contract` 标记
- 用 ASGITransport + TestClient（不启动真实服务器）

### 3.3 e2e 测试规范

- 关键用户路径（login -> 浏览 -> 加购 -> 下单）
- 需要真实 DB + LLM
- 用 `pytest.mark.e2e` 标记
- 可独立运行：`pytest -m e2e`

## 4. Git 提交规范

### 4.1 提交信息格式

```
<type>: <描述>

type: feat | fix | test | docs | refactor | chore | ci
```

### 4.2 分支命名

| 类型 | 格式 | 示例 |
|------|------|------|
| 功能 | `feature/<描述>` | `feature/auth-system` |
| 修复 | `fix/<描述>` | `fix/cart-race-condition` |
| 文档 | `docs/<描述>` | `docs/api-reference` |

## 5. CI 门禁

| 检查 | 工具 | 门禁 |
|------|------|------|
| Lint | ruff check | 0 error |
| 类型 | mypy | 0 error |
| 单元测试 | pytest -m unit --cov | 覆盖率 ≥ 70% |
| 契约测试 | pytest -m contract | 全通过 |
| 安全 | bandit + pip-audit | 0 high |
| 迁移 | alembic upgrade head | 幂等 |
