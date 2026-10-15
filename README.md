# quant-demo：CTP 行情与 SimNow 验收

基于底层 `MdApi` / `TdApi` 的教学实验，已补充结构化日志、离线测试、平仓对账和源码 WIKI。**全部下单入口固定为 SimNow，默认只查询；不是生产交易系统。**

## 先看验收结果

- **2026-10-13 最新整改版本：ag2612 买开 1 手 14686、卖平今 1 手 14684，开仓后查得今仓 1，两轮最终全账户持仓/活动委托均为 0/0。** [新日志、源码哈希及离线复核](docs/evidence/20261013-ag2612-latest/README.md)。

- 2026-10-08 夜盘：ag2612 买开 1 手成交 14338，卖平今 1 手成交 14336；两次全账户查询总持仓 0、活动委托 0。
- 独立 VeighNa 客户端和采集器 361 条同期行情的时间戳与六字段一致。独立的是进程、连接与处理实现，仍共享 SimNow 上游，不是另一数据供应商。
- 2026-10-09–10：36 项离线测试通过；新版只读客户端实收 52 Tick 后正常退出；集成入口只读回归取得 13 Tick、空仓及无活动委托。旧版真实开平仓证据与新版回归分别标注。
- [教师要求到证据的映射](docs/acceptance.md)、[原始成交证据包及说明](docs/evidence/20261008-ag2612/README.md)、[本地检查记录](docs/checks/local_checks.json)。

## 离线复核，无账号、无网络

Python 3.13：

```powershell
python -B -m unittest discover -s scripts/simnow -p 'test_*.py' -v
python -B scripts/verify_evidence.py
python -B scripts/check_secrets.py --output .cache/security.json
```

证据复核校验 ZIP 和全部成员哈希，再用当前验收器重算 10 项检查。CI 配置位于 `.github/workflows/offline.yml`；本次仅本地验证，尚未上传运行远端 CI。

## 本机连接与运行

在线环境已核验 Windows、Python 3.13.8、vnpy 4.4.0、vnpy_ctp 6.7.11.3。使用安装了这些依赖的 VeighNa Studio Python。`requirements.txt` 记录顶层版本，平台、原生库与完整依赖仍可能影响复现。

```powershell
# 弹出本地配置对话框；账号密码不写在命令、代码或聊天中
powershell -ExecutionPolicy Bypass -File scripts/simnow/configure.ps1
# 30 秒只读行情采集
powershell -ExecutionPolicy Bypass -File scripts/simnow/start.ps1 -Symbol ag2612 -DurationSeconds 30
# 查询账户、验证新鲜报价与最终状态；不下单
powershell -ExecutionPolicy Bypass -File scripts/simnow/start_acceptance.ps1
```

启动器输出运行目录和 PID，日志在 `data/simnow_checks/<run>/`。`start.ps1` 和 `start_acceptance.ps1` 支持 `-PythonPath` 与 `-CredentialPath`，不要求复制现有加密凭据；DPAPI 配置仅限创建它的 Windows 用户解密。行情成功以 `summary.json` 和 `analyze.py` 为准，进程启动不等于验收通过。

```powershell
python -B scripts/simnow/analyze.py --help
# 仅在准备进行一次新的仿真交易时使用：固定 ag2612，最多买开 1 手并卖平今
powershell -ExecutionPolicy Bypass -File scripts/simnow/start_acceptance.ps1 -ExecuteSimNow
```

需要报价活跃、全账户起始无持仓/活动委托。合约过期或前置变更后须重新审查合约与地址；本仓库不自动切换合约。`-Trigger <价格>` 可等待突破，超时不发单；未指定则作一次开平仓工程验收。原 `--live` 已撤销，`breakout_buy_demo.py` 使用同一安全入口。详见[设计和操作步骤](docs/breakout_buy.md)。

## 源码学习

从 [WIKI 总览](wiki/overview.md)进入：[底层 API、事件引擎对象导航](wiki/entities/runtime.md)、[订单生命周期原理](wiki/concepts/order-lifecycle.md)、[验收 DEMO 设计](wiki/code/simnow.md)。原 `market_data_demo.py` 与 `active_contracts_demo.py` 继续用于学习回调和多合约订阅；需要留存证据时使用 `scripts/simnow/` 入口。

## 边界

成交返回不等于最终空仓，净多空相抵不等于无持仓；验收使用全账户绝对持仓总和，并要求服务器查询完整结束。仅处理本次从空账户开出的 1 手，未知仓位或断线时停止自动发单并保留失败日志。IOC 未成交、通信异常、并发人工操作均可能使验收失败，需要查看真实账户状态；程序不保证在任何故障下平仓。凭据检查结果只覆盖本地可见文件和 Git 历史，不能宣称全球无泄漏。

## 本地交付与提交

[教师要求逐项对照](docs/acceptance.md) · [文件整理和自行提交步骤](docs/submission.md)。
