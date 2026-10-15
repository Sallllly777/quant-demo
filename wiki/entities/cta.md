---
title: CTA 策略与回测对象
type: architecture
status: reviewed
updated: 2026-10-10
sources:
  - "[[本地源码和运行记录]]"
tags: [quant, acceptance, reproducibility]
---

# CTA 策略与回测对象

源码阅读范围为本机 `vnpy_ctastrategy` 安装包，版本和三个源文件哈希见 [版本记录](../../docs/source_versions.json)。这是源码学习，不代表本仓库验收由 CTA 引擎执行。

| 对象 | 源码 / 方法 | 作用与边界 |
| --- | --- | --- |
| CtaTemplate | `vnpy_ctastrategy/template.py`；on_tick/on_bar/on_order/on_trade、buy/sell/short/cover、send_order | 策略回调协议和下单门面，运行状态控制策略能否发单 |
| CtaEngine | `engine.py`；process_tick_event、process_order_event、process_trade_event、send_order | 维护合约/策略/订单映射；去重成交，先更新 strategy.pos 再调用 on_trade；不是服务器持仓对账替代品 |
| BacktestingEngine | `backtesting.py`；run_backtesting、new_bar/new_tick、cross_limit_order/cross_stop_order、calculate_result/calculate_statistics | 历史回放、简化撮合、逐日结果与统计 |

跟读顺序：CtaTemplate.buy → CtaTemplate.send_order → CtaEngine.send_order → 合约查询和最小价位/数量对齐 → 限价或停止单分支 → MainEngine/网关。回报按订单归属路由回策略，终态委托移出活跃集合，成交去重后更新策略净仓。框架策略净仓与柜台全账户多空持仓是不同范围。

回测 `new_bar` 先处理既有委托的限价/停止单撮合，再调用 `on_bar`；普通限价 Bar 撮合用低/高价判断是否穿透，价格受开盘约束，模型会把可成交量记为全部成交。缺少排队、盘口深度和真实部分成交，不能用相同模板接口推导实盘成交一致。本地停止单也依赖进程和行情持续运行。

关联：[运行时对象](runtime.md)、[事件调用链](../architecture/event-flow.md)、[订单核验](../concepts/order-lifecycle.md)、[来源](../sources/local-records.md)。待学习：建立独立 CTA 策略回测实验；不将尚未做过的 CTA 实测写成完成。
