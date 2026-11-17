import os
import sys
import random
import statistics

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "vendor"))
import makefun_bars

# Named constants (Anti-overfit discipline: all parameters at the top)
FAST_EMA = 12
MED_EMA = 48
SLOW_EMA = 192
MOM_15 = 15
MOM_30 = 30
MOM_60 = 60
ATR_PERIOD = 14
ATR_MEDIAN_WINDOW = 240
HIGHVOL_RATIO_PCT = 140
POSITION_SIZE_NORMAL = 950_000_000  # 95% of equity
POSITION_SIZE_HALF = 475_000_000     # 47.5% of equity
MIN_NOTIONAL = 1_000_000            # 1 USDC
MAX_SLIPPAGE_BPS = 60
TRAILING_ATR_MULT = 7.0
TP_ATR_MULT = 6.0
MAX_HOLD_BARS = 300
COOLDOWN_BARS = 90

# Persistent tracking per symbol
symbol_state = {}

def calc_ema(closes, period):
    if len(closes) < period:
        return closes[-1] if closes else 0
    k = 2.0 / (period + 1)
    ema = closes[0]
    for c in closes[1:]:
        ema = k * c + (1 - k) * ema
    return ema

def calc_atr(bars, period=14):
    if len(bars) < 2:
        return 0.0
    trs = []
    for i in range(1, len(bars)):
        h = int(bars[i]["h"])
        l = int(bars[i]["l"])
        c_prev = int(bars[i-1]["c"])
        tr = max(h - l, abs(h - c_prev), abs(l - c_prev))
        trs.append(tr)
    recent = trs[-period:]
    return sum(recent) / len(recent) if recent else 0.0

def on_hello(state):
    seed = int(state.hello.get("seed", 42))
    random.seed(seed)
    print(f"hello: seed={seed}, symbols={list(state.symbols.keys())}", file=sys.stderr)

def on_batch(state, batch):
    if state.warming_up:
        return []

    orders = []
    for bar in batch["bars"]:
        sym = bar["symbol"]
        if sym not in symbol_state:
            symbol_state[sym] = {
                "history": [],
                "entry_price": None,
                "best_price": None,
                "entry_atr": None,
                "hold_bars": 0,
                "cooldown": 0
            }
        
        st = symbol_state[sym]
        st["history"].append(bar)
        if len(st["history"]) > 500:
            st["history"] = st["history"][-500:]

        bars_list = st["history"]
        if len(bars_list) < SLOW_EMA:
            continue

        closes = [int(b["c"]) for b in bars_list]
        current_close = closes[-1]

        # Indicator calculations
        fast_ema = calc_ema(closes, FAST_EMA)
        med_ema = calc_ema(closes, MED_EMA)
        slow_ema = calc_ema(closes, SLOW_EMA)

        mom_15 = closes[-1] - closes[-1 - MOM_15] if len(closes) > MOM_15 else 0
        mom_30 = closes[-1] - closes[-1 - MOM_30] if len(closes) > MOM_30 else 0
        mom_60 = closes[-1] - closes[-1 - MOM_60] if len(closes) > MOM_60 else 0

        current_atr = calc_atr(bars_list, ATR_PERIOD)
        if current_atr <= 0:
            continue

        # Calculate historical ATRs for median comparison
        atrs = []
        for i in range(max(1, len(bars_list) - ATR_MEDIAN_WINDOW), len(bars_list)):
            sub_bars = bars_list[:i+1]
            atrs.append(calc_atr(sub_bars, ATR_PERIOD))
        median_atr = statistics.median(atrs) if atrs else current_atr
        if median_atr <= 0:
            median_atr = current_atr

        is_high_vol = current_atr > (median_atr * HIGHVOL_RATIO_PCT / 100.0)

        # Regime detection
        is_uptrend = (fast_ema > med_ema > slow_ema) and (mom_60 > 0)
        is_downtrend = (fast_ema < med_ema < slow_ema) and (mom_60 < 0)

        held = state.positions.get(sym)
        has_position = held is not None and held.qty > 0

        if st["cooldown"] > 0:
            st["cooldown"] -= 1

        # Manage open position exits
        if has_position:
            st["hold_bars"] += 1
            if current_close > st["best_price"]:
                st["best_price"] = current_close

            # Exit conditions: downtrend, trailing stop, take profit, or max hold
            trailing_stop_price = st["best_price"] - (TRAILING_ATR_MULT * st["entry_atr"])
            take_profit_price = st["entry_price"] + (TP_ATR_MULT * st["entry_atr"])

            exit_reason = None
            if is_downtrend:
                exit_reason = "regime_downtrend"
            elif current_close <= trailing_stop_price:
                exit_reason = "trailing_stop"
            elif current_close >= take_profit_price:
                exit_reason = "take_profit"
            elif st["hold_bars"] >= MAX_HOLD_BARS:
                exit_reason = "max_hold"

            if exit_reason:
                print(f"bar seq {state.seq}: exiting {sym} qty {held.qty} at close {current_close}, reason: {exit_reason}", file=sys.stderr)
                orders.append({
                    "side": "sell",
                    "symbol": sym,
                    "qty": held.qty,
                    "max_slippage_bps": MAX_SLIPPAGE_BPS
                })
                st["entry_price"] = None
                st["best_price"] = None
                st["entry_atr"] = None
                st["hold_bars"] = 0
                st["cooldown"] = COOLDOWN_BARS
        else:
            # Entry conditions
            if st["cooldown"] == 0 and is_uptrend and not is_high_vol:
                if (mom_15 > 0) and (mom_30 > 0) and (current_close > fast_ema):
                    room = state.weight_room(sym)
                    size = POSITION_SIZE_NORMAL
                    if is_high_vol:
                        size = POSITION_SIZE_HALF
                    notional = min(size, state.cash - 10_000_000, room)
                    if notional >= MIN_NOTIONAL:
                        print(f"bar seq {state.seq}: buying {sym} notional {notional} at close {current_close} (fast={fast_ema:.1f}, atr={current_atr:.1f})", file=sys.stderr)
                        orders.append({
                            "side": "buy",
                            "symbol": sym,
                            "notional_quote_units": notional,
                            "max_slippage_bps": MAX_SLIPPAGE_BPS
                        })
                        st["entry_price"] = current_close
                        st["best_price"] = current_close
                        st["entry_atr"] = current_atr
                        st["hold_bars"] = 0

    return orders

if __name__ == "__main__":
    makefun_bars.run(on_batch, on_hello=on_hello)
