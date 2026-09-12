"""
SupplyIQ — Central Configuration
=================================
Single source of truth for paths, random seeds, and business constants used
across data generation, ETL, analytics, and modeling. Keeping this in one
module (instead of scattering magic numbers through the codebase) means the
whole simulated business is internally consistent — e.g., the same warehouse
list and lead-time assumptions are used everywhere from data generation to
the Streamlit app.
"""
from __future__ import annotations

import os
from pathlib import Path
from dotenv import load_dotenv

load_dotenv()

# ---------------------------------------------------------------------------
# Paths (all relative to project root — no machine-specific absolute paths)
# ---------------------------------------------------------------------------
ROOT_DIR = Path(__file__).resolve().parent.parent
DATA_DIR = ROOT_DIR / "data"
RAW_DIR = DATA_DIR / "raw"
PROCESSED_DIR = DATA_DIR / "processed"
SYNTHETIC_DIR = DATA_DIR / "synthetic"
DB_DIR = ROOT_DIR / "database"
DB_PATH = ROOT_DIR / os.getenv("SQLITE_DB_PATH", "database/supplyiq.db")
DASHBOARD_EXPORT_DIR = ROOT_DIR / "dashboard" / "powerbi_exports"
MODELS_DIR = ROOT_DIR / "data" / "processed" / "models"
LOGS_DIR = ROOT_DIR / "logs"

for d in [RAW_DIR, PROCESSED_DIR, SYNTHETIC_DIR, DASHBOARD_EXPORT_DIR, MODELS_DIR, LOGS_DIR]:
    d.mkdir(parents=True, exist_ok=True)

# ---------------------------------------------------------------------------
# Reproducibility
# ---------------------------------------------------------------------------
RANDOM_SEED = int(os.getenv("RANDOM_SEED", 42))

# ---------------------------------------------------------------------------
# Simulation time horizon
# ---------------------------------------------------------------------------
SIM_START_DATE = "2023-01-01"
SIM_END_DATE = "2025-12-31"   # 3 full years -> real seasonality + YoY comparisons

# ---------------------------------------------------------------------------
# Scale targets (documented + justified in docs/data_dictionary.md)
# ---------------------------------------------------------------------------
N_REGIONS = 10
N_WAREHOUSES = 22
N_PRODUCTS = 120
N_SUPPLIERS = 60          # 60 real supplier entities; N_SUPPLIER_PRODUCT_LINKS below
N_SUPPLIER_PRODUCT_LINKS = 5000   # supplier<->product<->warehouse relationship rows (fact-like)
N_CUSTOMER_SEGMENTS = 5
TARGET_ORDERS = 120_000
TARGET_SHIPMENTS = 24_000        # shipments are consolidated (multiple order-lines per shipment)
TARGET_INVENTORY_SNAPSHOTS = 12_000  # weekly snapshots per product-warehouse over 3 years, sampled

# ---------------------------------------------------------------------------
# Business logic constants
# ---------------------------------------------------------------------------
PRODUCT_CATEGORIES = [
    "Electronics", "Apparel", "Home & Kitchen", "Industrial Parts",
    "Packaged Foods", "Personal Care", "Office Supplies", "Automotive Parts",
]

TRANSPORT_MODES = ["Road", "Rail", "Air", "Sea"]

REGION_NAMES = [
    "North", "South", "East", "West", "Central",
    "North-East", "North-West", "South-East", "South-West", "Coastal",
]

CUSTOMER_SEGMENTS = ["Enterprise", "Mid-Market", "Small Business", "E-Commerce", "Government"]

# Supplier reliability archetypes: drives correlated behaviour (a "bad" supplier
# is bad across lead time, defects AND cost -- not independently random columns)
SUPPLIER_ARCHETYPES = {
    "excellent": {"share": 0.15, "otif": (0.95, 0.99), "lead_time_mult": (0.85, 1.0), "defect_rate": (0.001, 0.01), "cost_volatility": (0.02, 0.06)},
    "reliable":  {"share": 0.40, "otif": (0.88, 0.95), "lead_time_mult": (0.95, 1.1), "defect_rate": (0.01, 0.03), "cost_volatility": (0.05, 0.10)},
    "average":   {"share": 0.30, "otif": (0.75, 0.88), "lead_time_mult": (1.0, 1.3),  "defect_rate": (0.02, 0.05), "cost_volatility": (0.08, 0.15)},
    "risky":     {"share": 0.15, "otif": (0.55, 0.75), "lead_time_mult": (1.2, 1.8),  "defect_rate": (0.04, 0.10), "cost_volatility": (0.12, 0.25)},
}

# Risk thresholds used consistently by risk_engine, dashboard, and GenAI layer
STOCKOUT_RISK_BANDS = [(0.0, 0.25, "Low"), (0.25, 0.5, "Medium"), (0.5, 0.8, "High"), (0.8, 1.01, "Critical")]
SUPPLIER_RISK_BANDS = [(0, 30, "Low"), (30, 55, "Moderate"), (55, 80, "High"), (80, 101, "Critical")]

# Financial assumptions (documented — used only for *simulated* impact estimates)
HOLDING_COST_RATE_ANNUAL = 0.22          # % of inventory value held per year
STOCKOUT_LOST_MARGIN_RATE = 0.35         # assumed margin lost per stocked-out unit-demand
EXPEDITE_COST_PREMIUM = 2.4              # expedited shipping costs ~2.4x standard
AVG_GROSS_MARGIN = 0.28

# LLM configuration (see src/llm) — works with or without an API key
LLM_PROVIDER = os.getenv("LLM_PROVIDER", "none")   # "anthropic" | "openai" | "none"
LLM_MODEL = os.getenv("LLM_MODEL", "claude-sonnet-4-5")
LLM_API_KEY = os.getenv("LLM_API_KEY", "")
