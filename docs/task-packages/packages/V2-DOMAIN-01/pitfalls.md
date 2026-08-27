# V2-DOMAIN-01 易错点

- `Product.price`、`Offer.price` 和 `OfferQuote.amount` 不能作为同一字段继续传播。
- Product 是规范化身份，Variant 才能用于同规格比价；低置信度匹配不得合并。
- Quote 是带时间的不可变观察值，不应被原地覆盖而失去审计历史。
- Decimal/Numeric 仍需明确币种、最小单位和舍入；仅换类型不等于金额契约完整。
- 首版没有平台 Order、Payment、Refund 表，禁止为未来猜测提前建模。
