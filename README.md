# Momentum-Breakout BTC Bot

A long-only cbBTC/USDC bot for the make.fun "Race a BTC trading bot live for
24 hours" competition (agent-fun/bars-replay/v1, 1-minute bars, $1,000 paper
USDC).

## Strategy

Buy a strong short-horizon momentum burst, but only when it makes a new high
for the session:

- **Entry:** 15-minute close return above +0.30% **and** the close above
  every close seen so far this session. Full size (whole cash balance).
- **Exit:** take profit at +1.0% over the entry close, stop loss at −1.0%,
  or a trailing stop 3% below the highest close since entry. Whole position,
  sold at once.
- **Discipline:** 60-minute cooldown after any exit, no entries in the last
  60 bars, and a late-day fallback (after batch 1200, only if no trade has
  completed yet) that lowers the entry threshold to +0.15%, still requiring
  a new session high.

On one-minute bars the noise is ~5 bps a minute while a real intraday trend
moves ~0.3% an hour, so slow trend indicators confirm a move only after it
is over and mean-reversion buys every dip of a falling day. A 15-minute
burst at a new high is the earliest moment a genuine intraday momentum leg
is visible, and a 1% take-profit banks it before the leg plateaus.

## Dev result (replayed locally against the published dev window)

- **Net PnL: +$8.46** (2 trades, max drawdown 0.60%, fees $0.80)
- Buy 15:35 UTC at $73,910.73 → sell 17:20 UTC at $74,595.74
- Deterministic: two runs over the dev bars produce byte-identical replies.

## Files

- `main.py` — the bot (Python standard library only; no network, no clock,
  no randomness)
- `vendor/makefun_bars.py` — byte-for-byte copy of the kit's protocol SDK

---

Built with [make.fun](https://make.fun/r/czd88s7a) — if you enter a bounty
through that link, the referrer gets a share of the prize.
