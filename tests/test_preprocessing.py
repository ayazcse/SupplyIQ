"""Tests for src/preprocessing/clean_orders.py -- uses a small hand-built
'dirty' DataFrame so each cleaning rule is verified in isolation."""
import pandas as pd

from src.preprocessing.clean_orders import clean_orders


def make_dirty_raw():
    """20 'normal' orders (ids 1-20) + 1 duplicate of order_id=2 (normal data)
    + 1 distinct extreme-outlier order (id=21) + missing/negative price cases
    placed on their OWN unique order_ids so dedup doesn't accidentally remove
    the very rows the other assertions are checking."""
    normal_qty = [10, 12, 8, 15, 9, 11, 14, 10, 13, 9, 12, 11, 10, 14, 9, 13, 12, 10, 11, 9]
    rows = []
    for i in range(1, 21):
        rows.append(dict(order_id=str(i), order_qty=str(normal_qty[i - 1]), unit_price="100",
                          revenue="1000", order_status="Fulfilled", transport_mode_id="1"))
    rows.append(dict(order_id="2", order_qty="12", unit_price="100", revenue="1000",
                      order_status="STOCKOUT", transport_mode_id="1"))               # duplicate of id=2
    rows.append(dict(order_id="21", order_qty="1000000", unit_price="20", revenue="20000000",
                      order_status="Fulfilled", transport_mode_id="1"))               # extreme outlier, unique id
    rows.append(dict(order_id="22", order_qty="10", unit_price="", revenue="",
                      order_status="partial ", transport_mode_id="1"))               # missing price, messy status
    rows.append(dict(order_id="23", order_qty="10", unit_price="-50", revenue="-500",
                      order_status="Fulfilled", transport_mode_id=""))               # negative price, missing mode

    df = pd.DataFrame(rows)
    n = len(df)
    df["order_date"] = "2024-01-01"
    df["product_id"] = "1"
    df["warehouse_id"] = "1"
    df["region_id"] = "1"
    df["customer_segment_id"] = "1"
    df["supplier_id"] = "1"
    df["promised_delivery_date"] = "2024-01-05"
    df["actual_delivery_date"] = "2024-01-06"
    df["is_late"] = ["True", "False"] * (n // 2) + (["True"] if n % 2 else [])
    return df


def test_deduplication_removes_exact_duplicate_order_ids():
    raw = make_dirty_raw()
    dim_product = pd.DataFrame({"product_id": [1, 2], "unit_price": [99.0, 25.0]})
    cleaned = clean_orders(raw, dim_product, {1: 1})
    assert cleaned["order_id"].is_unique


def test_negative_prices_are_corrected():
    raw = make_dirty_raw()
    dim_product = pd.DataFrame({"product_id": [1, 2], "unit_price": [99.0, 25.0]})
    cleaned = clean_orders(raw, dim_product, {1: 1})
    assert (cleaned["unit_price"] >= 0).all()


def test_missing_prices_imputed_from_catalog():
    raw = make_dirty_raw()
    dim_product = pd.DataFrame({"product_id": [1, 2], "unit_price": [99.0, 25.0]})
    cleaned = clean_orders(raw, dim_product, {1: 1})
    assert cleaned["unit_price"].isna().sum() == 0


def test_order_status_normalized_to_canonical_labels():
    raw = make_dirty_raw()
    dim_product = pd.DataFrame({"product_id": [1, 2], "unit_price": [99.0, 25.0]})
    cleaned = clean_orders(raw, dim_product, {1: 1})
    assert set(cleaned["order_status"].unique()).issubset({"Fulfilled", "Stockout", "Partial"})


def test_outlier_quantity_is_flagged_not_dropped():
    raw = make_dirty_raw()
    dim_product = pd.DataFrame({"product_id": [1, 2], "unit_price": [99.0, 25.0]})
    cleaned = clean_orders(raw, dim_product, {1: 1})
    assert "is_outlier_qty" in cleaned.columns
    assert cleaned["is_outlier_qty"].sum() >= 1
    # row with qty=1,000,000 should still be present (flagged, not dropped)
    assert (cleaned["order_qty"] == 1_000_000).any()
