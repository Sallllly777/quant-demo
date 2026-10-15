---
title: 行情和委托的双向事件链
type: architecture
status: reviewed
updated: 2026-10-10
sources:
  - "[[本地源码和运行记录]]"
tags: [quant, acceptance, reproducibility]
---

# 行情和委托的双向事件链

问题：同一策略为什么会先收到 Tick，再经多层组件发单，最后异步收到成交？框架将外部柜台和策略解耦，事件顺序与完整性需要显式理解。

```text
行情：CTP MdApi → CtpMdApi → BaseGateway.on_tick → EventEngine
                                      ├→ OmsEngine 最新 Tick 缓存
                                      └→ CtaEngine → strategy.on_tick
下单：strategy.buy/sell → CtaEngine → MainEngine → CtpGateway → CtpTdApi
回报：CTP TdApi → 标准 OrderData/TradeData → EventEngine
                                      ├→ OMS 委托/成交缓存
                                      └→ CTA 归属路由、去重、pos 更新、回调
核验：完整服务器持仓/委托查询 → 对照缓存与本次成交 → 判断最终状态
```

事件队列让组件独立处理，但没有自动赋予“缓存一定完整”“关机就平仓”或“订单必成交”的保证。OMS 保存最新收到的事实；风险限额、查询错误、断线恢复和跨会话归属需另行设计。

本仓库底层验收绕过 CTA 和 OMS，直接持有查询/委托状态；独立行情客户端使用 EventEngine 与 MainWindow。这样可以核对两种行情处理路径，但仍共享 CTP 库与 SimNow 上游。

关联：[对象导航](../entities/runtime.md)、[CTA](../entities/cta.md)、[生命周期](../concepts/order-lifecycle.md)、[DEMO](../code/simnow.md)、[来源](../sources/local-records.md)。待验证：故障恢复与多策略并发的生产需求不在本教学验收范围。
