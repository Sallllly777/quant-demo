"""Minimal SimNow market-data client built directly on vnpy_ctp.api.MdApi.

This example intentionally does not use EventEngine, MainEngine, or CtpGateway.
It demonstrates the lower-level CTP Python callback API only.
"""

from __future__ import annotations

import argparse
import os
import signal
import sys
from dataclasses import dataclass
from pathlib import Path
from threading import Event
from typing import Any

from vnpy_ctp.api import MdApi


@dataclass(frozen=True)
class MdSettings:
    """Connection settings required by the CTP market-data API."""

    userid: str
    password: str
    brokerid: str
    address: str

    def login_request(self) -> dict[str, str]:
        return {
            "UserID": self.userid,
            "Password": self.password,
            "BrokerID": self.brokerid,
        }


class PrintMarketDataApi(MdApi):
    """Connect, log in, subscribe one contract, and print each depth-market tick."""

    def __init__(self, settings: MdSettings, symbol: str) -> None:
        super().__init__()
        self.settings = settings
        self.symbol = symbol
        self.request_id = 0
        self.logged_in = False
        self.stopped = Event()

    def _next_request_id(self) -> int:
        self.request_id += 1
        return self.request_id

    def onFrontConnected(self) -> None:
        print("[connection] CTP market-data front connected; requesting login.")
        self.reqUserLogin(self.settings.login_request(), self._next_request_id())

    def onFrontDisconnected(self, reason: int) -> None:
        self.logged_in = False
        print(f"[connection] CTP market-data front disconnected (reason={reason}).")

    def onRspUserLogin(self, data: dict, error: dict, reqid: int, last: bool) -> None:
        error_id = error.get("ErrorID", -1)
        if error_id:
            print(
                f"[login] failed (request={reqid}, error={error_id}): "
                f"[message omitted]",
                file=sys.stderr,
            )
            self.stopped.set()
            return

        self.logged_in = True
        print("[login] successful; subscribing to", self.symbol)
        self.subscribeMarketData(self.symbol)

    def onRspError(self, error: dict, reqid: int, last: bool) -> None:
        print(
            f"[ctp-error] request={reqid}, error={error.get('ErrorID')}: "
            f"[message omitted]",
            file=sys.stderr,
        )

    def onRspSubMarketData(self, data: dict, error: dict, reqid: int, last: bool) -> None:
        error_id = error.get("ErrorID", -1)
        if error_id:
            print(
                f"[subscribe] failed for {data.get('InstrumentID', self.symbol)} "
                f"(error={error_id}): [message omitted]",
                file=sys.stderr,
            )
            return
        print(f"[subscribe] accepted: {data.get('InstrumentID', self.symbol)}")

    def onRtnDepthMarketData(self, data: dict) -> None:
        """Receive and print the raw CTP depth-market callback as a compact row."""
        print(
            "[tick] "
            f"symbol={data.get('InstrumentID')} "
            f"time={data.get('ActionDay') or data.get('TradingDay')} "
            f"{data.get('UpdateTime')}.{data.get('UpdateMillisec', 0):03d} "
            f"last={data.get('LastPrice')} volume={data.get('Volume')} "
            f"bid1={data.get('BidPrice1')}@{data.get('BidVolume1')} "
            f"ask1={data.get('AskPrice1')}@{data.get('AskVolume1')}"
        )

    def start(self) -> None:
        """Create the native API instance and begin the asynchronous connection."""
        flow_path = Path.cwd() / ".ctp_flow"
        flow_path.mkdir(exist_ok=True)
        self.createFtdcMdApi((str(flow_path) + os.sep).encode("gbk"), True)
        self.registerFront(self.settings.address)
        self.init()

    def close(self) -> None:
        self.stopped.set()
        self.exit()


def required_env(name: str) -> str:
    value = os.getenv(name, "").strip()
    if not value:
        raise ValueError(f"Missing required environment variable: {name}")
    return value


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Minimal vnpy_ctp SimNow market-data demo")
    parser.add_argument("--symbol", required=True, help="CTP instrument ID to subscribe, e.g. ag2612")
    parser.add_argument(
        "--md-address",
        default=os.getenv("SIMNOW_MD_ADDRESS", "tcp://182.254.243.31:30011"),
        help="CTP market-data front address",
    )
    parser.add_argument(
        "--brokerid", default=os.getenv("SIMNOW_BROKERID", "9999"), help="CTP broker ID"
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    try:
        settings = MdSettings(
            userid=required_env("SIMNOW_USERID"),
            password=required_env("SIMNOW_PASSWORD"),
            brokerid=args.brokerid,
            address=args.md_address,
        )
    except ValueError as exc:
        print(f"Configuration error: {exc}", file=sys.stderr)
        return 2

    api = PrintMarketDataApi(settings, args.symbol)

    def request_shutdown(signum: int, frame: Any) -> None:
        print("\n[shutdown] stopping market-data client.")
        api.stopped.set()

    signal.signal(signal.SIGINT, request_shutdown)
    if hasattr(signal, "SIGTERM"):
        signal.signal(signal.SIGTERM, request_shutdown)

    try:
        api.start()
        print("[connection] waiting for callbacks; press Ctrl+C to stop.")
        api.stopped.wait()
        return 0
    finally:
        api.close()


if __name__ == "__main__":
    raise SystemExit(main())
