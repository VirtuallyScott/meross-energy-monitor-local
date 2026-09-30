# SRD 05 — Billing and Tariffs

The bill engine prices measured energy for a site using a rate plan. It must handle the simplest case (one price per kWh) and real utility tariffs (time-of-use, tiers, seasons, demand charges, net metering, taxes) with one model.

The engine is a **pure function**: `(interval data, rate plan versions, billing cycle, credit bank in) → (bill estimate, credit bank out)`. It does no I/O, which keeps it fully unit-testable (TST-001).

## 1. Inputs

| Input | Source |
|---|---|
| Grid import and export kWh per interval | Site's grid circuit (SITE-004), from `energy_15m` (demand, TOU) or `energy_hourly` |
| Solar generation kWh per interval | Site's solar circuit, only for buy-all/sell-all |
| Rate plan versions | `site_rate_assignment` for the cycle dates |
| Billing cycle | `billing_cycle` for the site |
| Credit bank | Carried from the previous cycle (net metering) |
| Calibration factor | `site_rate_assignment.calibration_factor`, default 1.0 (BIL-052) |

If no grid circuit is configured, the engine uses the load circuit and treats export as zero, with a warning on the estimate.

## 2. Rate plan structure

```
rate_plan  "Utility X — Residential TOU-D"
  └── rate_plan_version  effective 2026-01-01 → open
        ├── settings: netting mode, netting interval, tier allocation, proration, rounding
        ├── seasons:        Summer Jun 1 – Sep 30, Winter Oct 1 – May 31
        ├── tou_periods:    ON_PEAK, MID_PEAK, OFF_PEAK
        ├── tou_rules:      (season, day type, start, end) → period
        ├── holiday calendar
        └── components:     fixed, energy, demand, export credit, minimum, tax, credit
```

| ID | Pri | Requirement |
|---|---|---|
| BIL-010 | M | Rate plans live in a shared library. A plan has one or more **versions** with `effective_from` and optional `effective_to`. Versions of one plan must not overlap. |
| BIL-011 | M | Editing a version that has been used by a saved estimate creates a new version instead of changing it in place, so past estimates stay reproducible. |
| BIL-012 | M | A site is assigned a plan for a date range (`site_rate_assignment`). Assignments of one site must not overlap. |
| BIL-013 | M | Each interval is priced with the plan version in effect at that interval's local timestamp. A cycle that spans a version change is split by interval, and fixed charges are prorated by days (BIL-040). |
| BIL-014 | M | Plan editor validates on save: seasons cover all 365/366 days without overlap; TOU rules cover all 24 h for every season and day type without overlap; tiers are contiguous; every energy component resolves for every interval. Errors name the gap or overlap. |
| BIL-015 | M | Plan import and export as JSON (schema in §8), so plans can be shared and version-controlled. |
| BIL-016 | S | Plan templates: "Flat", "Flat + tiers", "Two-period TOU", "Three-period TOU with seasons", "TOU + NEM", "Net billing". |

## 3. Components

| Kind | Unit | Applies to | Pri | Notes |
|---|---|---|---|---|
| `fixed` | per cycle, per day | — | M | Customer or service charge. Per-cycle charges prorated by days when a cycle is short, long or split |
| `energy` | per kWh | import, gross import, net import | M | May be filtered by season, TOU period and tier. Riders, fuel adjustments and delivery charges are more `energy` components |
| `export_credit` | per kWh | export | M | Negative amount. Filterable by season and period. Used by net billing |
| `demand` | per kW | max demand | S | Filterable by season and TOU period. Window 15, 30 or 60 min |
| `minimum` | per cycle | bill subtotal | M | Raises the bill to a minimum amount |
| `tax` | percent | chosen base | M | Base is the subtotal, or a list of named components. Taxes can stack (tax on tax) in a defined order |
| `credit` | per cycle | — | S | Fixed rebate or program credit |

Every per-kWh component has a `nonbypassable` flag. Non-bypassable charges are always charged on **gross import** and are never offset by exports or credits (common in net metering tariffs).

## 4. Time of use

| ID | Pri | Requirement |
|---|---|---|
| BIL-020 | M | A version defines named TOU periods (for example `ON_PEAK`, `MID_PEAK`, `OFF_PEAK`, `SUPER_OFF_PEAK`) with a display color. A flat plan has a single implicit period `ALL`. |
| BIL-021 | M | Seasons are month-day ranges that may wrap the year end (for example Nov 1 – Mar 31). |
| BIL-022 | M | Day types: `weekday`, `weekend`, `holiday`. Holidays come from a holiday calendar attached to the version. A holiday uses the holiday rules; if none exist it falls back to weekend rules. |
| BIL-023 | M | TOU rules use **local wall-clock time** in the site time zone: start inclusive, end exclusive, `24:00` allowed as an end. A rule may cross midnight (for example 21:00–07:00). |
| BIL-024 | M | DST: on a 23-hour day the skipped hour has no intervals. On a 25-hour day the repeated hour is priced twice by its wall-clock period. Tests must cover both transitions (TST-003). |
| BIL-025 | M | Intervals are 15 minutes. Any TOU boundary not on a 15-minute mark is rejected by validation. |
| BIL-026 | S | Built-in US federal holiday generator with observed-date rules. Users can add or remove dates. |

## 5. Tiers (block rates)

| ID | Pri | Requirement |
|---|---|---|
| BIL-030 | M | An energy component can carry `tier_min_kwh` and `tier_max_kwh`. Tier thresholds apply to cumulative billable import in the cycle. |
| BIL-031 | M | Tier basis: `per_cycle` (fixed kWh thresholds) or `per_day_baseline` (threshold = allowance kWh/day × days in cycle, as with California baseline allowances). Baseline allowance may vary by season. |
| BIL-032 | M | Tier allocation when combined with TOU, set per version: `proportional` (each TOU period's kWh split across tiers in the same ratio as the cycle total; the default) or `chronological` (tiers fill in time order). |
| BIL-033 | S | Declining-block tiers (lower price at higher usage) are allowed; validation only checks contiguity. |

## 6. Net metering and export

| ID | Pri | Requirement |
|---|---|---|
| BIL-039 | M | Each version has a `netting_mode`, one of the values in the table below. |
| BIL-034 | M | Each version has a `netting_interval`: `instantaneous` (use the device's per-minute import and export as-is), `15min`, `hourly`, `daily` or `cycle`. Netting at interval *i*: `net = import − export`; positive becomes billable import, negative becomes billable export. |
| BIL-035 | M | Credit bank per site: `kwh_balance` and `money_balance`, carried between cycles. Each estimate records bank in and bank out. |
| BIL-036 | M | True-up: a version can set a `true_up_month`. At the end of that cycle, remaining kWh credit is paid out at `surplus_rate` (net surplus compensation) or forfeited, per the version's `true_up_policy`, and the bank resets. |
| BIL-037 | M | Credits never offset fixed, minimum, demand or non-bypassable charges unless the version sets `credits_offset_fixed = true`. |
| BIL-038 | S | Export rates may be a full schedule: a 12 × 2 × 24 matrix (month × weekday/weekend × hour), as with avoided-cost net billing tariffs. |

| `netting_mode` | Behaviour | Typical tariff |
|---|---|---|
| `none` | Imports billed; exports ignored | No solar, or exports uncompensated |
| `nem_kwh` | Net kWh over the netting interval, per TOU period when TOU. Positive net billed at retail. Negative net goes to the kWh bank and is used against later positive net, oldest first, in the same TOU period when possible | Classic 1:1 net metering, monthly or annual netting |
| `nem_retail_credit` | Imports billed at retail. Exports credited at the **retail rate of the interval they occurred in** (all non-bypassable charges excluded). Credits go to the money bank and offset later energy charges | NEM 2.0 style |
| `net_billing` | Imports billed at retail per netting interval. Exports credited at `export_credit` rates (flat, TOU or matrix). Excess credit goes to the money bank | NEM 3.0 / net billing tariff |
| `buy_all_sell_all` | All site consumption billed at retail. All solar generation credited at the feed-in rate. Uses the load and solar circuits, not the grid circuit | Feed-in tariff, value-of-solar |

## 7. Calculation

### 7.1 Algorithm

For one site and one billing cycle `[start, end)` in local time:

1. Convert the cycle bounds to UTC with the site time zone.
2. Load 15-minute import and export kWh for the grid circuit (or load and solar for `buy_all_sell_all`). Apply the calibration factor.
3. Tag each interval with plan version, season, day type and TOU period.
4. Apply netting per version settings to get billable import and billable export per interval.
5. Allocate billable import to tiers (BIL-032).
6. Price energy components per interval, period and tier. Price non-bypassable components on gross import.
7. Price demand: for each demand component, max over matching intervals of `kWh × (60 / window_minutes)` using window-length sums, times the rate.
8. Price export credits (or apply NEM bank logic).
9. Add fixed charges, prorated by days in cycle (BIL-040).
10. Apply credit bank per BIL-035 to BIL-037.
11. Apply minimum bill.
12. Apply taxes in their defined order.
13. Round line items to currency minor units (BIL-041). Total = sum of rounded line items.

### 7.2 Rules

| ID | Pri | Requirement |
|---|---|---|
| BIL-040 | M | Proration: per-cycle fixed charges × (days in cycle / 30.4375) when `proration = standard_month`, or × (days in portion / days in cycle) when a cycle is split by version change. Per-day charges × days. |
| BIL-041 | M | All money math uses decimal arithmetic (Python `Decimal`, Postgres `numeric`). No floats in the billing path. Rates stored with 6 decimal places. Rounding mode half-up by default, configurable per version. |
| BIL-042 | M | Each estimate stores line items: component, label, quantity, unit, rate, amount, TOU period, tier, season. The UI and export show the full breakdown. |
| BIL-043 | M | Each estimate stores **data coverage** (% of intervals with data), the share of `estimated` rows, and warnings (missing grid circuit, gaps over 1 h, rate version change mid-cycle). Coverage under 98% is shown prominently. |
| BIL-044 | M | Missing intervals are not filled by default. A per-estimate option fills gaps from the same weekday and hour average of the previous 4 weeks, and marks the estimate as gap-filled. |
| BIL-045 | M | Estimates record an input hash (data version, plan versions, cycle, bank in). If later data backfill or a plan change alters the hash, the estimate is flagged **stale** and a recalculation job is queued. |

## 8. Billing cycles

| ID | Pri | Requirement |
|---|---|---|
| BIL-046 | M | Cycle rules per site: `calendar_month`, `day_of_month` (for example the 17th) or `manual` (a user enters each meter-read date). |
| BIL-047 | M | A new cycle is opened automatically at each boundary. A closed cycle's estimate is computed once the aggregates for its last day are final (default 2 h after close). |

## 9. Outputs and features

These refine BIL-006 in SRD 01 (estimate for any past or current cycle).

| ID | Pri | Requirement |
|---|---|---|
| BIL-050 | M | **Projection** for the open cycle: actual to date plus a forecast for the remaining days, using the same weekday and hour load profile over the previous 28 days (so TOU mix is kept), with a low and high band from the 10th and 90th percentile days. Falls back to daily average if under 7 days of history. |
| BIL-051 | M | **Plan comparison**: price the same data for the last N cycles (default 12, or what exists) under 2 to 5 plans. Show per-cycle and total cost, and the difference versus the current plan. |
| BIL-052 | S | **Reconciliation**: user records an actual bill (cycle dates, import kWh, export kWh, total). The system shows kWh and cost variance and suggests a calibration factor = actual kWh / measured kWh. Applying it is an explicit user action, audited. |
| BIL-053 | M | **Cost per circuit**: allocate each interval's energy charges to circuits in proportion to their kWh in that interval. Fixed, demand, minimum and tax lines are shown as a separate "fixed and other" line, not allocated, unless the user picks proportional allocation. The unmetered remainder is its own row. |
| BIL-054 | M | Live **cost rate** on the overview: current import power × the current interval's marginal energy price (sum of per-kWh components for the current period and tier). |
| BIL-055 | S | Daily cost chart for the cycle, stacked by TOU period. |
| BIL-056 | C | What-if: scale a circuit's usage or shift a percentage of it between TOU periods (for example "run the pool pump off-peak") and show the change in cost. |
| BIL-060 | C | Import a tariff from the OpenEI Utility Rate Database JSON format. Opt-in, uses the network only when the user triggers it. |

## 10. Worked examples (test fixtures)

All use a 30-day cycle, USD. These become unit tests (TST-001).

**E1 — Flat.** 900 kWh at $0.14, fixed $12.00/cycle, 5% tax on subtotal.

| Line | Amount |
|---|---|
| Energy 900 kWh × 0.14 | 126.00 |
| Fixed charge | 12.00 |
| Subtotal | 138.00 |
| Tax 5% | 6.90 |
| **Total** | **144.90** |

**E2 — TOU.** On-peak weekdays 16:00–21:00 at $0.32; off-peak all other times at $0.11. Usage: 180 kWh on-peak, 720 kWh off-peak. Fixed $12.00, no tax.
Energy 57.60 + 79.20 = 136.80. **Total 148.80.**

**E3 — Tiered.** 0–500 kWh at $0.12, 500–1,000 at $0.15, above 1,000 at $0.20. Usage 1,150 kWh.
Energy 60.00 + 75.00 + 30.00 = 165.00. **Total 165.00** (no fixed or tax).

**E4 — NEM kWh, monthly netting.** Flat $0.14 energy, plus $0.02 non-bypassable on gross import. Fixed $12.00. Import 700 kWh, export 400 kWh.
Net 300 kWh × 0.14 = 42.00. Non-bypassable 700 × 0.02 = 14.00. Fixed 12.00. **Total 68.00.** Bank unchanged.
Variant: export 900 kWh. Net −200 kWh: energy 0.00, bank +200 kWh. Non-bypassable 14.00, fixed 12.00. **Total 26.00.**

**E5 — Net billing.** Import $0.14, export credit $0.05, hourly netting. After netting: 700 kWh import, 400 kWh export. Fixed $12.00.
Import 98.00, export credit −20.00, fixed 12.00. **Total 90.00.**

**E6 — Demand.** Highest 15-minute interval in the cycle holds 2.1 kWh, so demand = 2.1 × 4 = 8.4 kW. Rate $9.50/kW. Demand charge **79.80.**

**E7 — DST.** A TOU cycle containing the spring-forward day has 2,876 intervals rather than 2,880 for 30 days; the fall-back day adds 4. Totals must match a hand-computed fixture.

## 11. Data model

```sql
rate_plan (id uuid pk, name text, utility text, description text, currency char(3), archived_at)

rate_plan_version (
  id uuid pk, plan_id uuid, version_no int, effective_from date, effective_to date null,
  netting_mode text, netting_interval text, tier_allocation text,
  credits_offset_fixed bool default false, true_up_month smallint null,
  true_up_policy text null, surplus_rate numeric(12,6) null,
  proration text default 'standard_month', rounding_mode text default 'half_up',
  holiday_calendar_id uuid null, locked bool default false,       -- locked once used (BIL-011)
  notes text
)

season (id uuid pk, version_id uuid, name text, start_month smallint, start_day smallint,
        end_month smallint, end_day smallint, baseline_kwh_per_day numeric(10,3) null)

tou_period (id uuid pk, version_id uuid, code text, name text, color text, sort smallint)

tou_rule (id uuid pk, version_id uuid, season_id uuid null, day_type text,
          start_time time, end_time time, period_id uuid)   -- end 24:00 stored as '24:00'

rate_component (
  id uuid pk, version_id uuid, kind text, name text, sort smallint,
  amount numeric(12,6), unit text,                 -- per_kwh, per_kw, per_day, per_cycle, percent
  applies_to text null,                            -- import, gross_import, net_import, export
  season_id uuid null, period_id uuid null,
  tier_min_kwh numeric(12,3) null, tier_max_kwh numeric(12,3) null, tier_basis text null,
  demand_window_min smallint null,
  nonbypassable bool default false,
  tax_base jsonb null                              -- 'subtotal' or list of component ids
)

export_rate_matrix (version_id uuid, month smallint, day_type text, hour smallint, rate numeric(12,6),
                    primary key (version_id, month, day_type, hour))

holiday_calendar (id uuid pk, name text)
holiday (calendar_id uuid, day date, name text, primary key (calendar_id, day))

site_rate_assignment (id uuid pk, site_id uuid, plan_id uuid, effective_from date,
                      effective_to date null, calibration_factor numeric(8,5) default 1)

billing_cycle_rule (site_id uuid pk, kind text, day_of_month smallint null)
billing_cycle (id uuid pk, site_id uuid, start_date date, end_date date, status text)  -- open, closed

credit_bank_entry (id uuid pk, site_id uuid, cycle_id uuid, kwh_delta numeric, money_delta numeric,
                   reason text, created_at)

bill_estimate (id uuid pk, site_id uuid, cycle_id uuid, kind text,        -- actual_to_date, projection, comparison
               plan_version_ids uuid[], computed_at, input_hash text, stale bool,
               coverage_pct numeric(5,2), estimated_pct numeric(5,2), gap_filled bool,
               bank_in jsonb, bank_out jsonb, subtotal numeric(12,2), total numeric(12,2),
               currency char(3), warnings jsonb)

bill_line_item (estimate_id uuid, sort smallint, component_id uuid null, label text,
                quantity numeric(14,6), unit text, rate numeric(12,6), amount numeric(12,2),
                season text null, period text null, tier smallint null)

actual_bill (id uuid pk, site_id uuid, start_date date, end_date date,
             import_kwh numeric(12,3), export_kwh numeric(12,3), total numeric(12,2),
             notes text, created_by uuid, created_at)
```
