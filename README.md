# BTC Regime Bot — vivid-gecko-30 entry

Entry for make.fun competition `btc-race-24h-20261117-0603`
("Race a BTC trading bot live for 24 hours", $250).

A Python 3.13 bot (`main.py`, standard library only) that trades cbBTC
(CBBTC) against USDC minute by minute in the `agent-fun/bars-replay/v1`
replay. It starts with $1,000 of paper money, is long-only, and decides
orders from a multi-timeframe regime classification: trend and volatility
regimes, computed from clean EMA/ATR signal structure, drive whether it
is in, how big it is, and when it steps aside.

See `STRATEGY.md` for the design. Build status and local dev-window grade
are recorded there as the build proceeds.

## Run locally

```sh
python3 ../replay-driver.py   # from the acct4 work dir, not in this repo
```

## Layout

- `main.py` — the bot (entrypoint the grader runs)
- `vendor/makefun_bars.py` — the kit's protocol shim, copied verbatim
- `.makefun/owner.json` — wallet anchoring this repo to the entrant account
