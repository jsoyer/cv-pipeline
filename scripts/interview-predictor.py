#!/usr/bin/env python3
"""Predict interview probability using logistic regression (stdlib only).

Usage:
    scripts/interview-predictor.py                         # Train + show summary
    scripts/interview-predictor.py --predict applications/NAME
    scripts/interview-predictor.py --json
    scripts/interview-predictor.py --top N
"""

from __future__ import annotations

import argparse
import json
import math
import sys
from datetime import date, datetime
from pathlib import Path
from typing import Any

from lib.common import REPO_ROOT, require_yaml

yaml = require_yaml()

POSITIVE_OUTCOMES = {"interview", "offer", "accepted"}
NEGATIVE_OUTCOMES = {"rejected", "ghosted"}
SKIP_OUTCOMES = {"applied", "pending", None, ""}

MIN_SAMPLES = 5
FALLBACK_THRESHOLD = 60.0
ITERATIONS = 200
LEARNING_RATE = 0.1


# ---------------------------------------------------------------------------
# Data loading
# ---------------------------------------------------------------------------


def _ats_from_history(meta: dict[str, Any]) -> float:
    """Extract latest ATS score from ats_history list, or 0."""
    history = meta.get("ats_history") or []
    if history:
        entry = history[-1]
        if isinstance(entry, dict):
            return float(entry.get("score", 0))
    return 0.0


def _days_applied(meta: dict[str, Any]) -> int:
    """Return days since created date, or 0 if unparseable."""
    created = meta.get("created")
    if not created:
        return 0
    try:
        if isinstance(created, (date, datetime)):
            d = created if isinstance(created, date) else created.date()
        else:
            d = datetime.strptime(str(created), "%Y-%m-%d").date()
        return (date.today() - d).days
    except (ValueError, TypeError):
        return 0


def load_dataset() -> list[dict[str, Any]]:
    """Load all applications from applications/*/meta.yml.

    Returns a list of dicts with keys: name, ats_score, days_applied,
    provider, outcome, label (1/0/-1 for unknown).
    """
    apps_dir = REPO_ROOT / "applications"
    if not apps_dir.exists():
        return []

    records: list[dict[str, Any]] = []
    for d in sorted(apps_dir.iterdir()):
        if not d.is_dir():
            continue
        meta_path = d / "meta.yml"
        if not meta_path.exists():
            continue
        try:
            with open(meta_path, encoding="utf-8") as fh:
                meta = yaml.safe_load(fh) or {}
        except Exception:
            continue

        outcome = meta.get("outcome") or ""
        if outcome in POSITIVE_OUTCOMES:
            label = 1
        elif outcome in NEGATIVE_OUTCOMES:
            label = 0
        else:
            label = -1  # unknown — used for prediction only

        records.append(
            {
                "name": d.name,
                "ats_score": _ats_from_history(meta),
                "days_applied": _days_applied(meta),
                "provider": meta.get("tailor_provider", "unknown"),
                "outcome": outcome or "applied",
                "label": label,
                "meta": meta,
            }
        )
    return records


# ---------------------------------------------------------------------------
# Logistic regression (pure Python)
# ---------------------------------------------------------------------------


def sigmoid(x: float) -> float:
    """Logistic sigmoid function, numerically stable."""
    if x >= 0:
        return 1.0 / (1.0 + math.exp(-x))
    e = math.exp(x)
    return e / (1.0 + e)


def _normalize_ats(ats_score: float) -> float:
    """Normalize ATS score from [0..100] to [0..1]."""
    return ats_score / 100.0


def train_logistic(
    samples: list[dict[str, Any]],
) -> tuple[float, float] | None:
    """Train logistic regression with gradient descent.

    Features: [ats_score_normalized, intercept=1]
    Returns (coef_ats, intercept) or None if too few samples.
    """
    labeled = [s for s in samples if s["label"] in (0, 1)]
    if len(labeled) < MIN_SAMPLES:
        return None

    # Initialize weights
    w_ats = 0.0
    w_bias = 0.0

    n = len(labeled)
    for _ in range(ITERATIONS):
        grad_ats = 0.0
        grad_bias = 0.0
        for s in labeled:
            x = _normalize_ats(s["ats_score"])
            y = float(s["label"])
            pred = sigmoid(w_ats * x + w_bias)
            err = pred - y
            grad_ats += err * x
            grad_bias += err
        w_ats -= LEARNING_RATE * grad_ats / n
        w_bias -= LEARNING_RATE * grad_bias / n

    return (w_ats, w_bias)


def predict_proba(ats_score: float, weights: tuple[float, float] | None) -> float:
    """Return interview probability in [0..1].

    Falls back to simple threshold if weights is None (too few samples).
    """
    if weights is None:
        return 0.60 if ats_score >= FALLBACK_THRESHOLD else 0.35
    w_ats, w_bias = weights
    x = _normalize_ats(ats_score)
    return sigmoid(w_ats * x + w_bias)


def _training_accuracy(samples: list[dict[str, Any]], weights: tuple[float, float] | None) -> float:
    """Compute accuracy on labeled samples."""
    labeled = [s for s in samples if s["label"] in (0, 1)]
    if not labeled:
        return 0.0
    correct = 0
    for s in labeled:
        prob = predict_proba(s["ats_score"], weights)
        predicted = 1 if prob >= 0.5 else 0
        if predicted == s["label"]:
            correct += 1
    return correct / len(labeled)


# ---------------------------------------------------------------------------
# Reporting
# ---------------------------------------------------------------------------


def print_report(
    samples: list[dict[str, Any]],
    weights: tuple[float, float] | None,
    top_n: int | None = None,
    predict_name: str | None = None,
    as_json: bool = False,
) -> None:
    """Print model summary and optional prediction."""
    labeled = [s for s in samples if s["label"] in (0, 1)]
    positives = [s for s in labeled if s["label"] == 1]
    negatives = [s for s in labeled if s["label"] == 0]
    unlabeled = [s for s in samples if s["label"] == -1]

    accuracy = _training_accuracy(samples, weights)

    if as_json:
        output: dict[str, Any] = {
            "labeled": len(labeled),
            "positive": len(positives),
            "negative": len(negatives),
            "training_accuracy": round(accuracy * 100, 1),
            "model": None,
            "fallback": weights is None,
        }
        if weights is not None:
            output["model"] = {
                "ats_coefficient": round(weights[0], 4),
                "intercept": round(weights[1], 4),
            }

        if predict_name:
            target = _find_sample(samples, predict_name)
            if target:
                prob = predict_proba(target["ats_score"], weights)
                output["prediction"] = {
                    "name": target["name"],
                    "ats_score": target["ats_score"],
                    "probability": round(prob * 100, 1),
                    "recommendation": "APPLY" if prob >= 0.5 else "RECONSIDER",
                }

        if top_n is not None:
            ranked = _rank_all(samples, weights, top_n)
            output["top"] = [
                {
                    "name": r["name"],
                    "ats_score": r["ats_score"],
                    "probability": round(r["prob"] * 100, 1),
                    "outcome": r["outcome"],
                }
                for r in ranked
            ]

        print(json.dumps(output, indent=2))
        return

    # Text mode
    print("=== Interview Probability Predictor ===")
    print(f"Training on {len(labeled)} labeled applications ({len(positives)} positive, {len(negatives)} negative)")

    if weights is None:
        print(f"WARNING: fewer than {MIN_SAMPLES} labeled samples — using simple threshold (ATS >= 60 -> 60%)")
    else:
        w_ats, w_bias = weights
        sign = "+" if w_ats >= 0 else ""
        print(f"ATS coefficient: {sign}{w_ats:.2f}  (intercept: {w_bias:.2f})")
        print(f"Training accuracy: {accuracy * 100:.0f}%")

    if predict_name:
        target = _find_sample(samples, predict_name)
        if target is None:
            # Try to load directly from path
            p = Path(predict_name)
            meta_path = p / "meta.yml"
            if meta_path.exists():
                try:
                    with open(meta_path, encoding="utf-8") as fh:
                        meta = yaml.safe_load(fh) or {}
                    target = {
                        "name": p.name,
                        "ats_score": _ats_from_history(meta),
                        "outcome": meta.get("outcome", "applied"),
                    }
                except Exception:
                    pass
        if target:
            prob = predict_proba(target["ats_score"], weights)
            rec = "APPLY" if prob >= 0.5 else "RECONSIDER"
            print()
            print(f"Prediction for {target['name']}:")
            print(f"  ATS score: {target['ats_score']:.0f}%")
            print(f"  Interview probability: {prob * 100:.0f}%")
            print(
                f"  Recommendation: {rec} (above 50% threshold)"
                if rec == "APPLY"
                else f"  Recommendation: {rec} (below 50% threshold)"
            )
        else:
            print(f"\nApplication not found: {predict_name}")

    if top_n is not None:
        ranked = _rank_all(samples + unlabeled, weights, top_n)
        if ranked:
            print()
            print(f"Top {top_n} applications by predicted probability:")
            print(f"  {'Name':35s} {'ATS':>5s}  {'Prob':>5s}  {'Outcome':>10s}")
            print(f"  {'─' * 60}")
            for r in ranked:
                prob_pct = r["prob"] * 100
                print(f"  {r['name']:35s} {r['ats_score']:4.0f}%  {prob_pct:4.0f}%  {r['outcome']:>10s}")


def _find_sample(samples: list[dict[str, Any]], name: str) -> dict[str, Any] | None:
    """Find a sample by name or path."""
    target_name = Path(name).name
    for s in samples:
        if s["name"] == target_name:
            return s
    return None


def _rank_all(samples: list[dict[str, Any]], weights: tuple[float, float] | None, top_n: int) -> list[dict[str, Any]]:
    """Return top_n samples ranked by predicted probability."""
    ranked = []
    for s in samples:
        prob = predict_proba(s["ats_score"], weights)
        ranked.append({**s, "prob": prob})
    ranked.sort(key=lambda r: r["prob"], reverse=True)
    return ranked[:top_n]


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------


def main() -> int:
    parser = argparse.ArgumentParser(description="Predict interview probability via logistic regression.")
    parser.add_argument(
        "--predict",
        metavar="APPLICATION",
        help="Predict probability for a specific application path or name.",
    )
    parser.add_argument(
        "--json",
        action="store_true",
        dest="as_json",
        help="Output results as JSON.",
    )
    parser.add_argument(
        "--top",
        metavar="N",
        type=int,
        default=None,
        help="Show top N applications by predicted probability.",
    )
    args = parser.parse_args()

    samples = load_dataset()

    if not samples:
        msg = {"error": "No applications found."} if args.as_json else "No applications found in applications/."
        print(json.dumps(msg) if args.as_json else msg)
        return 1

    weights = train_logistic(samples)

    print_report(
        samples,
        weights,
        top_n=args.top,
        predict_name=args.predict,
        as_json=args.as_json,
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
