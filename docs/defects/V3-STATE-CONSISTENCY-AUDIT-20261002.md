# V3 理想状态与代码实现核对（2026-10-02）

审查依据：`docs/plans/v3-complex-commerce-repair-plan.md` 与 `V3-ANDROID-UX-CLOSE-01` 的接口、恢复和视觉验收条款。下面先登记代码根因，再修复、测试、复审。范围是当前 Mission/比较/待购状态链，不代表已经审查整仓所有代码。

## 已确认缺陷表

| ID / 优先级 | 理想状态 | 当前实现与根因 | 修复与验收 | 状态 |
|---|---|---|---|---|
| S01 / P1 | 同一幂等请求重放或冲突不改变任务 | `TurnService.submit` 在 `reserve` 前合并澄清并调用 `update_goal`；重放、409 都能递增版本 | 预留 Turn 与澄清写入原子完成；相同 key 重放和不同正文冲突不改变 goal/version | 已修复；API/数据库并发通过 |
| S02 / P1 | 编辑需求后的恢复只展示当前版本结果 | `snapshot` 仍读旧 Turn 的候选/路线；`update_goal` 保留旧比较；比较校验遍历旧事件；旧版本待审批仍能继续执行 | 版本不匹配时返回待执行空结果并清比较；拒绝旧版本候选重新入选和审批 | 已修复；恢复/拒绝旧审批通过 |
| S03 / P2 | Snapshot 与 SSE reducer 最终状态一致 | `snapshot` 累加多次 products，完成后仍返回历史 approval_required | 只使用最后 products 事件；非 WAITING_APPROVAL 不返回待审批动作 | 已修复；事件回放测试通过 |
| S04 / P1 | 清单、待购只接受目录中存在的商品/报价 | `DemoCommerce` 与 `PostgresDemoCommerce` 写入时未检查新增 variant/offer 是否存在 | 无效引用返回错误且不写入；已存在条目移除语义不变 | 已修复；API/数据库不写入测试通过 |
| S05 / P2 | 修改观察阈值后读取新阈值 | 内存 `create_watcher` 直接返回旧对象，而 PostgreSQL 使用 upsert 更新 | 两种实现均更新同一 watcher 的阈值；ID/创建时间不变 | 已修复；两种存储测试通过 |
| S06 / P1 | 返回对话只是导航，不丢比较候选 | `ReturnToMissionConversation` 清空 products；页面路由复用 products 是否为空 | 单独表达对话/推荐显示状态；保留候选与比较；新结果重新打开推荐 | 已修复；reducer/编译通过，未做设备点击 |
| S07 / P2 | JSON null 对应 Kotlin null | `parseThreadSnapshot` 用 optString 读取 nullable pending_action，得到字面量 null；商业事实有效期同样受影响 | nullable 字段明确检查 isNull；协议测试断言 null，而非仅检查候选 | 已修复；协议单测通过 |

## 理想能力边界

- 现有 Agent 有规划、工具执行、审批和事件恢复链，并非只有商品列表 UI；但这些状态一致性缺陷妨碍跨步骤完成任务。
- 演示报价、观察草稿不等于真实可购买报价或后台通知。修复不得改变 DEMO_FIXTURE/草稿说明。
- 多商品预算组合优化、真实商业履约不由本表中的状态修复证明完成。
- 历史 fixture、Android 测试数量不作为本次通过证据；真实 MiMo、设备真点击、PostgreSQL 并发分别记录，未运行则不声明通过。

## 修改范围

`apps/api/src/ragcommerce_api/{app,service,postgres_index,demo,postgres_demo}.py`、相关 API 测试、Android ShoppingModels/EditorialShoppingApp/ShoppingRepository 与 reducer、协议测试、所属任务包路径声明以及本表。S04 同时修正 HTTP 层未转换目录 KeyError 的问题，避免非法引用变成 500。

## 本轮验证与独立复审

### 可重跑验证

| 检查 | 命令 / 证据入口 | 实测结果 |
|---|---|---|
| Python 非集成回归 | `.venv/Scripts/python.exe -m pytest -m "not integration" -q` | 126 passed，15 deselected；未将未选集成用例计为通过 |
| PostgreSQL 专项 | `API_DATABASE_URL` 指向隔离库后运行 `pytest apps/api/tests/test_postgres_api_integration.py -q` | 7 passed；含新增 3 项事务/并发/数据一致性回归 |
| 数据库初始化 | `alembic -c apps/api/alembic.ini upgrade head` | 临时 PostgreSQL 17 全部迁移成功；未修改现有项目数据库 |
| Android 单测 | `gradlew.bat :app:testDebugUnitTest` | 26 tests，0 failures，0 errors；XML 位于 `apps/android/app/build/test-results/testDebugUnitTest/` |
| Android 编译与 lint | `:app:compileDebugAndroidTestKotlin`、`:app:lintDebug :app:assembleDebug` | 全部成功；最后一轮 20 executed / 40 UP-TO-DATE，如实保留增量构建属性 |
| 任务包 | `python scripts/validate_task_packages.py` | 38 packages，0 errors，0 warnings |
| Python 静态检查 | `ruff check` 本轮 API 源码与回归文件 | 通过 |
| 空白检查 | `git diff --check` | 无 diff 错误；存在 Windows LF/CRLF 提示，不计作代码失败 |

初始回归实际复现 S01、S04、S05；测试开发期间另纠正了测试中的接口路径和候选 payload，未把测试自身错误算作产品缺陷。Android 首次构建未设置 SDK 路径而失败，补充进程内 ANDROID_HOME 后成功，未读取或写入 local.properties。

### 修复后独立于实现步骤的二次代码复审

由同一执行者在修复后重新沿调用链核对，并非另一名审查者背书：

1. 从 HTTP submit → reserve → Worker 复查：澄清写入已移入预留事务，重复 key 在任何写入前返回；PostgreSQL 对 thread 行加锁，同 key 并发只产生一次版本变更。
2. 从 edit → snapshot → comparison → decide 复查：发现旧审批入口遗漏，补充 S02 拒绝旧版本审批测试后，重新执行完整 Python 非集成回归。已完成动作的幂等重放保留。
3. 从非法目录 ID → HTTP → 内存/SQL 写入复查：无效引用先失败；与改名组合的清单请求也不留下部分更新；HTTP 404 不再成为未处理 KeyError。
4. 从返回对话 → 底部导航 → 决策候选复查：showConversation 只控制显示；候选和比较集合不再清空；新 products 事件重新显示推荐，主/次/再次纵向结构未改。
5. 从 API nullable 字段 → Kotlin 解析复查：JSON null 不再变成字面字符串；无备用结果、自动模型切换或通用重试新增。

**结论：表内 7 项已完成代码修复和相应自动化验证。** 本轮未运行真实 MiMo、ADB 业务点击或 Android instrumentation；仅发现其他项目模拟器，不替换或清除其状态。因此这是代码/协议/数据库专项修复结论，不是全场景视觉验收，也不等于 V3 宏观方案全部完成。未暂存、提交或推送。
