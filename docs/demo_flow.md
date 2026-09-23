# Demo flow

## Core callback sequence

```text
MdApi.createFtdcMdApi
  -> registerFront
  -> init
  -> onFrontConnected
  -> reqUserLogin
  -> onRspUserLogin
  -> subscribeMarketData
  -> onRspSubMarketData
  -> onRtnDepthMarketData (repeated)
```

`market_data_demo.py` 中 `onFrontConnected` 发起登录，`onRspUserLogin` 只在成功后订阅，`onRtnDepthMarketData` 将交易所推送的原始字段压缩成一行输出。`Event` 用于让主线程持续等待，收到登录失败或 Ctrl+C 后退出。

## 观察重点

- 连接成功不等于登录成功。
- 订阅响应确认不等于已经收到 Tick；合约必须在交易时段有行情。
- 回调来自异步 CTP 线程，打印逻辑应保持轻量。
- `.ctp_flow` 只保存底层 API 流文件，已加入忽略规则。
