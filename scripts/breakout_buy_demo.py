"""Guarded SimNow round trip, optional --trigger, default queries only.

--execute-simnow explicitly permits one buy-open and matching close-today.
The complete query/reconciliation workflow currently supports ag2612 only.
"""
from simnow.acceptance import main

if __name__ == '__main__':
    raise SystemExit(main())
