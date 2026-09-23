# Active contract demo

`active_contracts_demo.py` 复用单合约 Demo 的底层 `MdApi` 流程，将一个订阅请求扩展为多个合约。默认合约只是示例，主力月份会迁移；运行时可通过 `--symbols` 替换。

一个合约订阅失败只打印错误，不会主动取消其他合约的订阅。按 `Ctrl+C` 或收到登录失败后退出。
