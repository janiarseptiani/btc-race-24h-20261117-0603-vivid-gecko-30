# Strategy: multi-timeframe regime detection

## Idea (visual/polish persona)

Treat the bot as a clean signal-visualisation problem: every minute the
bot classifies the market into one legible regime, and the regime — not a
tangle of ad-hoc triggers — decides position and size. The code is
structured so each regime, each indicator and each exit reads like a
labelled panel: one function per signal, one table of named constants,
no magic numbers buried in logic.

## Regimes (from closes only; fills use next bar's open)

- **Trend:** fast EMA (12m) vs slow EMA (192m) plus a medium EMA (48m).
  UPTREND when fast > medium > slow with positive 60-minute momentum;
  DOWNTREND when the reverse; otherwise RANGE.
- **Volatility:** 14-minute ATR as a share of price. HIGHVOL when ATR
  is above its own 240-minute median by a wide margin — in HIGHVOL the
  bot halves size and widens stops, because 1-minute noise then eats
  the ~26 bps round-trip cost.
- **Momentum confirmation:** a buy needs the 15-minute return positive
  and the close above the fast EMA; no chasing after a vertical bar.

## Position rules

- Long only, at most one open position, max 100% of equity.
- Size by regime: full size in a confirmed UPTREND with normal
  volatility, half size in a weak/early uptrend or HIGHVOL, flat in
  DOWNTREND or RANGE.
- Exits: regime flip to DOWNTREND, an ATR-multiple trailing stop from
  the best price since entry, a modest take-profit at a multiple of
  entry ATR, and a maximum holding time so a stale trade cannot bleed
  through a regime change. A short cooldown follows a losing exit.
- Trade sparingly: every round trip costs ~26 bps in fees, slippage and
  impact, so a trade must expect a move clearly larger than that.

## Anti-overfit discipline

- Few parameters, all as named constants at the top of `main.py`.
- No thresholds tuned to specific hours of the dev window; no
  hour-of-day, no calendar, no per-bar special cases.
- Sanity check on both halves of the dev window (first 12h / second
  12h): neither half may be deeply negative, or the rules are too
  fitted to one stretch of the window.
- Deterministic: standard library only, no network, no wall clock, no
  unseeded randomness. State is rebuilt from the hello message and the
  batches alone.

## Dev window (measured 2026-11-17, from the kit dataset)

- CBBTC $64,461 → $64,776 over 24h (+0.49%); range $63,874–$65,467.
- Buy-and-hold max drawdown 2.12%; 1-minute return stdev 6.4 bps;
  116 of 1,439 bars flat. 60-minute returns: p10 −0.67%, p90 +0.61%.
- Median open depth ~$880k, so a full-size $1,000 buy pays ~11 bps of
  price impact on top of 4 bps fee + 2 bps slippage.

## Local grade

(To be filled in by the build session after running replay-driver.py
twice: net PnL, trades, max drawdown, first-half / second-half PnL,
and whether the two action logs matched byte for byte.)
