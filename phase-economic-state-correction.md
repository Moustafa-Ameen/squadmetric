# Economic State Correction — Purchase, Market and Selling Prices

## Status

Complete and accepted on 2026-08-10.

This phase fixes a correctness defect in the benchmark and live planner. The
previous implementation refreshed every owned player's `price` to current
market price and then treated that amount as transfer proceeds. That credited
all price-rise profit immediately.

FPL instead returns GBP 0.1m for every complete GBP 0.2m rise while a player is
owned. Price falls are realised in full. The official example is that a player
bought for GBP 5.0m and rising to GBP 5.3m has a selling price of GBP 5.1m.

Official source:

- https://www.premierleague.com/news/2858775

## Implemented contract

Every owned player now carries three distinct values:

```text
purchase_price
current_price
selling_price
```

The spendable legacy `price` field is deliberately set to `selling_price` in
optimizer squad state so older transfer and chip branches cannot silently use
full market value.

The selling calculation uses integer tenths to avoid floating-point drift:

```text
if current_price <= purchase_price:
    selling_price = current_price
else:
    selling_price = purchase_price
                    + floor((current_price - purchase_price) / 2)
```

The implementation now:

- Preserves an owned player's purchase price through market-price refreshes.
- Resets the purchase price when a player is transferred in.
- Uses selling price plus bank for transfer affordability.
- Uses squad selling value plus bank as Wildcard and Free Hit budget.
- Keeps the new Wildcard squad and its new cost bases permanently.
- Restores the original Free Hit squad and its cost bases after the Gameweek.
- Reads live `purchase_price` and `selling_price` values from FPL pick payloads.
- Exposes purchase, current and selling prices in live squad responses.
- Persists squad market value, selling value and spendable team value before
  and after every historical Gameweek decision.

## Benchmark reconciliation

The no-transfer controls are exactly unchanged because player prices do not
affect scoring when no transfer is made.

| Season | Track | Old hindsight | New hindsight | Old realistic | New realistic |
|---|---|---:|---:|---:|---:|
| 2023/24 | No transfers | 772 | 772 | 669 | 669 |
| 2023/24 | Deterministic single transfer | 2,276 | 2,201 | 2,047 | 1,992 |
| 2024/25 | No transfers | 2,174 | 2,174 | 1,963 | 1,963 |
| 2024/25 | Deterministic single transfer | 2,345 | 2,298 | 2,147 | 2,080 |

The reductions of 55 realistic points in 2023/24 and 67 in 2024/25 are the
removal of impossible purchasing power, not a model regression. Future
optimizer improvements must use these corrected totals as their control.

## Verification

- Economic, chip and beam focused tests: 38 passed.
- Transfer-strategy tests: 10 passed.
- Season-benchmark tests: 16 passed.
- Full suite: 249 passed, 93 dependency deprecation warnings.
- Ruff on every changed Python file: passed.
- Frontend ESLint: passed.
- Repository-wide Ruff remains blocked by five pre-existing issues in
  `analysis/fpl_points_gap_recovery.ipynb`; that unrelated notebook was not
  modified during this phase.

Focused tests cover:

- No rise, odd and even price rises, and price falls.
- Purchase-price persistence across deadlines.
- Transfer-in cost-basis reset.
- Rejection of a transfer affordable only at full market value.
- Live FPL purchase/selling-price ingestion.
- Free Hit economic-state restoration.
- Wildcard economic-state permanence.

## Acceptance decision

Accepted. Economic state is now correct and shared by historical transfers,
beam search, chip squad construction and live recommendations.

The next phase may expand the action space to multiple transfers and hits. It
must use this corrected selling-price state and must not rebaseline against the
old inflated totals.
