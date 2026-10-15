---
title: quant-demo 学习总览
type: analysis
status: reviewed
updated: 2026-10-15
sources:
  - "[[本地源码和运行记录]]"
tags: [quant, reproducibility]
---

# quant-demo 学习总览

当前已完成底层行情、单手仿真开平仓、服务器持仓/委托核验、独立客户端对照，以及日志、离线测试和只读客户端收尾修复。完整仓库入口见 [README](../README.md)。

学习顺序：[来源与版本](sources/local-records.md) → [对象导航](entities/runtime.md) → [状态与核验原理](concepts/order-lifecycle.md) → [代码设计](code/simnow.md) → [实际验收](../docs/acceptance.md)。

待学习：断线后的持久化恢复、多账户并发风控、合约生命周期、生产级订单恢复和盘中人工操作冲突。当前教学实验不覆盖这些能力。行情程序及多合约程序保持教学入口，新验收为独立可审查实验。

[知识目录](index.md) · [维护日志](log.md)

扩展导航：[CTA 对象](entities/cta.md) · [双向事件链](architecture/event-flow.md)。

2026-10-13 已按当前整改源码完成新的 1 手 SimNow 持仓实验；[最新原始日志和复核](../docs/evidence/20261013-ag2612-latest/README.md)证明开仓后持仓 1、最终两次 0/0。独立客户端对照仍引用 10 月 8 日单独证据。

## [2026-10-15] ingest | 阶段提交复核

按[提交说明](../docs/submission.md)复核实际拟提交文件、36 项测试与交易证据；本轮不联网交易，保留不同日期的独立对照和最新开平仓证据边界。
