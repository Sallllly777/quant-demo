"""Continuously print SimNow ticks for a small, replaceable active-contract set.

This stays at the low-level vnpy_ctp.api.MdApi layer.  It does not submit
orders and exits only after Ctrl+C (or a login failure).
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


# Checked on 2026-09-19.  Override with --symbols when the dominant month rolls.
DEFAULT_SYMBOLS = ("rb2701", "i2701", "IF2612")


@dataclass(frozen=True)
class MdSettings:
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


class ContinuousMarketDataApi(MdApi):
    """Log in once and continuously print ticks for several CTP instruments."""

    def __init__(self, settings: MdSettings, symbols: tuple[str, ...]) -> None:
        super().__init__()
        self.settings = settings
        self.symbols = symbols
        self.request_id = 0
        self.stopped = Event()

    def _next_request_id(self) -> int:
        self.request_id += 1
        return self.request_id

    def onFrontConnected(self) -> None:
        print("[connection] front connected; requesting login.")
        self.reqUserLogin(self.settings.login_request(), self._next_request_id())

    def onFrontDisconnected(self, reason: int) -> None:
        print(f"[connection] front disconnected (reason={reason}).", file=sys.stderr)

    def onRspUserLogin(self, data: dict, error: dict, reqid: int, last: bool) -> None:
        if error.get("ErrorID", -1):
            print(
                f"[login] failed (error={error.get('ErrorID')}): [message omitted]",
                file=sys.stderr,
            )
            self.stopped.set()
            return

        print("[login] successful; subscribing to", ", ".join(self.symbols))
        for symbol in self.symbols:
            self.subscribeMarketData(symbol)

    def onRspError(self, error: dict, reqid: int, last: bool) -> None:
        print(
            f"[ctp-error] request={reqid}, error={error.get('ErrorID')}: "
            f"[message omitted]",
            file=sys.stderr,
        )

    def onRspSubMarketData(self, data: dict, error: dict, reqid: int, last: bool) -> None:
        symbol = data.get("InstrumentID", "<unknown>")
        if error.get("ErrorID", -1):
            print(
                f"[subscribe] rejected: {symbol}; error={error.get('ErrorID')}: "
                f"[message omitted]",
                file=sys.stderr,
            )
        else:
            print(f"[subscribe] accepted: {symbol}")

    def onRtnDepthMarketData(self, data: dict) -> None:
        """Print the main fields in every CTP depth-market callback."""
        millisec = data.get("UpdateMillisec") or 0
        print(
            "[tick] "
            f"symbol={data.get('InstrumentID')} "
            f"time={data.get('ActionDay') or data.get('TradingDay')} "
            f"{data.get('UpdateTime')}.{millisec:03d} "
            f"last={data.get('LastPrice')} volume={data.get('Volume')} "
            f"bid1={data.get('BidPrice1')}@{data.get('BidVolume1')} "
            f"ask1={data.get('AskPrice1')}@{data.get('AskVolume1')}",
            flush=True,
        )

    def start(self) -> None:
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
    parser = argparse.ArgumentParser(description="Continuous vnpy_ctp SimNow market-data demo")
    parser.add_argument(
        "--symbols",
        nargs="+",
        default=DEFAULT_SYMBOLS,
        help="instrument IDs to subscribe; default: %(default)s",
    )
    parser.add_argument(
        "--md-address", default=os.getenv("SIMNOW_MD_ADDRESS", "tcp://182.254.243.31:30011")
    )
    parser.add_argument("--brokerid", default=os.getenv("SIMNOW_BROKERID", "9999"))
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

    api = ContinuousMarketDataApi(settings, tuple(args.symbols))

    def request_shutdown(signum: int, frame: Any) -> None:
        print("\n[shutdown] Ctrl+C received; closing market-data API.")
        api.stopped.set()

    signal.signal(signal.SIGINT, request_shutdown)
    if hasattr(signal, "SIGTERM"):
        signal.signal(signal.SIGTERM, request_shutdown)

    try:
        api.start()
        print("[connection] streaming indefinitely; press Ctrl+C to stop.")
        api.stopped.wait()
        return 0
    finally:
        api.close()


if __name__ == "__main__":
    raise SystemExit(main())
