"""Train and evaluate the Week 3 delay-prediction model.

Two XGBoost models sharing the same feature set from build_features.py:
  - Regressor: predicts arrival_delay_sec (evaluated by MAE)
  - Classifier: predicts is_late (delay > 5min), evaluated by accuracy/
    precision/recall/F1/ROC-AUC — the "P(delay > 5 min)" the roadmap asked for

Both use a time-based train/test split (not random) — this is real
operational data with autocorrelated conditions (a bad hour stays bad for
a while), so a random split would leak future information into training
and overstate performance. Both are compared against a naive baseline
(train-set mean / majority class) so "the model works" means "beats the
trivial baseline," not just "produces numbers."

route_id and mode are used as native XGBoost categoricals (no one-hot —
route_id alone has hundreds of distinct values). stop_id is deliberately
excluded: at thousands of distinct values with only a few weeks of data,
it would let the model memorize specific stops rather than learn a
generalizable pattern.

Usage:
    python models/train_delay_model.py
"""

from __future__ import annotations

import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT))
sys.path.insert(0, str(REPO_ROOT / "models"))

import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
import xgboost as xgb
from build_features import build_features
from sklearn.metrics import (
    accuracy_score,
    f1_score,
    mean_absolute_error,
    precision_score,
    recall_score,
    roc_auc_score,
)
from sqlalchemy import create_engine

from ingestion.config import DATABASE_URL

CHART_PATH = REPO_ROOT / "docs" / "images" / "delay_model_feature_importance.png"
REPORT_PATH = REPO_ROOT / "docs" / "delay_model_card.md"

FEATURE_COLS = [
    "mode",
    "route_id",
    "hour",
    "day_of_week",
    "is_weekend",
    "local_saturation",
    "n_signals",
    "has_nearby_signal",
    "rainfall_mm",
    "temp_max_c",
    "wind_kph",
    "n_disruption_alerts",
]
CATEGORICAL_COLS = ["mode", "route_id"]
TEST_FRACTION = 0.2

INK_PRIMARY = "#0b0b0b"
INK_SECONDARY = "#52514e"
GRIDLINE = "#e1e0d9"
BAR_COLOR = "#2a78d6"


def prepare(df: pd.DataFrame) -> pd.DataFrame:
    df = df.copy()
    for col in CATEGORICAL_COLS:
        df[col] = df[col].astype("category")
    df["is_weekend"] = df["is_weekend"].astype(int)
    df["has_nearby_signal"] = df["has_nearby_signal"].astype(int)
    return df


def time_split(df: pd.DataFrame) -> tuple[pd.DataFrame, pd.DataFrame]:
    df = df.sort_values("scheduled_arrival")
    cutoff = df["scheduled_arrival"].quantile(1 - TEST_FRACTION)
    train = df[df["scheduled_arrival"] < cutoff]
    test = df[df["scheduled_arrival"] >= cutoff]
    return train, test


def random_split(df: pd.DataFrame) -> tuple[pd.DataFrame, pd.DataFrame]:
    test = df.sample(frac=TEST_FRACTION, random_state=42)
    train = df.drop(test.index)
    return train, test


def train_regressor(train: pd.DataFrame, test: pd.DataFrame) -> tuple[xgb.XGBRegressor, dict]:
    X_train, y_train = train[FEATURE_COLS], train["arrival_delay_sec"]
    X_test, y_test = test[FEATURE_COLS], test["arrival_delay_sec"]

    model = xgb.XGBRegressor(
        n_estimators=300,
        max_depth=6,
        learning_rate=0.05,
        enable_categorical=True,
        tree_method="hist",
        random_state=42,
    )
    model.fit(X_train, y_train)
    pred = model.predict(X_test)

    baseline_pred = np.full(len(y_test), y_train.mean())
    metrics = {
        "mae_sec": mean_absolute_error(y_test, pred),
        "baseline_mae_sec": mean_absolute_error(y_test, baseline_pred),
    }
    return model, metrics


def train_classifier(train: pd.DataFrame, test: pd.DataFrame) -> tuple[xgb.XGBClassifier, dict]:
    X_train, y_train = train[FEATURE_COLS], train["is_late"].astype(int)
    X_test, y_test = test[FEATURE_COLS], test["is_late"].astype(int)

    model = xgb.XGBClassifier(
        n_estimators=300,
        max_depth=6,
        learning_rate=0.05,
        enable_categorical=True,
        tree_method="hist",
        random_state=42,
        eval_metric="logloss",
    )
    model.fit(X_train, y_train)
    pred = model.predict(X_test)
    pred_proba = model.predict_proba(X_test)[:, 1]

    majority_class = int(y_train.mode()[0])
    baseline_pred = np.full(len(y_test), majority_class)
    metrics = {
        "accuracy": accuracy_score(y_test, pred),
        "precision": precision_score(y_test, pred, zero_division=0),
        "recall": recall_score(y_test, pred, zero_division=0),
        "f1": f1_score(y_test, pred, zero_division=0),
        "roc_auc": roc_auc_score(y_test, pred_proba),
        "baseline_accuracy": accuracy_score(y_test, baseline_pred),
        "positive_rate_test": y_test.mean(),
        "positive_rate_train": y_train.mean(),
    }
    return model, metrics


def plot_feature_importance(reg_model: xgb.XGBRegressor, clf_model: xgb.XGBClassifier) -> None:
    CHART_PATH.parent.mkdir(parents=True, exist_ok=True)
    fig, axes = plt.subplots(1, 2, figsize=(11, 5), dpi=150)
    fig.patch.set_facecolor("#fcfcfb")

    for ax, model, title in [
        (axes[0], reg_model, "Regressor — predicting delay (seconds)"),
        (axes[1], clf_model, "Classifier — predicting >5min late"),
    ]:
        ax.set_facecolor("#fcfcfb")
        importances = pd.Series(model.feature_importances_, index=FEATURE_COLS).sort_values()
        ax.barh(importances.index, importances.values, color=BAR_COLOR, zorder=3)
        ax.grid(axis="x", color=GRIDLINE, linewidth=1, zorder=0)
        ax.set_axisbelow(True)
        for spine in ["top", "right", "left"]:
            ax.spines[spine].set_visible(False)
        ax.spines["bottom"].set_color("#898781")
        ax.tick_params(colors=INK_SECONDARY, labelsize=9)
        ax.set_title(title, fontsize=11, fontweight="bold", color=INK_PRIMARY, loc="left")
        ax.set_xlabel("Gain-based importance", fontsize=9, color=INK_SECONDARY)

    fig.tight_layout()
    fig.savefig(CHART_PATH, facecolor=fig.get_facecolor())
    plt.close(fig)


def write_report(
    df: pd.DataFrame,
    train: pd.DataFrame,
    test: pd.DataFrame,
    reg_metrics: dict,
    clf_metrics: dict,
    reg_metrics_rand: dict,
    clf_metrics_rand: dict,
) -> None:
    n_signal_pct = 100 * df["has_nearby_signal"].mean()
    df_by_date = df.assign(date=df["scheduled_arrival"].dt.date).groupby("date")["arrival_delay_sec"].mean()
    regime_shift_note = "; ".join(f"{d}: {v:.0f}s avg" for d, v in df_by_date.items())
    daily_counts = df.groupby(df["scheduled_arrival"].dt.date).size()
    lines = [
        "# Delay-prediction model card",
        "",
        "Two XGBoost models — a regressor for arrival delay in seconds, and a classifier for "
        "whether a trip runs more than 5 minutes late — trained on real polled GTFS-Realtime "
        "delay observations joined against BCC intersection traffic (spatial join, nearest "
        "signal within 400m) and daily Brisbane weather.",
        "",
        "## Data window and honesty check",
        "",
        f"- **{len(df):,} tracked (trip, stop) arrivals**, {df['scheduled_arrival'].min():%Y-%m-%d %H:%M} "
        f"to {df['scheduled_arrival'].max():%Y-%m-%d %H:%M} UTC",
        f"- This window is short — about {(df['scheduled_arrival'].max() - df['scheduled_arrival'].min()).days} "
        "days — bounded by when the BCC traffic poller started (it has no historical backfill; see "
        "`ingestion/bcc_traffic.py`). Treat every number below as a first read from real but limited "
        "data, not a claim about Brisbane transit in general.",
        f"- Only **{n_signal_pct:.0f}%** of arrivals have a traffic signal within 400m of their stop "
        "(most Brisbane stops aren't at signalized intersections). XGBoost handles this natively via "
        "missing-value-aware splits rather than imputation — `has_nearby_signal` is included explicitly "
        "so the model can use \"no signal nearby\" as a feature in its own right.",
        "- Weather varies over only a handful of distinct days in this window, so `rainfall_mm`/"
        "`temp_max_c`/`wind_kph` carry weak signal here by construction — more data needed before "
        "trusting a weather effect either way.",
        f"- **{100 * df['is_late'].mean():.1f}% of arrivals are >5min late** in this window — the "
        "classifier's baseline is a majority-class predictor (always predict \"not late\"), not a coin flip.",
        "",
        "## Method",
        "",
        f"- **Split:** time-based, not random — trained on the earliest {100 * (1 - TEST_FRACTION):.0f}% "
        f"by scheduled arrival ({len(train):,} rows), tested on the most recent {100 * TEST_FRACTION:.0f}% "
        f"({len(test):,} rows). A random split would let autocorrelated conditions (a bad hour stays bad) "
        "leak from test into train and overstate performance.",
        "- **Features:** mode, route_id (both native XGBoost categoricals, no one-hot), hour, day of week, "
        "is_weekend, local traffic saturation + signal count, has_nearby_signal, rainfall, max temp, wind.",
        "- **Deliberately excluded:** `stop_id` — thousands of distinct values against a few weeks of data "
        "would let the model memorize specific stops rather than learn a pattern that generalizes.",
        "",
        "## Results",
        "",
        "### Time-based split (the real deployment scenario)",
        "",
        "### Regressor — arrival delay (seconds)",
        "",
        f"| | MAE |\n|---|---|\n| Model | {reg_metrics['mae_sec']:.0f}s |\n"
        f"| Baseline (predict train-set mean) | {reg_metrics['baseline_mae_sec']:.0f}s |",
        "",
        "### Classifier — is this trip >5min late?",
        "",
        "| Metric | Model | Baseline (majority class) |\n|---|---|---|\n"
        f"| Accuracy | {clf_metrics['accuracy']:.3f} | {clf_metrics['baseline_accuracy']:.3f} |\n"
        f"| Precision | {clf_metrics['precision']:.3f} | — |\n"
        f"| Recall | {clf_metrics['recall']:.3f} | — |\n"
        f"| F1 | {clf_metrics['f1']:.3f} | — |\n"
        f"| ROC-AUC | {clf_metrics['roc_auc']:.3f} | 0.500 |",
        "",
        f"Test-set positive rate (actually >5min late): {100 * clf_metrics['positive_rate_test']:.1f}%",
        "",
        (
            "**The time-split model currently loses to its own baseline "
            if reg_metrics["mae_sec"] > reg_metrics["baseline_mae_sec"]
            else "**The time-split model beats its baseline "
        )
        + f"({reg_metrics['mae_sec']:.0f}s MAE vs. {reg_metrics['baseline_mae_sec']:.0f}s; "
        f"{clf_metrics['accuracy']:.3f} accuracy vs. {clf_metrics['baseline_accuracy']:.3f}).** "
        f"The test set covers {test['scheduled_arrival'].min():%Y-%m-%d %H:%M} to "
        f"{test['scheduled_arrival'].max():%Y-%m-%d %H:%M} UTC. Average delay swings a lot from day to day "
        f"({regime_shift_note}), and daily row counts are very uneven ({daily_counts.min():,} to "
        f"{daily_counts.max():,}) because collection had gaps. Route, hour and day-of-week features can't "
        "anticipate a day-level swing (a strike, an incident, a holiday timetable) they haven't seen, so a "
        "constant set to the training mean is hard to beat whenever the test days behave differently from "
        "the training days. The features also have no public-holiday flag, so a holiday is treated as an "
        "ordinary weekday. More days of data spanning several of these swings, and a holiday feature, are "
        "the fixes; a different model isn't.",
        "",
        "### Random split (diagnostic only — not a valid deployment estimate)",
        "",
        "To check whether the model can learn *any* signal at all from these features, absent the "
        "regime-shift problem: the same model, same features, but train/test rows drawn i.i.d. rather than "
        "split by time (test rows now overlap the same days as training, so this **leaks information a real "
        "deployment would never have** — it exists only to isolate the regime-shift effect from a "
        "does-the-model-work-at-all question).",
        "",
        f"| | Regressor MAE | Classifier accuracy | Classifier ROC-AUC |\n|---|---|---|---|\n"
        f"| Model | {reg_metrics_rand['mae_sec']:.0f}s | {clf_metrics_rand['accuracy']:.3f} | "
        f"{clf_metrics_rand['roc_auc']:.3f} |\n"
        f"| Baseline | {reg_metrics_rand['baseline_mae_sec']:.0f}s | {clf_metrics_rand['baseline_accuracy']:.3f} | 0.500 |",
        "",
        (
            "The model beats baseline here, confirming the features do carry real signal — the time-split "
            "result above is a problem of too few, too uneven days, not a broken feature set."
            if reg_metrics_rand["mae_sec"] < reg_metrics_rand["baseline_mae_sec"]
            else "The model **still** doesn't clearly beat baseline even with leakage allowed, which points "
            "at the feature set itself needing work, not just more days of data."
        ),
        "",
        "## Feature importance",
        "",
        "![Feature importance](images/delay_model_feature_importance.png)",
        "",
        "## Caveats",
        "",
        "- A first pass, not a production model — the collection window is short and grows every day the "
        "pollers keep running; re-run `models/build_features.py` + `models/train_delay_model.py` "
        "periodically to retrain on more data.",
        "- Traffic-signal coverage is spatial-proximity-based (nearest signals within 400m), not a "
        "confirmed causal link between that specific intersection and that specific trip's route.",
        "- No per-route delay-driver breakdown yet (the roadmap's original ask) — global feature "
        "importance only. SHAP values per route is the natural next step once there's enough data per "
        "route to support it.",
    ]
    REPORT_PATH.write_text("\n".join(lines) + "\n")


def main() -> None:
    engine = create_engine(DATABASE_URL)
    df = prepare(build_features(engine))

    train, test = time_split(df)
    print(f"Time split — train: {len(train):,} rows, test: {len(test):,} rows")

    reg_model, reg_metrics = train_regressor(train, test)
    print(f"Regressor MAE: {reg_metrics['mae_sec']:.0f}s (baseline: {reg_metrics['baseline_mae_sec']:.0f}s)")

    clf_model, clf_metrics = train_classifier(train, test)
    print(
        f"Classifier accuracy: {clf_metrics['accuracy']:.3f} (baseline: {clf_metrics['baseline_accuracy']:.3f}), "
        f"ROC-AUC: {clf_metrics['roc_auc']:.3f}"
    )

    train_r, test_r = random_split(df)
    _, reg_metrics_rand = train_regressor(train_r, test_r)
    _, clf_metrics_rand = train_classifier(train_r, test_r)
    print(
        f"[diagnostic random split] Regressor MAE: {reg_metrics_rand['mae_sec']:.0f}s "
        f"(baseline: {reg_metrics_rand['baseline_mae_sec']:.0f}s), "
        f"Classifier accuracy: {clf_metrics_rand['accuracy']:.3f} (baseline: {clf_metrics_rand['baseline_accuracy']:.3f})"
    )

    plot_feature_importance(reg_model, clf_model)
    print(f"Saved chart to {CHART_PATH}")

    write_report(df, train, test, reg_metrics, clf_metrics, reg_metrics_rand, clf_metrics_rand)
    print(f"Saved model card to {REPORT_PATH}")


if __name__ == "__main__":
    main()
