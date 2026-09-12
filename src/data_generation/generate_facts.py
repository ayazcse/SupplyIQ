"""
Generate fact tables: fact_orders, fact_shipments, fact_inventory_snapshot,
fact_supplier_performance.

APPROACH (documented in docs/data_dictionary.md + architecture.md):
1. For every valid (product, warehouse) pair (derived from the supplier-product
   bridge table — a product is only "stocked" in warehouses it's actually linked
   to), simulate WEEKLY demand and inventory levels across the full 3-year
   horizon using a vectorized (product-warehouse x week) numpy simulation with
   reorder-point / reorder-quantity replenishment logic and supplier lead times.
   This is what makes stockouts, excess inventory, and demand-driven ordering
   causally connected instead of independently random.
2. Two deliberate "shock events" are injected mid-horizon:
     - A supplier deterioration event (a reliable supplier's lead time and OTIF
       degrade sharply for ~10 weeks) -> creates a genuine root-cause story.
     - A demand surge event (a product category spikes in specific regions)
       -> creates a genuine forecasting/stockout-risk story.
   These are the ONLY hand-placed events; everything else emerges from the
   stochastic simulation. This satisfies the "insights must come from the data,
   not be invented after the fact" requirement while still guaranteeing the
   dataset has at least a couple of clear, explainable, headline findings.
3. Weekly aggregates are exploded into individual order-line transactions
   (fact_orders), which are then grouped into consolidated shipments
   (fact_shipments). Weekly inventory levels are sampled down into periodic
   snapshots (fact_inventory_snapshot). Supplier performance is aggregated
   monthly per supplier (fact_supplier_performance).
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))

import numpy as np
import pandas as pd

from config import config as cfg
from src.utils.logger import get_logger

log = get_logger(__name__)
rng = np.random.default_rng(cfg.RANDOM_SEED + 1)

SYN = cfg.SYNTHETIC_DIR


def load_dims():
    dim_date = pd.read_csv(SYN / "dim_date.csv", parse_dates=["date"])
    dim_region = pd.read_csv(SYN / "dim_region.csv")
    dim_warehouse = pd.read_csv(SYN / "dim_warehouse.csv")
    dim_product = pd.read_csv(SYN / "dim_product.csv")
    dim_supplier = pd.read_csv(SYN / "dim_supplier.csv")
    dim_customer_segment = pd.read_csv(SYN / "dim_customer_segment.csv")
    dim_transport_mode = pd.read_csv(SYN / "dim_transport_mode.csv")
    bridge = pd.read_csv(SYN / "bridge_supplier_product.csv")
    return dim_date, dim_region, dim_warehouse, dim_product, dim_supplier, dim_customer_segment, dim_transport_mode, bridge


def build_valid_pairs(dim_product, dim_warehouse, dim_supplier, bridge):
    """One row per (product, warehouse) that actually exists in the business,
    with its PRIMARY supplier and that supplier's baseline reliability stats."""
    primary = bridge[bridge.is_primary_supplier].copy()
    # A product might have >1 primary flagged per warehouse only if data generation
    # quirk; keep first occurrence deterministically.
    primary = primary.drop_duplicates(subset=["product_id", "warehouse_id"], keep="first")
    pairs = primary.merge(dim_product, on="product_id").merge(dim_supplier, on="supplier_id")
    pairs = pairs.merge(dim_warehouse[["warehouse_id", "region_id"]], on="warehouse_id")
    pairs = pairs.reset_index(drop=True)
    pairs["pair_id"] = np.arange(len(pairs))
    return pairs


def simulate_weekly(pairs: pd.DataFrame, dim_date: pd.DataFrame, dim_region: pd.DataFrame):
    n_pairs = len(pairs)
    dd = dim_date.copy()
    iso = dd["date"].dt.isocalendar()
    dd["iso_year"] = iso["year"]
    dd["iso_week"] = iso["week"]
    week_starts = dd.drop_duplicates(subset=["iso_year", "iso_week"]).sort_values("date")["date"].reset_index(drop=True)
    n_weeks = len(week_starts)
    log.info(f"Simulating {n_pairs:,} product-warehouse pairs x {n_weeks} weeks...")

    region_index = pairs.merge(dim_region, on="region_id")["demand_index"].values
    base_daily_demand = pairs["base_daily_demand"].values
    is_seasonal = pairs["is_seasonal"].values
    base_lead_days = pairs["base_lead_time_days"].values
    lead_vol = pairs["lead_time_volatility"].values
    base_otif = pairs["base_otif_rate"].values
    archetype = pairs["archetype"].values

    lead_weeks = np.maximum(1, np.round(base_lead_days / 7)).astype(int)
    weekly_base_qty = base_daily_demand * 7 * region_index
    # Safety-stock policy varies by pair (some warehouses run leaner than others) --
    # calibrated (via empirical testing) to produce a realistic ~5-10% stockout/
    # partial-fulfillment rate overall, rather than a supply chain that never fails.
    safety_factor = rng.uniform(0.55, 1.05, size=n_pairs)
    reorder_point = weekly_base_qty * lead_weeks * safety_factor
    reorder_qty = weekly_base_qty * rng.uniform(1.8, 3.0, size=n_pairs)
    inventory = reorder_qty.copy() * rng.uniform(0.9, 1.3, size=n_pairs)  # start reasonably (not perfectly) stocked

    # --- Deliberate shock events (documented, used to validate root-cause + forecasting) ---
    month_arr = week_starts.dt.month.values
    year_arr = week_starts.dt.year.values
    week_idx_of_year2 = (year_arr == 2024) & np.isin(month_arr, [7, 8, 9])  # deterioration window

    # Event A: supplier deterioration -- pick 2 "reliable" suppliers, degrade for a window
    deteriorating_suppliers = pairs.loc[pairs.archetype == "reliable", "supplier_id"].drop_duplicates().sample(
        n=2, random_state=cfg.RANDOM_SEED).values
    deteriorating_pair_mask = pairs["supplier_id"].isin(deteriorating_suppliers).values

    # Event B: demand surge -- Electronics category, regions North & West, Q4 2024
    surge_pair_mask = (pairs["category"].values == "Electronics") & (pairs["region_id"].isin(
        pairs.loc[pairs["region_id"].isin([1, 4]), "region_id"].unique()).values)

    max_buf = int(lead_weeks.max()) + 3
    pipeline = np.zeros((n_weeks + max_buf, n_pairs))

    demand_log = np.zeros((n_weeks, n_pairs))
    fulfilled_log = np.zeros((n_weeks, n_pairs))
    unmet_log = np.zeros((n_weeks, n_pairs))
    inv_end_log = np.zeros((n_weeks, n_pairs))
    effective_lead_log = np.zeros((n_weeks, n_pairs))
    effective_otif_log = np.zeros((n_weeks, n_pairs))

    for w in range(n_weeks):
        month = month_arr[w]
        seasonal_mult = np.where(is_seasonal & (month >= 10) & (month <= 12), 1.6,
                          np.where(is_seasonal & np.isin(month, [1, 2]), 0.75, 1.0))
        surge_mult = np.where(surge_pair_mask & (year_arr[w] == 2024) & (month >= 10), 1.9, 1.0)
        # Occasional organic demand spikes (independent of the crafted surge event)
        # so volatility -- and the stockouts it causes -- isn't confined to one
        # scripted window; this is what makes stockout risk a learnable pattern.
        spike_mult = np.where(rng.random(n_pairs) < 0.05, rng.uniform(1.5, 2.8, n_pairs), 1.0)
        noise = rng.lognormal(mean=0.0, sigma=0.42, size=n_pairs)
        demand = np.maximum(0, weekly_base_qty * seasonal_mult * surge_mult * spike_mult * noise)

        inventory = inventory + pipeline[w]
        fulfilled = np.minimum(demand, inventory)
        unmet = demand - fulfilled
        inventory = inventory - fulfilled

        # effective supplier reliability this week: organic week-to-week lead-time
        # jitter for everyone, PLUS a sharp degradation for the scripted event window.
        deteriorate_now = deteriorating_pair_mask & week_idx_of_year2[w]
        jitter = rng.uniform(0.85, 1.3, size=n_pairs)
        eff_lead_weeks = np.where(deteriorate_now, np.round(lead_weeks * 1.8).astype(int),
                                   np.maximum(1, np.round(lead_weeks * jitter)).astype(int))
        eff_lead_days = np.where(deteriorate_now, base_lead_days * 1.7 + rng.normal(0, 0.5, n_pairs),
                                  base_lead_days * jitter)
        eff_otif = np.where(deteriorate_now, base_otif * 0.55, base_otif * rng.uniform(0.9, 1.02, n_pairs))
        eff_otif = np.clip(eff_otif, 0.05, 0.99)

        need_reorder = inventory < reorder_point
        order_qty = np.where(need_reorder, reorder_qty, 0.0)
        arrival_w = np.clip(w + eff_lead_weeks, 0, n_weeks + max_buf - 1)
        np.add.at(pipeline, (arrival_w, np.arange(n_pairs)), order_qty)

        demand_log[w] = demand
        fulfilled_log[w] = fulfilled
        unmet_log[w] = unmet
        inv_end_log[w] = inventory
        effective_lead_log[w] = eff_lead_days
        effective_otif_log[w] = eff_otif

    log.info("Weekly simulation complete.")
    return {
        "week_starts": week_starts, "demand": demand_log, "fulfilled": fulfilled_log,
        "unmet": unmet_log, "inv_end": inv_end_log, "eff_lead": effective_lead_log,
        "eff_otif": effective_otif_log, "reorder_point": reorder_point,
        "deteriorating_suppliers": deteriorating_suppliers,
    }


def explode_orders(pairs, sim, dim_customer_segment, dim_transport_mode, target_orders):
    n_weeks, n_pairs = sim["demand"].shape
    week_starts = sim["week_starts"]
    total_units = sim["demand"].sum()
    avg_order_size = total_units / target_orders
    log.info(f"Total simulated demand units: {total_units:,.0f} | target avg order size: {avg_order_size:.2f}")

    seg_ids = dim_customer_segment["customer_segment_id"].values
    seg_weights = dim_customer_segment["avg_order_value_index"].values
    seg_weights = seg_weights / seg_weights.sum()
    mode_ids = dim_transport_mode["transport_mode_id"].values

    rows = []
    order_id = 1
    for w in range(n_weeks):
        week_start = week_starts.iloc[w]
        demand_w = sim["demand"][w]
        unmet_w = sim["unmet"][w]
        active = np.where(demand_w > 0.01)[0]
        for p_idx in active:
            demand_units = demand_w[p_idx]
            n_orders = max(1, int(round(demand_units / avg_order_size)))
            unmet_ratio = unmet_w[p_idx] / demand_units if demand_units > 0 else 0
            row = pairs.iloc[p_idx]
            qty_splits = rng.dirichlet(np.ones(n_orders)) * demand_units
            offer_days = rng.integers(0, 7, size=n_orders)
            stockout_draws = rng.random(n_orders) < unmet_ratio
            seg_draws = rng.choice(seg_ids, size=n_orders, p=seg_weights)
            mode_draws = rng.choice(mode_ids, size=n_orders, p=[0.45, 0.20, 0.15, 0.20])
            lead_mean = sim["eff_lead"][w, p_idx]
            otif_prob = sim["eff_otif"][w, p_idx]
            for k in range(n_orders):
                order_date = week_start + pd.Timedelta(days=int(offer_days[k]))
                qty = max(1, int(round(qty_splits[k])))
                is_stockout = bool(stockout_draws[k])
                promised_lead = max(1, round(lead_mean))
                promised_date = order_date + pd.Timedelta(days=int(promised_lead))
                on_time = rng.random() < otif_prob
                if is_stockout:
                    status = "Stockout" if rng.random() < 0.6 else "Partial"
                    actual_lead_extra = rng.uniform(3, 12)
                else:
                    status = "Fulfilled"
                    actual_lead_extra = 0 if on_time else rng.uniform(1, 6)
                actual_date = promised_date + pd.Timedelta(days=float(actual_lead_extra))
                unit_price = float(row["unit_price"]) * float(rng.uniform(0.97, 1.03))
                rows.append((
                    order_id, order_date.date(), int(row["product_id"]), int(row["warehouse_id"]),
                    int(row["region_id"]), int(seg_draws[k]), int(row["supplier_id"]), int(mode_draws[k]),
                    qty, round(unit_price, 2), round(unit_price * qty, 2), status,
                    promised_date.date(), actual_date.date(), bool(actual_date > promised_date),
                ))
                order_id += 1
        if w % 20 == 0:
            log.info(f"  exploded week {w+1}/{n_weeks} -> {order_id-1:,} orders so far")

    cols = ["order_id", "order_date", "product_id", "warehouse_id", "region_id",
            "customer_segment_id", "supplier_id", "transport_mode_id", "order_qty",
            "unit_price", "revenue", "order_status", "promised_delivery_date",
            "actual_delivery_date", "is_late"]
    df = pd.DataFrame(rows, columns=cols)
    return df


def inject_data_quality_issues(orders: pd.DataFrame) -> pd.DataFrame:
    """Deliberately injects the realistic messiness requested in the spec:
    nulls, duplicates, outliers, inconsistent values -- done AFTER the clean
    business simulation so the data-quality engine has genuine, documented
    issues to find (see docs/data_dictionary.md 'Known Injected Issues')."""
    df = orders.copy()
    n = len(df)

    # 1. Random nulls in a few non-critical columns (~0.4%)
    null_idx = rng.choice(n, size=int(n * 0.004), replace=False)
    df.loc[null_idx, "unit_price"] = np.nan

    null_idx2 = rng.choice(n, size=int(n * 0.003), replace=False)
    df.loc[null_idx2, "transport_mode_id"] = np.nan

    # 2. Duplicate order records (~0.2%) -- common real-world ingestion issue
    dup_idx = rng.choice(n, size=int(n * 0.002), replace=False)
    dup_rows = df.loc[dup_idx]
    df = pd.concat([df, dup_rows], ignore_index=True)

    # 3. Outlier / fat-finger quantities (~0.1%)
    outlier_idx = rng.choice(len(df), size=int(n * 0.001), replace=False)
    df.loc[outlier_idx, "order_qty"] = df.loc[outlier_idx, "order_qty"] * rng.integers(50, 200, size=len(outlier_idx))
    df.loc[outlier_idx, "revenue"] = df.loc[outlier_idx, "order_qty"] * df.loc[outlier_idx, "unit_price"].fillna(0)

    # 4. A few negative costs from a data-entry sign error (~0.05%)
    neg_idx = rng.choice(len(df), size=max(1, int(n * 0.0005)), replace=False)
    df.loc[neg_idx, "unit_price"] = -df.loc[neg_idx, "unit_price"].abs()

    # 5. Inconsistent status casing/labels from a legacy system merge (~0.3%)
    messy_idx = rng.choice(len(df), size=int(n * 0.003), replace=False)
    messy_map = {"Fulfilled": "fulfilled", "Stockout": "STOCKOUT", "Partial": "partial "}
    df.loc[messy_idx, "order_status"] = df.loc[messy_idx, "order_status"].map(messy_map).fillna(df.loc[messy_idx, "order_status"])

    return df.sample(frac=1.0, random_state=cfg.RANDOM_SEED).reset_index(drop=True)


def build_shipments(orders: pd.DataFrame, dim_transport_mode) -> pd.DataFrame:
    """Consolidate order-lines into shipments: several orders going to the same
    warehouse via the same transport mode on the same day are typically shipped
    together in real logistics operations."""
    clean = orders.dropna(subset=["transport_mode_id"]).copy()
    clean["transport_mode_id"] = clean["transport_mode_id"].astype(int)
    group_cols = ["warehouse_id", "supplier_id", "transport_mode_id", "order_date"]
    grouped = clean.groupby(group_cols).agg(
        n_orders=("order_id", "count"),
        total_qty=("order_qty", "sum"),
        avg_promised=("promised_delivery_date", "max"),
        avg_actual=("actual_delivery_date", "max"),
        any_late=("is_late", "max"),
    ).reset_index()

    # Downsample/aggregate further to land near the ~24k shipment target
    grouped = grouped.sample(n=min(cfg.TARGET_SHIPMENTS, len(grouped)), random_state=cfg.RANDOM_SEED).reset_index(drop=True)
    grouped["shipment_id"] = np.arange(1, len(grouped) + 1)
    grouped["ship_date"] = pd.to_datetime(grouped["order_date"]) + pd.to_timedelta(rng.integers(0, 2, size=len(grouped)), unit="D")
    grouped["distance_km"] = rng.uniform(50, 3200, size=len(grouped)).round(1)
    mode_cost = dict(zip(dim_transport_mode.transport_mode_id, dim_transport_mode.relative_cost_index))
    grouped["shipping_cost"] = (grouped["distance_km"] * grouped["transport_mode_id"].map(mode_cost) *
                                 rng.uniform(0.8, 1.2, size=len(grouped)) * (grouped["total_qty"] ** 0.5)).round(2)
    grouped["is_otif"] = ~grouped["any_late"].astype(bool)
    grouped = grouped.rename(columns={"avg_promised": "promised_delivery_date", "avg_actual": "actual_delivery_date"})
    return grouped[["shipment_id", "warehouse_id", "supplier_id", "transport_mode_id", "ship_date",
                     "promised_delivery_date", "actual_delivery_date", "n_orders", "total_qty",
                     "distance_km", "shipping_cost", "is_otif"]]


def build_inventory_snapshots(pairs, sim, target_rows):
    n_weeks, n_pairs = sim["inv_end"].shape
    week_starts = sim["week_starts"]
    # sample a manageable subset of (week, pair) cells, weighted toward monthly cadence
    monthly_weeks = [w for w in range(n_weeks) if w % 4 == 0]
    candidates = [(w, p) for w in monthly_weeks for p in range(n_pairs)]
    chosen = rng.choice(len(candidates), size=min(target_rows, len(candidates)), replace=False)
    rows = []
    for idx in chosen:
        w, p = candidates[idx]
        row = pairs.iloc[p]
        weekly_demand = sim["demand"][w, p]
        avg_weekly_demand = sim["demand"][:, p].mean()
        days_of_supply = (sim["inv_end"][w, p] / (avg_weekly_demand / 7)) if avg_weekly_demand > 0 else 0
        rows.append((
            week_starts.iloc[w].date(), int(row["product_id"]), int(row["warehouse_id"]),
            round(float(sim["inv_end"][w, p]), 1), round(float(sim["reorder_point"][p]), 1),
            round(float(days_of_supply), 1), round(float(weekly_demand), 1),
        ))
    df = pd.DataFrame(rows, columns=["snapshot_date", "product_id", "warehouse_id", "inventory_on_hand",
                                      "reorder_point", "days_of_supply", "week_demand"])
    df.insert(0, "snapshot_id", np.arange(1, len(df) + 1))
    return df.sort_values(["snapshot_date", "warehouse_id", "product_id"]).reset_index(drop=True)


def build_supplier_performance(orders: pd.DataFrame, dim_supplier: pd.DataFrame) -> pd.DataFrame:
    df = orders.copy()
    df["order_date"] = pd.to_datetime(df["order_date"])
    df["actual_delivery_date"] = pd.to_datetime(df["actual_delivery_date"])
    df["month"] = df["order_date"].values.astype("datetime64[M]")
    df["is_late_bool"] = df["is_late"].fillna(False).astype(bool)
    df["fulfilled_flag"] = df["order_status"].astype(str).str.strip().str.lower().eq("fulfilled")
    # Actual realized lead time per order, derived from the simulation itself
    # (order_date -> actual_delivery_date) -- NOT independent noise -- so that
    # injected supplier-deterioration events are visible in this metric too,
    # consistent with the OTIF drop and the root-cause narrative.
    df["realized_lead_days"] = (df["actual_delivery_date"] - df["order_date"]).dt.days.clip(lower=0)

    grp = df.groupby(["supplier_id", "month"]).agg(
        order_count=("order_id", "count"),
        on_time_count=("is_late_bool", lambda x: (~x).sum()),
        fulfilled_count=("fulfilled_flag", "sum"),
        avg_qty=("order_qty", "mean"),
        total_revenue=("revenue", "sum"),
        avg_lead_time_days=("realized_lead_days", "mean"),
    ).reset_index()
    grp["avg_lead_time_days"] = grp["avg_lead_time_days"].round(1)
    grp["otif_rate"] = (grp["on_time_count"] / grp["order_count"]).round(4)
    grp["fill_rate"] = (grp["fulfilled_count"] / grp["order_count"]).round(4)
    grp = grp.merge(dim_supplier[["supplier_id", "supplier_name", "defect_rate", "cost_volatility"]],
                     on="supplier_id")
    grp["defect_rate_observed"] = (grp["defect_rate"] * rng.uniform(0.7, 1.4, size=len(grp))).round(4)
    grp["cost_variance_pct"] = (grp["cost_volatility"] * rng.normal(1.0, 0.3, size=len(grp)) * 100).round(2)
    grp = grp.drop(columns=["defect_rate", "cost_volatility"])
    return grp.rename(columns={"month": "performance_month"}).sort_values(["supplier_id", "performance_month"]).reset_index(drop=True)


def main():
    log.info("Loading dimensions...")
    dim_date, dim_region, dim_warehouse, dim_product, dim_supplier, dim_customer_segment, dim_transport_mode, bridge = load_dims()

    pairs = build_valid_pairs(dim_product, dim_warehouse, dim_supplier, bridge)
    log.info(f"Valid product-warehouse pairs: {len(pairs):,}")

    sim = simulate_weekly(pairs, dim_date, dim_region)

    log.info("Exploding weekly simulation into order-line transactions...")
    orders = explode_orders(pairs, sim, dim_customer_segment, dim_transport_mode, cfg.TARGET_ORDERS)
    log.info(f"Generated {len(orders):,} clean order rows before injecting DQ issues.")

    orders_dirty = inject_data_quality_issues(orders)
    log.info(f"Final fact_orders row count (post DQ-issue injection): {len(orders_dirty):,}")

    shipments = build_shipments(orders, dim_transport_mode)
    log.info(f"fact_shipments: {len(shipments):,} rows")

    inventory_snap = build_inventory_snapshots(pairs, sim, cfg.TARGET_INVENTORY_SNAPSHOTS)
    log.info(f"fact_inventory_snapshot: {len(inventory_snap):,} rows")

    supplier_perf = build_supplier_performance(orders, dim_supplier)
    log.info(f"fact_supplier_performance: {len(supplier_perf):,} rows")

    out = cfg.SYNTHETIC_DIR
    orders_dirty.to_csv(out / "fact_orders.csv", index=False)
    shipments.to_csv(out / "fact_shipments.csv", index=False)
    inventory_snap.to_csv(out / "fact_inventory_snapshot.csv", index=False)
    supplier_perf.to_csv(out / "fact_supplier_performance.csv", index=False)

    # Save which suppliers/events were injected, for transparency & later validation
    events = pd.DataFrame({
        "event_type": ["supplier_deterioration", "supplier_deterioration", "demand_surge"],
        "detail": [
            f"supplier_id={sid} lead-time +70% and OTIF -45% during Jul-Sep 2024"
            for sid in sim["deteriorating_suppliers"]
        ] + ["Electronics category demand +90% in regions 1 & 4 during Oct-Dec 2024"],
    })
    events.to_csv(out / "injected_events_log.csv", index=False)
    log.info("Fact generation complete. Injected events logged to injected_events_log.csv")


if __name__ == "__main__":
    main()
