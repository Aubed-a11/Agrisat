"""Modeles de rendement: correction de tendance, validation par annee exclue, SHAP."""
import numpy as np
import pandas as pd
from sklearn.linear_model import RidgeCV
from sklearn.ensemble import RandomForestRegressor
from sklearn.pipeline import make_pipeline
from sklearn.preprocessing import StandardScaler
from sklearn.metrics import r2_score, mean_squared_error, mean_absolute_error, roc_auc_score

try:
    from xgboost import XGBRegressor
except ImportError:  # pragma: no cover
    XGBRegressor = None

BAD_YEAR_THRESHOLD = 0.70   # rendement relatif < 70 pour cent de la tendance = perte > 30 pour cent


def detrend(df):
    """Ajoute trend_kg_ha et rel_yield par commune et culture (regression lineaire sur l'annee)."""
    df = df.copy()
    df["trend_kg_ha"] = np.nan
    for _, g in df.groupby(["commune_id", "crop"]):
        x, y = g["year"].values, g["yield_kg_ha"].values
        a, b = np.polyfit(x, y, 1) if len(g) >= 5 else (0.0, y.mean())
        df.loc[g.index, "trend_kg_ha"] = a * x + b
    df["rel_yield"] = df["yield_kg_ha"] / df["trend_kg_ha"]
    df["loss_kg_ha"] = np.maximum(0.0, df["trend_kg_ha"] - df["yield_kg_ha"])
    return df


def _models(seed=0):
    m = {
        "ridge": make_pipeline(StandardScaler(), RidgeCV(alphas=np.logspace(-2, 3, 20))),
        "random_forest": RandomForestRegressor(n_estimators=300, min_samples_leaf=5, random_state=seed, n_jobs=-1),
    }
    if XGBRegressor is not None:
        m["xgboost"] = XGBRegressor(n_estimators=300, max_depth=3, learning_rate=0.05, subsample=0.8,
                                    colsample_bytree=0.8, random_state=seed, n_jobs=2)
    return m


def feature_columns(df):
    skip = {"commune_id", "crop", "year", "yield_kg_ha", "source", "trend_kg_ha", "rel_yield", "loss_kg_ha"}
    return [c for c in df.columns if c not in skip]


def evaluate(df, seed=0):
    """Validation leave-one-year-out pour chaque modele. Retourne metriques et predictions."""
    feats = feature_columns(df)
    X = df[feats].astype(float)
    X = X.loc[:, X.notna().any()]
    feats = list(X.columns)
    X = X.fillna(X.median())
    y = df["rel_yield"].values
    years = df["year"].values
    results, preds = {}, {}
    for name, model in _models(seed).items():
        oof = np.zeros(len(df))
        for yr in np.unique(years):
            tr, te = years != yr, years == yr
            model.fit(X[tr], y[tr])
            oof[te] = model.predict(X[te])
        bad = (y < BAD_YEAR_THRESHOLD).astype(int)
        auc = roc_auc_score(bad, -oof) if 0 < bad.sum() < len(bad) else None
        results[name] = {
            "r2": round(float(r2_score(y, oof)), 3),
            "rmse": round(float(np.sqrt(mean_squared_error(y, oof))), 4),
            "mae": round(float(mean_absolute_error(y, oof)), 4),
            "auc_bad_year": round(float(auc), 3) if auc is not None else None,
        }
        preds[name] = oof
    best = max(results, key=lambda k: results[k]["r2"])
    return {"metrics": results, "best_model": best, "n_obs": int(len(df)),
            "n_years": int(len(np.unique(years))), "features": feats}, preds


def shap_importance(df, seed=0, top=15):
    feats = feature_columns(df)
    X = df[feats].astype(float)
    X = X.loc[:, X.notna().any()]
    feats = list(X.columns)
    X = X.fillna(X.median())
    y = df["rel_yield"].values
    model = _models(seed).get("xgboost") or _models(seed)["random_forest"]
    model.fit(X, y)
    try:
        import shap
        sv = shap.TreeExplainer(model).shap_values(X)
        imp = np.abs(sv).mean(axis=0)
        method = "shap"
    except Exception:  # pragma: no cover
        imp = model.feature_importances_
        method = "gain"
    order = np.argsort(imp)[::-1][:top]
    by_phase = {}
    for f, v in zip(feats, imp):
        key = f"phase {f[-1]}" if f[-2:-1] == "p" and f[-1].isdigit() else "calendrier"
        by_phase[key] = by_phase.get(key, 0.0) + float(v)
    tot = sum(by_phase.values()) or 1.0
    return {"method": method,
            "top_features": [{"feature": feats[i], "importance": round(float(imp[i]), 5)} for i in order],
            "by_phase": {k: round(v / tot, 3) for k, v in sorted(by_phase.items())}}
