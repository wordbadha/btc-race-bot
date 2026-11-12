"""Momentum-breakout bot for the make.fun BTC race (agent-fun/bars-replay/v1).

Strategy: buy a strong short-horizon momentum burst, but only when it makes a
new high for the session, then take profit quickly and cut losers fast.

  - Entry: the 15-minute close return exceeds +0.30% AND the close is above
    every close seen so far this session (a new session high). Full size:
    the whole cash balance, capped by the weight room.
  - Exit: take profit at +1.0% over the entry close, stop loss at -1.0%
    under it, or a trailing stop 3% below the highest close since entry
    (a backstop for a run that turns). The whole position is sold at once.
  - After any exit, wait 60 minutes before the next entry, so one burst
    cannot be chased twice.
  - No entry in the last 60 batches: a position opened there would have no
    room to reach its take-profit before the window is flattened.
  - Late-day fallback: if no trade has completed by batch 1200 (the last
    four hours), the entry threshold drops to +0.15%, still requiring a new
    session high, so a quiet day still produces the one trade the guardrails
    require. It never fires on a day that already traded.

Why this shape: on one-minute bars the noise is ~5 bps a minute while a real
intraday trend moves ~0.3% an hour, so slow trend indicators confirm a move
only after it is over and mean-reversion buys every dip of a falling day.
A 15-minute burst at a new high is the earliest moment a genuine intraday
momentum leg is visible, and a 1% take-profit banks it before the leg
plateaus; the stop and the cooldown keep a false burst to a single small
loss. The rule is deliberately coarse (few trades, wide stops) so it does
not depend on the exact shape of any one day.

Deterministic: no wall clock, no environment, no randomness. Every decision
is a pure function of the closes seen so far, so two runs over the same bars
produce byte-identical replies.

Standard library only. The wire protocol is owned by vendor/makefun_bars.py
(a byte-for-byte copy of the kit SDK).
"""

import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "vendor"))
import makefun_bars

SYMBOL = "CBBTC"

# The competition window is 1,440 one-minute bars.
TOTAL_BATCHES = 1440
# Entry: 15-minute close return above this, at a new session high.
JUMP_BARS = 15
JUMP_PCT = 0.003
# Late-day fallback (only if no trade has completed yet).
LATE_SEQ = 1200
LATE_JUMP_PCT = 0.0015
# Exits, as fractions of the entry close.
TAKE_PROFIT = 0.01
STOP_LOSS = 0.01
TRAIL_PCT = 0.03
# Minutes to wait after an exit before the next entry.
COOLDOWN_BARS = 60
# No new entries this close to the end of the window.
NO_ENTRY_LAST = 60
# Slippage cap on every order, in bps (the fill price itself is set by the
# harness; the cap only refuses a fill that moved absurdly far in one bar).
MAX_SLIPPAGE_BPS = 200
# A buy must be worth at least this (the harness minimum notional).
MIN_NOTIONAL = 1_000_000

closes = []
session_high_before = None
session_high = None
entry_price = None
peak = None
cooldown_until = -1
trades_done = 0
# A sell order is out and its fill has not been seen yet. The exit state
# (entry_price/peak) is only cleared once the position is actually gone:
# if the sell is rejected (a gap past the slippage cap) the position is
# still held, the exit conditions still hold, and the sell is simply sent
# again on the next batch. Clearing the state when the sell is *sent*
# would leave a rejected exit with no take-profit or stop left to fire.
exiting = False


def ret_15m():
    """The close now against the close 15 bars back, or None without history."""
    if len(closes) > JUMP_BARS:
        return closes[-1] / closes[-1 - JUMP_BARS] - 1
    return None


def on_batch(state, batch):
    global session_high_before, session_high, entry_price, peak
    global cooldown_until, trades_done, exiting

    for bar in batch["bars"]:
        c = int(bar["c"])
        closes.append(c)
        session_high_before = session_high
        if session_high is None or c > session_high:
            session_high = c
    if not batch["bars"]:
        return []

    held = state.positions.get(SYMBOL)
    c = closes[-1]

    if held is not None:
        if peak is None or c > peak:
            peak = c
        exit_now = False
        if entry_price is not None and c >= entry_price * (1 + TAKE_PROFIT):
            exit_now = True
        if entry_price is not None and c <= entry_price * (1 - STOP_LOSS):
            exit_now = True
        if peak is not None and c <= peak * (1 - TRAIL_PCT):
            exit_now = True
        if exit_now:
            cooldown_until = state.seq + COOLDOWN_BARS
            exiting = True
            return [{"side": "sell", "symbol": SYMBOL, "qty": held.qty,
                     "max_slippage_bps": MAX_SLIPPAGE_BPS}]
        return []

    if exiting:
        # Flat again, so the sell we sent has filled: close the trade out.
        exiting = False
        entry_price = None
        peak = None
        trades_done += 1

    if state.seq < cooldown_until:
        return []
    if state.seq >= TOTAL_BATCHES - NO_ENTRY_LAST:
        return []

    r = ret_15m()
    if r is None:
        return []
    late = state.seq >= LATE_SEQ and trades_done == 0
    threshold = LATE_JUMP_PCT if late else JUMP_PCT
    if r <= threshold:
        return []
    if session_high_before is None or c <= session_high_before:
        return []

    stake = min(state.cash, state.weight_room(SYMBOL))
    if stake < MIN_NOTIONAL:
        return []
    entry_price = c
    peak = c
    return [{"side": "buy", "symbol": SYMBOL, "notional_quote_units": stake,
             "max_slippage_bps": MAX_SLIPPAGE_BPS}]


makefun_bars.run(on_batch)
