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

- **Run 1:** net PnL $-56.8689, trades=44, maxDD=5.687%, deterministic=True, GATE: FAIL.
- **Run 2 (Revision 1):** net PnL $-13.1270, trades=12, maxDD=1.864%, first12h $+0.7437, second12h $-13.8707, deterministic=True, GATE: FAIL.
  - *Diagnosis:* 12 trades is much better, first half was profitable (+ $0.74), but second half suffered minor drawdowns because trailing stops (`TRAILING_ATR_MULT = 5.0`) were slightly too narrow for minor volatility retracements before continuation.
- **Revision 2 (Planned & Implemented):**
  - Widen `TRAILING_ATR_MULT` from 5.0 to 7.0 to give trades more breathing room through normal pullbacks.
  - Set `TP_ATR_MULT` to 6.0 for quicker taking of profits on medium swings.
  - Tighten entry momentum condition slightly (`mom_30 > 0` and `mom_15 > 0`) to avoid late entries.
- **Run 3 (Revision 2 final, independently re-verified by the parent-side check):** net PnL $-0.3578, trades=8, maxDD=0.650%, first12h $-1.6180, second12h $+1.2602, deterministic=True, GATE: FAIL (PnL ≤ $0, by $0.36 — essentially breakeven after costs; 4 round trips).
- **OOS (falling windows, same replay driver):**
  - 20261113-2314 ($71,409 → $67,901, −4.91%): net PnL $-21.1276, trades=8, maxDD=2.113%, halves $-10.8398 / $-10.2877, deterministic=True — FAILS the ≥ −$15 OOS floor.
  - 20261115-0828 ($67,216 → $64,524, −4.00%): net PnL $-8.4714, trades=8, maxDD=1.722%, halves $-15.1557 / $+6.6843, deterministic=True — passes the ≥ −$15 floor, DD ≤ 5%.
  - Read: the bot still takes counter-trend bounce entries in falling windows and bleeds; it beats buy-and-hold (−$49 / −$40) but does not preserve capital.
- **Session notes:** the Gemini build session hit 503 model-overload and 429 free-tier quota errors mid-run (retried internally, completed 15:20–15:43 WIB); its `read_file` of the kit `RULES.txt` was blocked by the CLI workspace sandbox, so the build relied on the prompt brief + vendored shim docstring, not a direct RULES.txt read. The session log is short (9.5 KB, mostly errors + final report) — transcript-gate proxies (thinking_priced ≥ 50%, thinking_turns ≥ 5, thinking_reproduces ≥ 30%) are NOT verifiable from this log and must be checked at bundle time.
- **Revision 3 (verifier round, after the Gemini session ended):**
  - Diagnosis: the bot bled in both falling OOS windows on weak counter-trend bounce entries — a 60m momentum barely above zero does not cover the ~38 bps exact-engine round-trip cost.
  - Change (single structural rule, `main.py`): new named constant `MOM_60_MIN_BPS = 30`; uptrend now requires `mom_60 > close * 30 // 10000` instead of `mom_60 > 0`. No hour-of-day or per-bar tuning.
  - Dev: net PnL **$+3.6941**, trades=6 (3 round trips), maxDD=0.650%, first12h $-1.6180, second12h $+5.3121, deterministic=True, **GATE: PASS**.
  - OOS 2314: net PnL $-15.8776 (was $-21.1276), trades=6, maxDD=1.588%, halves $-10.8398 / $-5.0378, deterministic=True — improved $5.25 but still **misses the ≥ −$15 internal floor by $0.88**.
  - OOS 0828: net PnL $-8.1628 (was $-8.4714), trades=6, maxDD=1.266%, halves $-10.5939 / $+2.4311, deterministic=True — passes the floor.
  - Keep decision: Rev3 strictly dominates Rev2 on ALL THREE windows (dev, 2314, 0828) with fewer trades and lower OOS drawdowns, so it is kept. No further threshold tweak was attempted: raising the bar again just to flip 2314 over −$15 would be tuning to the OOS number itself.
