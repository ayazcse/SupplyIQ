"""
AI Supply Chain Analyst (GenAI Layer)
========================================
A grounded question-answering layer: SQL/analytics/model outputs are
retrieved FIRST as structured context, then either (a) sent to an LLM to be
turned into a business-readable explanation, or (b) if no LLM API key is
configured, assembled into the same structured answer using a deterministic
template -- so the project is fully demonstrable with zero API keys.

The LLM is NEVER allowed to answer from "general knowledge" about the
business -- it only restates/reasons over the retrieved context. If the
context doesn't contain enough evidence, both modes say so explicitly
("Insufficient evidence...") rather than inventing numbers.

Response contract (both modes): INSIGHT / EVIDENCE / BUSINESS IMPACT /
RECOMMENDATION / CONFIDENCE & LIMITATIONS.
"""
from __future__ import annotations

import json
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))

import pandas as pd

from config import config as cfg
from src.ingestion.load_raw import get_connection
from src.utils.logger import get_logger

log = get_logger(__name__)


# -----------------------------------------------------------------------------
# STEP 1: Context retrieval -- pulls real numbers for a given question "intent"
# -----------------------------------------------------------------------------
def retrieve_context(question: str) -> dict:
    q = question.lower()
    context = {"question": question, "matched_intents": [], "data": {}}

    def load_json(name):
        path = cfg.PROCESSED_DIR / name
        return json.loads(path.read_text()) if path.exists() else []

    if any(k in q for k in ["supplier", "vendor"]):
        context["matched_intents"].append("supplier_risk")
        sup = load_json("unified_supplier_risk.json")
        context["data"]["top_risk_suppliers"] = sorted(sup, key=lambda r: -r["risk_score"])[:5]

    if any(k in q for k in ["stockout", "stock out", "out of stock", "sku", "product"]):
        context["matched_intents"].append("stockout_risk")
        sku = load_json("unified_sku_risk.json")
        context["data"]["top_risk_skus"] = sorted(sku, key=lambda r: -r["stockout_probability"])[:5]

    if any(k in q for k in ["inefficien", "excess", "inventory", "working capital"]):
        context["matched_intents"].append("inventory")
        try:
            conn = get_connection()
            df = pd.read_sql("""
                SELECT p.sku, w.warehouse_name, AVG(f.days_of_supply) avg_dos
                FROM fact_inventory_snapshot f
                JOIN dim_product p ON p.product_id=f.product_id
                JOIN dim_warehouse w ON w.warehouse_id=f.warehouse_id
                GROUP BY p.product_id, w.warehouse_id HAVING avg_dos > 15
                ORDER BY avg_dos DESC LIMIT 5
            """, conn)
            conn.close()
            context["data"]["excess_inventory_examples"] = df.to_dict(orient="records")
        except Exception as e:
            log.warning(f"Inventory context retrieval failed: {e}")

    if any(k in q for k in ["action", "recommend", "should", "do about", "what changed", "this week", "this month", "summar"]):
        context["matched_intents"].append("recommendations")
        recs = load_json("recommendations.json")
        context["data"]["top_recommendations"] = recs[:5]

    if any(k in q for k in ["impact", "cost", "money", "revenue", "financial", "rupee", "dollar"]):
        context["matched_intents"].append("business_impact")
        path = cfg.PROCESSED_DIR / "business_impact_summary.json"
        if path.exists():
            context["data"]["business_impact"] = json.loads(path.read_text())

    if not context["matched_intents"]:
        # default: give a general risk snapshot
        context["matched_intents"].append("general_snapshot")
        sup = load_json("unified_supplier_risk.json")
        sku = load_json("unified_sku_risk.json")
        context["data"]["top_risk_suppliers"] = sorted(sup, key=lambda r: -r["risk_score"])[:3]
        context["data"]["top_risk_skus"] = sorted(sku, key=lambda r: -r["stockout_probability"])[:3]

    return context


# -----------------------------------------------------------------------------
# STEP 2a: Local (no-API-key) fallback -- deterministic, template-based
# -----------------------------------------------------------------------------
def local_fallback_answer(context: dict) -> str:
    data = context["data"]
    if not any(data.values()):
        return ("### INSIGHT\nInsufficient evidence to determine an answer.\n\n### EVIDENCE\n"
                "No matching structured data was found for this question in the current analytics run.\n\n"
                "### BUSINESS IMPACT\nNot determinable from available data.\n\n### RECOMMENDATION\n"
                "Re-run the analytics pipeline (scripts/run_pipeline.py) and ask again, or rephrase the question "
                "around suppliers, SKUs/stockouts, inventory, recommendations, or business impact.\n\n"
                "### CONFIDENCE / LIMITATION\nLow -- no grounding data retrieved.")

    lines = []
    evidence_lines = []

    if "top_risk_suppliers" in data and data["top_risk_suppliers"]:
        top = data["top_risk_suppliers"][0]
        lines.append(f"The highest supplier risk is **{top['supplier_name']}** at a score of "
                      f"{top['risk_score']}/100 ({top['risk_band']}).")
        ev = "; ".join(top.get("evidence", [])) or "No further evidence available."
        evidence_lines.append(f"- {top['supplier_name']}: {ev}")
        for s in data["top_risk_suppliers"][1:3]:
            evidence_lines.append(f"- {s['supplier_name']}: risk score {s['risk_score']} ({s['risk_band']})")

    if "top_risk_skus" in data and data["top_risk_skus"]:
        top = data["top_risk_skus"][0]
        lines.append(f"The SKU most likely to stock out is **{top['sku']}** at {top['warehouse']} "
                      f"({top['stockout_probability']:.0%} probability, {top['risk_band']} risk).")
        evidence_lines.append(f"- {top['sku']} @ {top['warehouse']}: " + "; ".join(top.get("evidence", [])))

    if "excess_inventory_examples" in data and data["excess_inventory_examples"]:
        top = data["excess_inventory_examples"][0]
        lines.append(f"The largest inventory inefficiency found is **{top['sku']}** at {top['warehouse_name']}, "
                      f"carrying {top['avg_dos']:.0f} days of supply.")
        evidence_lines.append(f"- {top['sku']} @ {top['warehouse_name']}: {top['avg_dos']:.0f} days of supply "
                               f"(above the network's healthy benchmark).")

    if "top_recommendations" in data and data["top_recommendations"]:
        r = data["top_recommendations"][0]
        lines.append(f"Top recommended action: **{r['recommended_action']}** (urgency: {r['urgency']}).")
        evidence_lines.append(f"- {r['issue']}")

    impact_lines = []
    if "business_impact" in data and data["business_impact"]:
        bi = data["business_impact"]
        impact_lines.append(f"Estimated total annual risk exposure: Rs.{bi['total_estimated_annual_risk_exposure']:,.0f} "
                             f"(simulated). Estimated recoverable opportunity: Rs.{bi['estimated_recoverable_opportunity']:,.0f}.")
    elif "top_risk_skus" in data and data["top_risk_skus"]:
        impact_lines.append("Business impact figures are available via the 'business impact' or 'financial' question type.")
    else:
        impact_lines.append("Not directly quantified for this question -- ask about business impact for a financial estimate.")

    recs = []
    if "top_recommendations" in data and data["top_recommendations"]:
        for r in data["top_recommendations"][:2]:
            recs.append(f"- {r['recommended_action']} ({r['urgency']})")
    if not recs:
        recs = ["- Review the top-ranked risk items above and consult the full recommendations.json for the prioritized action list."]

    insight = " ".join(lines) if lines else "No single dominant risk pattern was found for this specific question."
    evidence = "\n".join(evidence_lines) if evidence_lines else "- Based on the available data, no strongly supporting evidence was found."

    return (f"### INSIGHT\n{insight}\n\n"
            f"### EVIDENCE\n{evidence}\n\n"
            f"### BUSINESS IMPACT\n{' '.join(impact_lines)}\n\n"
            f"### RECOMMENDATION\n" + "\n".join(recs) + "\n\n"
            f"### CONFIDENCE / LIMITATION\nModerate -- based on the most recent analytics run only "
            f"(local template mode, no LLM). Based on the available data; insufficient evidence is reported "
            f"explicitly rather than inferred.")


# -----------------------------------------------------------------------------
# STEP 2b: LLM-backed answer (used only if LLM_PROVIDER + LLM_API_KEY configured)
# -----------------------------------------------------------------------------
SYSTEM_PROMPT = """You are the SupplyIQ AI Supply Chain Analyst. You must answer ONLY using the
structured JSON context provided below -- never invent numbers, supplier names, or SKUs that
are not present in the context. If the context does not contain enough information to answer,
say "Insufficient evidence to determine the root cause" (or similar) rather than guessing.

Always structure your answer with these exact headers:
### INSIGHT
### EVIDENCE
### BUSINESS IMPACT
### RECOMMENDATION
### CONFIDENCE / LIMITATION

Keep it concise and business-readable (a supply chain ops manager, not a data scientist, is the
audience). Use "Based on the available data..." framing."""


def llm_answer(context: dict) -> str:
    import requests
    payload_context = json.dumps(context, indent=2, default=str)
    try:
        if cfg.LLM_PROVIDER == "anthropic":
            resp = requests.post(
                "https://api.anthropic.com/v1/messages",
                headers={"x-api-key": cfg.LLM_API_KEY, "anthropic-version": "2023-06-01",
                         "content-type": "application/json"},
                json={"model": cfg.LLM_MODEL, "max_tokens": 700,
                      "system": SYSTEM_PROMPT,
                      "messages": [{"role": "user", "content": f"Context:\n{payload_context}\n\nQuestion: {context['question']}"}]},
                timeout=30,
            )
            resp.raise_for_status()
            return resp.json()["content"][0]["text"]
        elif cfg.LLM_PROVIDER == "openai":
            resp = requests.post(
                "https://api.openai.com/v1/chat/completions",
                headers={"Authorization": f"Bearer {cfg.LLM_API_KEY}", "Content-Type": "application/json"},
                json={"model": cfg.LLM_MODEL, "max_tokens": 700,
                      "messages": [{"role": "system", "content": SYSTEM_PROMPT},
                                   {"role": "user", "content": f"Context:\n{payload_context}\n\nQuestion: {context['question']}"}]},
                timeout=30,
            )
            resp.raise_for_status()
            return resp.json()["choices"][0]["message"]["content"]
    except Exception as e:
        log.warning(f"LLM call failed ({e}); falling back to local template mode.")
        return local_fallback_answer(context)
    return local_fallback_answer(context)


# -----------------------------------------------------------------------------
# Public entry point
# -----------------------------------------------------------------------------
def ask(question: str) -> dict:
    context = retrieve_context(question)
    if cfg.LLM_PROVIDER in ("anthropic", "openai") and cfg.LLM_API_KEY:
        answer = llm_answer(context)
        mode = f"llm:{cfg.LLM_PROVIDER}"
    else:
        answer = local_fallback_answer(context)
        mode = "local_fallback"
    return {"question": question, "answer": answer, "mode": mode, "matched_intents": context["matched_intents"]}


if __name__ == "__main__":
    test_questions = [
        "Why is supplier risk increasing?",
        "Which SKUs are most likely to stock out?",
        "What are the biggest inventory inefficiencies?",
        "What action should operations take this week?",
        "What is the estimated financial impact of current risks?",
    ]
    for q in test_questions:
        result = ask(q)
        print(f"\n{'='*80}\nQ: {q}  [mode={result['mode']}]\n{'='*80}")
        print(result["answer"])
