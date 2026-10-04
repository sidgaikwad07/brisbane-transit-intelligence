# ML models (added in Week 3)

The delay-prediction model (XGBoost) is trained on the dbt mart output, joined with BCC
intersection traffic and daily weather. `build_features.py` builds the training table and
`train_delay_model.py` trains and evaluates it, writing the results to
`docs/delay_model_card.md`.
