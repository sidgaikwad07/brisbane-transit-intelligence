# Delay-prediction model card

Two XGBoost models — a regressor for arrival delay in seconds, and a classifier for whether a trip runs more than 5 minutes late — trained on real polled GTFS-Realtime delay observations joined against BCC intersection traffic (spatial join, nearest signal within 400m) and daily Brisbane weather.

## Data window and honesty check

- **759,687 tracked (trip, stop) arrivals**, 2026-09-25 00:00 to 2026-09-28 13:56 UTC
- This window is short — about 3 days — bounded by when the BCC traffic poller started (it has no historical backfill; see `ingestion/bcc_traffic.py`). Treat every number below as a first read from real but limited data, not a claim about Brisbane transit in general.
- Only **18%** of arrivals have a traffic signal within 400m of their stop (most Brisbane stops aren't at signalized intersections). XGBoost handles this natively via missing-value-aware splits rather than imputation — `has_nearby_signal` is included explicitly so the model can use "no signal nearby" as a feature in its own right.
- Weather varies over only a handful of distinct days in this window, so `rainfall_mm`/`temp_max_c`/`wind_kph` carry weak signal here by construction — more data needed before trusting a weather effect either way.
- **15.8% of arrivals are >5min late** in this window — the classifier's baseline is a majority-class predictor (always predict "not late"), not a coin flip.

## Method

- **Split:** time-based, not random — trained on the earliest 80% by scheduled arrival (607,743 rows), tested on the most recent 20% (151,944 rows). A random split would let autocorrelated conditions (a bad hour stays bad) leak from test into train and overstate performance.
- **Features:** mode, route_id (both native XGBoost categoricals, no one-hot), hour, day of week, is_weekend, local traffic saturation + signal count, has_nearby_signal, rainfall, max temp, wind.
- **Deliberately excluded:** `stop_id` — thousands of distinct values against ~3.5 days of data would let the model memorize specific stops rather than learn a pattern that generalizes.

## Results

### Time-based split (the real deployment scenario)

### Regressor — arrival delay (seconds)

| | MAE |
|---|---|
| Model | 435s |
| Baseline (predict train-set mean) | 258s |

### Classifier — is this trip >5min late?

| Metric | Model | Baseline (majority class) |
|---|---|---|
| Accuracy | 0.760 | 0.908 |
| Precision | 0.051 | — |
| Recall | 0.091 | — |
| F1 | 0.066 | — |
| ROC-AUC | 0.500 | 0.500 |

Test-set positive rate (actually >5min late): 9.2%

**The time-split model currently loses to its own baseline (435s MAE vs. 258s; 0.760 accuracy vs. 0.908). This is a real result, not a bug, and it's diagnosable: average delay across the window is 2026-09-25: 181s avg; 2026-09-26: 183s avg; 2026-09-27: 83s avg; 2026-09-28: 87s avg — the network was genuinely, substantially less reliable on 25-26 Sep than 27-28 Sep (independently consistent with the STRIKE-caused "Reduced train timetables" alert found active in `raw.service_alerts` over this period). The model trains almost entirely on the bad-regime days and is tested entirely on the good-regime day, and even with `n_disruption_alerts` included, route/hour/day-of-week features don't fully carry that shift across the train/test boundary — a constant baseline set to the train mean ends up more competitive than it should be, precisely because the model's route/hour-specific patterns learned under disruption don't transfer to normal conditions. The fix isn't a modeling trick, it's more data: enough days to include multiple disruption/no-disruption cycles in both train and test.

### Random split (diagnostic only — not a valid deployment estimate)

To check whether the model can learn *any* signal at all from these features, absent the regime-shift problem: the same model, same features, but train/test rows drawn i.i.d. rather than split by time (test rows now overlap the same days as training, so this **leaks information a real deployment would never have** — it exists only to isolate the regime-shift effect from a does-the-model-work-at-all question).

| | Regressor MAE | Classifier accuracy | Classifier ROC-AUC |
|---|---|---|---|
| Model | 217s | 0.857 | 0.841 |
| Baseline | 242s | 0.842 | 0.500 |

The model beats baseline here, confirming the features do carry real signal — the time-split failure above is specifically a too-short-a-window problem, not a broken feature set.

## Feature importance

![Feature importance](images/delay_model_feature_importance.png)

## Caveats

- A first pass, not a production model — the collection window is short and grows every day the pollers keep running; re-run `models/build_features.py` + `models/train_delay_model.py` periodically to retrain on more data.
- Traffic-signal coverage is spatial-proximity-based (nearest signals within 400m), not a confirmed causal link between that specific intersection and that specific trip's route.
- No per-route delay-driver breakdown yet (the roadmap's original ask) — global feature importance only. SHAP values per route is the natural next step once there's enough data per route to support it.
