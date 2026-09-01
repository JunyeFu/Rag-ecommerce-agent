# V3-DATA-RAG-01 演示数据与混合检索

## 目标
交付可分发 3C 演示数据和混合检索链。
## 状态
`complete`
## 范围
- 60 个虚构 SKU、品牌规范化、Embedding SPI、BM25/向量/过滤/RRF。
## 非目标
- 287 条开发数据不进入演示包。
## 前置依赖
- `V3-CONTRACT-01`。
## 路径所有权
- `data/demo`、`packages/retrieval`、数据生成脚本。
## 现状证据
- 60 SKU、4 品类、60 SVG 资产确定性检查通过。
## 执行步骤
1. 写数据与检索红测。2. 生成资产。3. 实现融合。4. 重建验证。
## 数据引用
- `../../shared/business-data.json`
- `../../shared/development-data.json`
- `../../shared/pitfalls.md`
## 验收
- [x] 数据许可清单完整。
- [x] 别名、过滤、融合与重建测试通过。
## 回滚
- 只回滚 `data/demo` 与 V3 retrieval 新增路径。
## 停止条件
- 许可来源或哈希不明确时停止。
## 交接格式
- 结果、路径、验证、外部门禁、下一包。
