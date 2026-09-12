"""Tests for src/data_generation -- checks schema, row counts, and referential
integrity of the synthetic dataset (does NOT regenerate data; assumes
`python scripts/run_pipeline.py` or the generation scripts have already run,
as they would in CI before the test stage)."""
import pandas as pd
import pytest

from config import config as cfg


@pytest.fixture(scope="module")
def dims():
    return {
        "product": pd.read_csv(cfg.SYNTHETIC_DIR / "dim_product.csv"),
        "supplier": pd.read_csv(cfg.SYNTHETIC_DIR / "dim_supplier.csv"),
        "warehouse": pd.read_csv(cfg.SYNTHETIC_DIR / "dim_warehouse.csv"),
        "region": pd.read_csv(cfg.SYNTHETIC_DIR / "dim_region.csv"),
    }


@pytest.fixture(scope="module")
def orders():
    return pd.read_csv(cfg.SYNTHETIC_DIR / "fact_orders.csv")


def test_dimension_row_counts(dims):
    assert len(dims["product"]) == cfg.N_PRODUCTS
    assert len(dims["supplier"]) == cfg.N_SUPPLIERS
    assert len(dims["warehouse"]) == cfg.N_WAREHOUSES
    assert len(dims["region"]) == cfg.N_REGIONS


def test_dimension_keys_unique(dims):
    for name, df in dims.items():
        id_col = f"{name}_id"
        assert df[id_col].is_unique, f"{id_col} is not unique in dim_{name}"


def test_orders_meets_scale_target(orders):
    assert len(orders) >= 100_000, "fact_orders should meet the '100,000+ orders' scale target"


def test_orders_has_expected_columns(orders):
    expected = {"order_id", "order_date", "product_id", "warehouse_id", "region_id",
                "customer_segment_id", "supplier_id", "transport_mode_id", "order_qty",
                "unit_price", "revenue", "order_status", "promised_delivery_date",
                "actual_delivery_date", "is_late"}
    assert expected.issubset(set(orders.columns))


def test_orders_has_injected_data_quality_issues(orders):
    """Confirms the deliberately injected messiness is actually present --
    i.e. the data-quality engine downstream has real issues to find."""
    assert orders["unit_price"].isna().sum() > 0, "expected some injected null unit_price values"
    assert orders["order_id"].duplicated().sum() > 0, "expected some injected duplicate order_id values"
    assert (pd.to_numeric(orders["unit_price"], errors="coerce") < 0).sum() > 0, "expected some injected negative prices"


def test_orders_referential_integrity(orders, dims):
    valid_products = set(dims["product"]["product_id"])
    valid_warehouses = set(dims["warehouse"]["warehouse_id"])
    assert set(orders["product_id"]).issubset(valid_products)
    assert set(orders["warehouse_id"]).issubset(valid_warehouses)


def test_supplier_archetype_distribution(dims):
    """Sanity check that the archetype mix roughly matches config shares
    (within a generous tolerance, since it's a random draw)."""
    counts = dims["supplier"]["archetype"].value_counts(normalize=True)
    for archetype, params in cfg.SUPPLIER_ARCHETYPES.items():
        if archetype in counts:
            assert abs(counts[archetype] - params["share"]) < 0.25
