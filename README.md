# quantllm

基于 `vnpy_ctp` 底层 Python 交易 API 的 VeighNa 最小行情 Demo。

## Demo 目标

本仓库把课程项目中已经完成的底层行情实验整理成可以独立阅读和运行的最小示例：

1. 从 `vnpy_ctp.api.MdApi` 创建行情 API。
2. 连接 CTP 行情前置。
3. 在前置连接回调中发送登录请求。
4. 登录成功后发送合约行情订阅请求。
5. 在 `onRtnDepthMarketData` 回调中打印 Tick 推送。

核心流程位于 [`scripts/market_data_demo.py`](scripts/market_data_demo.py)。这个 Demo 不使用 `CtpGateway`、`EventEngine` 或 GUI，便于从底层回调理解连接和行情数据流。

## 文件结构

| 文件或目录 | 用途 |
| --- | --- |
| `scripts/market_data_demo.py` | 单合约连接、登录、订阅和 Tick 打印入口 |
| `scripts/active_contracts_demo.py` | 多合约持续订阅和 Tick 打印入口 |
| `scripts/breakout_buy_demo.py` | 可选的 MdApi + TdApi 触发下单教学扩展，默认 dry-run |
| `config/ctp_settings.example.json` | 无凭据的连接配置示例 |
| `docs/demo_flow.md` | 回调顺序、运行方法和边界 |
| `docs/active_contracts.md` | 多合约订阅说明 |
| `docs/breakout_buy.md` | 下单扩展示例的安全边界 |
| `link.md` | vn.py、VeighNa 和 CTP 文档链接 |

## 安装

请使用 VeighNa Studio 自带的 Python，或已经安装 `vnpy_ctp` 的虚拟环境：

```powershell
python -m pip install -r requirements.txt
```

如果使用项目中的源码副本，可按本机 C++ 构建环境安装 `raw/vnpy_ctp`；Windows 优先使用 VeighNa Studio Python。

## 运行单合约行情 Demo

凭据只放在当前终端环境变量中，不要写入代码或 Git：

```powershell
$env:SIMNOW_USERID = '你的用户名'
$env:SIMNOW_PASSWORD = '你的密码'
$env:SIMNOW_BROKERID = '9999'
$env:SIMNOW_MD_ADDRESS = 'tcp://182.254.243.31:30011'

python .\scripts\market_data_demo.py --symbol rb2605
```

预期回调顺序是连接、登录成功、订阅确认和类似下面的 Tick：

```text
[connection] front connected; requesting login.
[login] successful; subscribing to rb2605
[subscribe] accepted: rb2605
[tick] symbol=rb2605 time=... last=... volume=... bid1=... ask1=...
```

按 `Ctrl+C` 退出。合约月份和行情前置可能随 SimNow 环境变化，应以当前可交易合约为准。

## 多合约订阅

```powershell
python .\scripts\active_contracts_demo.py --symbols rb2701 i2701 IF2612
```

## 下单扩展

`breakout_buy_demo.py` 同时演示 `MdApi` 和 `TdApi` 的认证、登录、结算确认、合约查询和一次性 FAK 买开请求。默认只 dry-run；只有显式传入 `--live` 才会尝试发送一手仿真委托。它不是生产策略，也没有止损和平仓逻辑。

## 安全边界

仓库不包含真实账号、密码、授权码、API token 或交易配置。SimNow 连接和行情回调结果取决于服务器、交易时段和当前合约状态。
