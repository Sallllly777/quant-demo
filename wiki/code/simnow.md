---
title: SimNow 验收与行情 DEMO 设计
type: practice
status: reviewed
updated: 2026-10-09
sources:
  - "[[本地源码和运行记录]]"
tags: [quant, reproducibility]
---

# SimNow 验收与行情 DEMO 设计

职责：`capture.py` 负责限时采集/新鲜度证据；`acceptance.py` 负责受限交易闭环；`reference_client.py` 负责独立只读连接；`verify_acceptance.py` 只读复算；PowerShell 负责 DPAPI 解密与进程环境，不输出凭据。

最小流程和命令见 [操作说明](../../docs/breakout_buy.md)。Journal 记录经过字段白名单的 JSONL 事件与 JSON 查询快照；原生 flow 留本机并忽略。默认验收入口也会连接 TD 与确认结算，但不发单。显式开关只开放一个固定仿真合约，最多一手开仓，最多五次平仓尝试。

关键取舍：IOC 加限价边界减少挂单持续风险，但不能保证成交；只处理本次可对账仓位，避免误处理人工仓位；发生断线或查询错误时拒绝继续发单。新 reference 只创建 CtpMdApi，原生生产者停止后再关闭事件引擎和文件。

基础 `market_data_demo.py` 演示登录→订阅→打印，不带订单；`active_contracts_demo.py` 对多个合约执行同一流程，API 初始化与错误脱敏已统一。它们不提供完整证据存档，实测使用 capture。`breakout_buy_demo.py` 转接同一验收入口，可选价格阈值，未触发超时退出；阈值并非盈利信号证明。

测试：[本地检查](../../docs/checks/local_checks.json)覆盖行情、查询、报价、次数限制、归属与重复回报；[实际证据](../../docs/acceptance.md)覆盖成功路径。离线 Mock 不能代替网络成交实测，当前新代码的在线回归是只读；旧开平仓绑定原始源码哈希。

关联：[生命周期](../concepts/order-lifecycle.md)、[对象](../entities/runtime.md)、[来源](../sources/local-records.md)。待验证：升级版本、合约到期或前置调整均需重新核验。当前不覆盖跨夜仓、套利组合、并发策略或生产风控。
