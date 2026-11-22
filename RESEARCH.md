# How other trading bots make money — and what it means here

Researched 25 Oct 2026, after the question "use the internet and existing trading bots and see what and
how they are making profits". Sources at the bottom. Read this before changing any strategy rule.

## 1. The base rate, from the regulator's own data

SEBI's fourth study of individual traders in equity derivatives (published Aug 2026, covering FY25 and FY26):

| Fact | Number |
|---|---|
| Individual traders with a net loss, FY26 | **87.7%** |
| Same, FY25 | 91% |
| Traders present for 4 consecutive years who still lost | **96.5%** |
| Net loss, individual traders, FY26 | ₹91,685 crore (FY25: ~₹1.12 lakh crore) |
| Average loss per trader | ~₹1.17 lakh |
| Share of the loss coming from options | 92% |
| Part of the FY26 loss that was **pure transaction cost** (brokerage, exchange, STT) | **₹25,000 crore** |
| Total costs paid by individuals, FY22–FY26 | ~₹1 lakh crore |
| Traders who are essentially option **buyers** | 97% |
| Loss rate, "only option buyers" | **90%** |
| Loss rate, "predominantly option sellers" (best group) | 44% |
| Average loss **when** a seller loses | ₹51.7 lakh — 11x a buyer's |
| Prop desks / FPIs | +₹44,000 cr / +₹14,000 cr gross, **99% of it to algorithmic entities** |

Two things follow, and they are not comfortable:

1. **All the money on the other side is made by market-making and latency, not by retail indicator
   bots.** "Algo trading is profitable" is true of desks with capital, colocation and rebates. It says
   nothing about a one-machine Python bot on a retail API.
2. **The only category with a loss rate below 50% is premium selling**, and its losses are
   catastrophic and rare. That is the shape of the variance risk premium: collect small, pay huge.

## 2. What the retail-visible bots actually do

Open-source Indian bot collections (e.g. `buzzsubash/algo_trading_strategies_india`) and the commercial
strategy marketplaces (Tradetron, AlgoTest and similar) cluster hard on one family:

- **short straddle / short strangle at 09:20** on expiry day
- **iron fly / iron condor** — the same, hedged
- risk control by **MTM stop** (fixed %, trailing %, or account-level), a **daily profit target**, and a
  forced square-off by 15:15
- almost nothing that buys breakouts

That is consistent with section 1: retail bots sell the variance premium. High win rate, small average
win, occasional account-level loss. None of these bots are verifiable: the published numbers are backtests
or hand-picked screenshots, and the marketplaces' "live" feeds are self-reported.

**None of them can be run on ₹10,000.** One short NIFTY straddle needs roughly ₹1.2–1.5 lakh of SPAN +
exposure margin. A defined-risk spread is the only selling structure small enough, and at ₹10k the widest
spread you can margin is ~100 points — max profit a couple of thousand, max loss most of the account.
Selling is not available at this account size, in any variant.

## 3. Does breakout *buying* have an edge at all?

The best independent, fully-specified test is an ORB study on MNQ (Micro Nasdaq futures), 2019–2026, with
commissions and margin modelled, split in-sample 2020–2022 and out-of-sample 2023–2026:

| | In-sample | Out-of-sample |
|---|---|---|
| Trades | 451 | 474 |
| Win rate | 30.4% | **24.9%** |
| Profit factor | 1.43 | **1.32** |
| Max drawdown | −10.9% | −12.8% |
| Sharpe | 1.37 | 1.10 |

Its verdict: "ORB is not a magical strategy. But when engineered and tested properly, it does not appear to
be a backtest illusion either." Three engineering details did the work, and they are the transferable part:

1. a **trend filter** (200-day SMA) so it only breaks in the direction of the larger trend;
2. a **hard cap on the stop distance** (150 ticks ≈ 1% of capital) because wide-range opens otherwise
   produce losses far beyond the risk plan;
3. **stop for the day after one losing trade**, because ORB overtrades chop.

This repo's First-Hour is the same idea and reports **PF 1.41 over 549 trades** — which is almost exactly
the *in-sample* number of that study, and its out-of-sample decayed to 1.32. So: treat 1.41 as the
optimistic end of the range, expect meaningfully less live, and treat the ex-expiry-day **PF 1.15** as the
more honest estimate.

## 4. What this means for this bot

- **It is an option buyer**, i.e. the 90%-lose bucket. That is not a reason to stop; it is a reason for
  the go/no-go gate to be strict and for the paper record to be the only thing that decides.
- **Costs are the mechanism, not a rounding error.** At 65 lots, one round trip costs ~₹60 (STT 0.15% on
  the sell side, exchange, brokerage, GST — the model in `config.CHARGES` is accurate). ~250 trades/year
  is ~₹15,000/year, i.e. **150% of a ₹10k account, every year**. SEBI puts 27% of retail losses in exactly
  this bucket.
- **Capital is the binding constraint, not the edge.** One NIFTY lot at a ~₹80 premium is ₹5,200 ≈ half
  the account; the rule's own 2-year worst drawdown (−₹28.7k) is ~3x the account. The paper book takes at
  least 1 lot even when the risk budget says otherwise, which is why the Settings ruin table says 41%.
- **Verified constants** (checked against current NSE/BSE data, Oct 2026): NIFTY lot **65** (cut from 75
  from the Jan 2026 series), Bank Nifty 30, SENSEX 20; NSE index F&O expires **Tuesday**, BSE **Thursday**.
  The repo's `INSTRUMENTS` and expiry logic match — no change needed.

## 5. Changes made because of this

1. **`go_no_go` now fails on unaffordable trades.** It counted a trade that took more risk than the
   settings allow (the paper book flags these `oversize`) as if it were a normal trade. A GO now requires
   zero oversize trades, plus the five original checks. Rationale: the paper book is allowed to take
   minimum 1 lot so it stays comparable with the lab, but an account that cannot fund the position did not
   really take the trade, and SEBI's small-account data is precisely the story of doing it anyway.

Open items that follow from the research are in `TODO.md`.

## Sources

- SEBI FY25/FY26 study, reported 24 Aug 2026 — https://www.newindianexpress.com/business/2026/Aug/24/practice-isnt-making-you-a-better-fo-trader
- SEBI FY25 study coverage — https://www.business-standard.com/markets/news/net-losses-of-traders-in-fo-widens-in-fy25-sebi-study-125070701221_1.html
- Retail option-selling bot collection (strategy inventory) — https://github.com/buzzsubash/algo_trading_strategies_india
- ORB in-sample/out-of-sample futures study, Mar 2026 — https://backtestsnotsignals.substack.com/p/opening-range-breakout-real-edge
- ORB literature (index futures, 1-minute) — https://ieeexplore.ieee.org/abstract/document/8641124
- Lot sizes and expiry days, 2026 — https://onetradejournal.com/fno-lot-size-expiry-calendar , https://fyers.in/notice-board/revision-in-index-derivatives-contracts-lot-size
