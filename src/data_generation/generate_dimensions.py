"""
Generate dimension tables: dim_date, dim_region, dim_warehouse, dim_product,
dim_supplier, dim_customer_segment, dim_transport_mode.

Design principles (see docs/data_dictionary.md for full rationale):
- Suppliers are drawn from correlated "archetypes" (excellent/reliable/average/risky)
  so that a bad supplier is consistently bad across OTIF, lead time, defects and
  cost — mirroring how real supplier risk clusters, rather than being independent
  random noise per column.
- Products have a base category-driven demand profile and seasonality flag so
  downstream demand generation tells a coherent story (e.g., apparel is seasonal,
  industrial parts are not).
- Warehouses are mapped to regions so regional stockout/logistics analysis is
  meaningful rather than arbitrary.
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))

import numpy as np
import pandas as pd
from faker import Faker

from config import config as cfg
from src.utils.logger import get_logger

log = get_logger(__name__)
rng = np.random.default_rng(cfg.RANDOM_SEED)
fake = Faker()
Faker.seed(cfg.RANDOM_SEED)


def generate_dim_date() -> pd.DataFrame:
    dates = pd.date_range(cfg.SIM_START_DATE, cfg.SIM_END_DATE, freq="D")
    df = pd.DataFrame({"date": dates})
    df["date_key"] = df["date"].dt.strftime("%Y%m%d").astype(int)
    df["year"] = df["date"].dt.year
    df["quarter"] = df["date"].dt.quarter
    df["month"] = df["date"].dt.month
    df["month_name"] = df["date"].dt.month_name()
    df["week_of_year"] = df["date"].dt.isocalendar().week.astype(int)
    df["day_of_week"] = df["date"].dt.dayofweek
    df["day_name"] = df["date"].dt.day_name()
    df["is_weekend"] = df["day_of_week"].isin([5, 6])
    # Simple festive/peak-season flag (Oct-Dec = peak retail season) — used to
    # inject realistic seasonality into demand generation later.
    df["is_peak_season"] = df["month"].isin([10, 11, 12])
    df["fiscal_year"] = np.where(df["month"] >= 4, df["year"], df["year"] - 1)  # Apr-Mar FY, common in India
    return df[["date_key", "date", "year", "quarter", "month", "month_name",
               "week_of_year", "day_of_week", "day_name", "is_weekend",
               "is_peak_season", "fiscal_year"]]


def generate_dim_region() -> pd.DataFrame:
    rows = []
    for i, name in enumerate(cfg.REGION_NAMES, start=1):
        rows.append({
            "region_id": i,
            "region_name": name,
            # demand_index drives baseline order volume per region (some regions are
            # simply bigger markets) -- used consistently in fact_orders generation
            "demand_index": round(rng.uniform(0.6, 1.6), 2),
            "logistics_cost_index": round(rng.uniform(0.85, 1.35), 2),
        })
    return pd.DataFrame(rows)


def generate_dim_warehouse(dim_region: pd.DataFrame) -> pd.DataFrame:
    rows = []
    region_ids = dim_region["region_id"].tolist()
    for i in range(1, cfg.N_WAREHOUSES + 1):
        region_id = region_ids[(i - 1) % len(region_ids)] if i > len(region_ids) else region_ids[i - 1]
        rows.append({
            "warehouse_id": i,
            "warehouse_code": f"WH-{i:03d}",
            "warehouse_name": f"{fake.city()} Distribution Center",
            "region_id": region_id,
            "capacity_units": int(rng.integers(20_000, 150_000)),
            "automation_level": rng.choice(["Manual", "Semi-Automated", "Automated"], p=[0.4, 0.4, 0.2]),
            "opened_year": int(rng.integers(2008, 2022)),
        })
    return pd.DataFrame(rows)


def generate_dim_product() -> pd.DataFrame:
    rows = []
    for i in range(1, cfg.N_PRODUCTS + 1):
        category = rng.choice(cfg.PRODUCT_CATEGORIES)
        seasonal = category in ["Apparel", "Packaged Foods", "Personal Care"]
        base_demand = float(rng.gamma(shape=2.0, scale=40))  # right-skewed: many low-volume, few high-volume SKUs
        unit_cost = float(np.round(rng.lognormal(mean=3.0, sigma=1.0), 2))
        rows.append({
            "product_id": i,
            "sku": f"SKU-{i:05d}",
            "product_name": f"{category.split(' ')[0]} Item {i}",
            "category": category,
            "unit_cost": max(unit_cost, 1.5),
            "unit_price": round(max(unit_cost, 1.5) * float(rng.uniform(1.3, 2.2)), 2),
            "base_daily_demand": round(max(base_demand, 1.0), 2),
            "is_seasonal": seasonal,
            "shelf_life_days": int(rng.choice([30, 90, 180, 365, 3650], p=[0.1, 0.15, 0.2, 0.25, 0.3])),
            "abc_class_hint": None,  # computed later from actual revenue (ABC analysis), not hardcoded
        })
    return pd.DataFrame(rows)


def generate_dim_supplier() -> pd.DataFrame:
    archetype_names = list(cfg.SUPPLIER_ARCHETYPES.keys())
    shares = [cfg.SUPPLIER_ARCHETYPES[a]["share"] for a in archetype_names]
    rows = []
    for i in range(1, cfg.N_SUPPLIERS + 1):
        archetype = rng.choice(archetype_names, p=shares)
        params = cfg.SUPPLIER_ARCHETYPES[archetype]
        base_otif = float(rng.uniform(*params["otif"]))
        lead_time_mult = float(rng.uniform(*params["lead_time_mult"]))
        defect_rate = float(rng.uniform(*params["defect_rate"]))
        cost_volatility = float(rng.uniform(*params["cost_volatility"]))
        base_lead_time = float(np.round(rng.uniform(3, 12) * lead_time_mult, 1))
        rows.append({
            "supplier_id": i,
            "supplier_code": f"SUP-{i:04d}",
            "supplier_name": fake.company(),
            "country": fake.country(),
            "archetype": archetype,   # kept for transparency/debugging; not used directly as a model feature (would leak the label)
            "base_otif_rate": round(base_otif, 3),
            "base_lead_time_days": base_lead_time,
            "lead_time_volatility": round(base_lead_time * float(rng.uniform(0.08, 0.35)), 2),
            "defect_rate": round(defect_rate, 4),
            "cost_volatility": round(cost_volatility, 3),
            "onboarded_year": int(rng.integers(2010, 2024)),
            "is_single_source": bool(rng.random() < 0.12),  # concentration-risk flag
        })
    return pd.DataFrame(rows)


def generate_dim_customer_segment() -> pd.DataFrame:
    rows = []
    for i, seg in enumerate(cfg.CUSTOMER_SEGMENTS, start=1):
        rows.append({
            "customer_segment_id": i,
            "segment_name": seg,
            "avg_order_value_index": round(rng.uniform(0.7, 1.8), 2),
            "price_sensitivity": round(rng.uniform(0.3, 1.0), 2),
        })
    return pd.DataFrame(rows)


def generate_dim_transport_mode() -> pd.DataFrame:
    speed_days = {"Air": (1, 3), "Road": (2, 6), "Rail": (4, 9), "Sea": (10, 30)}
    cost_index = {"Air": 4.2, "Road": 1.4, "Rail": 1.0, "Sea": 0.55}
    rows = []
    for i, mode in enumerate(cfg.TRANSPORT_MODES, start=1):
        lo, hi = speed_days[mode]
        rows.append({
            "transport_mode_id": i,
            "mode_name": mode,
            "typical_transit_days_min": lo,
            "typical_transit_days_max": hi,
            "relative_cost_index": cost_index[mode],
        })
    return pd.DataFrame(rows)


def generate_supplier_product_links(dim_supplier, dim_product, dim_warehouse) -> pd.DataFrame:
    """
    Bridge table representing which suppliers supply which products into which
    warehouses, at what negotiated cost. This is what makes N_SUPPLIER_PRODUCT_LINKS
    a meaningful ~5,000-row relationship table rather than an arbitrary number:
    each product typically has 1-3 approved suppliers, and each link is
    warehouse-specific (a supplier may serve some regions but not others).
    """
    rows = []
    link_id = 1
    supplier_ids = dim_supplier["supplier_id"].tolist()
    warehouse_ids = dim_warehouse["warehouse_id"].tolist()
    for _, prod in dim_product.iterrows():
        n_suppliers_for_product = int(rng.choice([1, 2, 3], p=[0.35, 0.45, 0.20]))
        chosen_suppliers = rng.choice(supplier_ids, size=n_suppliers_for_product, replace=False)
        n_warehouses_for_product = int(rng.integers(3, min(12, len(warehouse_ids))))
        chosen_warehouses = rng.choice(warehouse_ids, size=n_warehouses_for_product, replace=False)
        for sup_id in chosen_suppliers:
            sup_cost_var = dim_supplier.loc[dim_supplier.supplier_id == sup_id, "cost_volatility"].values[0]
            for wh_id in chosen_warehouses:
                negotiated_cost = round(float(prod["unit_cost"]) * float(rng.uniform(0.85, 1.05)), 2)
                rows.append({
                    "link_id": link_id,
                    "supplier_id": int(sup_id),
                    "product_id": int(prod["product_id"]),
                    "warehouse_id": int(wh_id),
                    "negotiated_unit_cost": negotiated_cost,
                    "is_primary_supplier": bool(sup_id == chosen_suppliers[0]),
                    "moq_units": int(rng.choice([50, 100, 250, 500, 1000])),
                })
                link_id += 1
            if link_id > cfg.N_SUPPLIER_PRODUCT_LINKS:
                break
        if link_id > cfg.N_SUPPLIER_PRODUCT_LINKS:
            break
    return pd.DataFrame(rows)


def main():
    log.info("Generating dimension tables...")
    dim_region = generate_dim_region()
    dim_warehouse = generate_dim_warehouse(dim_region)
    dim_product = generate_dim_product()
    dim_supplier = generate_dim_supplier()
    dim_customer_segment = generate_dim_customer_segment()
    dim_transport_mode = generate_dim_transport_mode()
    dim_date = generate_dim_date()
    supplier_product_link = generate_supplier_product_links(dim_supplier, dim_product, dim_warehouse)

    out = cfg.SYNTHETIC_DIR
    dim_date.to_csv(out / "dim_date.csv", index=False)
    dim_region.to_csv(out / "dim_region.csv", index=False)
    dim_warehouse.to_csv(out / "dim_warehouse.csv", index=False)
    dim_product.to_csv(out / "dim_product.csv", index=False)
    dim_supplier.to_csv(out / "dim_supplier.csv", index=False)
    dim_customer_segment.to_csv(out / "dim_customer_segment.csv", index=False)
    dim_transport_mode.to_csv(out / "dim_transport_mode.csv", index=False)
    supplier_product_link.to_csv(out / "bridge_supplier_product.csv", index=False)

    log.info(f"dim_date: {len(dim_date):,} rows")
    log.info(f"dim_region: {len(dim_region):,} rows")
    log.info(f"dim_warehouse: {len(dim_warehouse):,} rows")
    log.info(f"dim_product: {len(dim_product):,} rows")
    log.info(f"dim_supplier: {len(dim_supplier):,} rows")
    log.info(f"dim_customer_segment: {len(dim_customer_segment):,} rows")
    log.info(f"dim_transport_mode: {len(dim_transport_mode):,} rows")
    log.info(f"bridge_supplier_product: {len(supplier_product_link):,} rows")
    log.info("Dimension generation complete.")


if __name__ == "__main__":
    main()
