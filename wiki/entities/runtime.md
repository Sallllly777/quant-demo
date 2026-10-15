---
title: 核心源码对象导航
type: architecture
status: reviewed
updated: 2026-10-09
sources:
  - "[[本地源码和运行记录]]"
tags: [quant, reproducibility]
---

# 核心源码对象导航

先定位对象职责，再跟踪调用；版本以 [来源记录](../sources/local-records.md)为准。

| 对象 | 模块 / 方法 | 职责与下一跳 |
| --- | --- | --- |
| MdApi / TdApi | `vnpy_ctp.api`，`createFtdc*Api`、`init`、`req*`、`onRsp*` / `onRtn*` | 创建原生接口，异步响应；当前本机创建方法要求显式第二个握手模式参数 |
| CtpGateway | `vnpy_ctp/gateway/ctp_gateway.py`，`connect/subscribe/send_order/close` | 接口门面，标准请求到 CtpMdApi / CtpTdApi |
| CtpMdApi | 同模块，`onRtnDepthMarketData` | 转换 TickData，`gateway.on_tick` 分发；本次独立客户端直接复用安装版本 |
| CtpTdApi | 同模块，认证登录、结算确认、查询、`onRtnOrder/onRtnTrade` | CTP 枚举/方向/开平和合约信息转换，发布标准交易对象 |
| BaseGateway | `vnpy/trader/gateway.py`，`on_event/on_tick/on_order` | 将对象封装成事件投入 EventEngine |
| EventEngine | `vnpy/event/engine.py`，`put/register/_process` | 队列与处理器分发；慢回调会影响后续事件 |
| MainEngine / OmsEngine | `vnpy/trader/engine.py`，`add_gateway`、`process_*_event`、`get_*` | 协调组件与缓存最新订单/成交/持仓；缓存完整性依赖连接和回调 |
| OffsetConverter / PositionHolding | `vnpy/trader/converter.py`，`convert_order_request/update_*` | 持仓、冻结量与平今/平昨请求转换；需要正确更新数据 |

仓库实现：[Trading.rpc/response/account_snapshot/submit](../../scripts/simnow/acceptance.py) 明确请求编号、最后一包、全账户对账与订单归属；[verify_acceptance](../../scripts/simnow/verify_acceptance.py)独立重算结论。直接底层 API 实验不经过 OmsEngine，因而使用服务器查询保存最终状态。

关联：[订单生命周期](../concepts/order-lifecycle.md)、[DEMO](../code/simnow.md)。CTA 的后续源码导航见 [CTA 对象](cta.md)与[双向事件链](../architecture/event-flow.md)；本实验没有采用 CtaEngine 执行交易。
