"""
Cold Start Model Training
Trains two production models:
  1. Cold Start Model  — uses ONLY static/demographic features (0-3 month accounts)
  2. Full Model        — uses all features including behavioral (established accounts)
"""
import logging
import os
import sys
import warnings
from datetime import datetime
import joblib
import matplotlib.pyplot as plt
import mlflow
import mlflow.sklearn
import numpy as np
import pandas as pd
import yaml
from sklearn.compose import ColumnTransformer
from sklearn.ensemble import GradientBoostingClassifier, RandomForestClassifier
from sklearn.impute import SimpleImputer
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import (accuracy_score, average_precision_score, classification_report,f1_score, precision_recall_curve, precision_score, recall_score,roc_auc_score, roc_curve)
from sklearn.model_selection import StratifiedKFold, cross_val_score, train_test_split
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import OneHotEncoder, StandardScaler
warnings.filterwarnings("ignore")

# ── Resolve project root regardless of where script is invoked from ────
PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, PROJECT_ROOT)
from src.data.feature_pipeline import run_snap_pipeline
from src.core.versioning import save_versioned_model 
# ── Logging 
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(message)s",
    handlers=[
        logging.FileHandler(os.path.join(PROJECT_ROOT, "cold_start_training.log")),
        logging.StreamHandler(),
    ],
)
logger = logging.getLogger(__name__)
mlflow.set_experiment("Cold_Start_Credit_Model")

# HELPER FUNCTIONS
def load_params(root: str = PROJECT_ROOT) -> dict:
    params_path = os.path.join(root, "params.yaml")
    try:
        with open(params_path, "r") as f:
            return yaml.safe_load(f)
    except FileNotFoundError:
        logger.warning(f"params.yaml not found at {params_path}")
        return {
            "models": {
                "logistic_regression": {"max_iter": 1000, "class_weight": "balanced", "solver": "lbfgs"},
                "random_forest":       {"n_estimators": 100, "class_weight": "balanced", "n_jobs": -1},
                "gradient_boosting":   {"n_estimators": 100, "learning_rate": 0.1, "max_depth": 5},
            },
            "data": {"random_state": 42},
        }


def get_feature_types(df: pd.DataFrame) -> tuple:
    cat = df.select_dtypes(include=["object", "category"]).columns.tolist()
    num = df.select_dtypes(include=["number"]).columns.tolist()
    return cat, num


def build_preprocessor(numerical_features: list, categorical_features: list) -> ColumnTransformer:
    num_pipe = Pipeline([
        ("imputer", SimpleImputer(strategy="median")),
        ("scaler",  StandardScaler()),
    ])
    cat_pipe = Pipeline([
        ("imputer", SimpleImputer(strategy="constant", fill_value="Unknown")),
        ("encoder", OneHotEncoder(handle_unknown="ignore", sparse_output=False)),
    ])
    return ColumnTransformer([
        ("num", num_pipe, numerical_features),
        ("cat", cat_pipe, categorical_features),
    ])

def make_classifiers(params: dict, rs: int) -> dict:
    lr_p = params["models"]["logistic_regression"]
    rf_p = params["models"]["random_forest"]
    gb_p = params["models"]["gradient_boosting"]
    return {
        "Logistic Regression": LogisticRegression(
            max_iter=lr_p["max_iter"], random_state=rs,
            class_weight=lr_p["class_weight"], solver=lr_p["solver"],
        ),
        "Random Forest": RandomForestClassifier(
            n_estimators=rf_p["n_estimators"], random_state=rs,
            class_weight=rf_p["class_weight"], n_jobs=rf_p["n_jobs"],
        ),
        "Gradient Boosting": GradientBoostingClassifier(
            n_estimators=gb_p["n_estimators"], random_state=rs,
            learning_rate=gb_p["learning_rate"], max_depth=gb_p["max_depth"],
        ),
    }

def train_and_evaluate(classifiers: dict,preprocessor: ColumnTransformer,X_train: pd.DataFrame,X_test:  pd.DataFrame,y_train: pd.Series,y_test:pd.Series,label:str) -> tuple:
    """
    Train all classifiers.
    All 3 classifiers are trained, evaluated, and compared — the best by AUC is returned.
    """
    results   = {}
    best_model = None
    best_auc   = 0.0
    best_name  = ""
    cv = StratifiedKFold(n_splits=5, shuffle=True, random_state=42)

    for name, classifier in classifiers.items():
        logger.info(f"  Training [{label}] {name}...")

        model = Pipeline([
            ("preprocessor", preprocessor),
            ("classifier",   classifier),
        ])
        model.fit(X_train, y_train)

        y_pred = model.predict(X_test)
        y_pred_proba = model.predict_proba(X_test)[:, 1]

        auc = roc_auc_score(y_test, y_pred_proba)
        auc_pr  = average_precision_score(y_test, y_pred_proba)
        accuracy = accuracy_score(y_test, y_pred)
        precision = precision_score(y_test, y_pred, zero_division=0)
        recall  = recall_score(y_test, y_pred, zero_division=0)
        f1  = f1_score(y_test, y_pred, zero_division=0)

        cv_scores = cross_val_score(
            model, pd.concat([X_train, X_test]), pd.concat([y_train, y_test]),
            cv=cv, scoring="roc_auc", n_jobs=-1,
        )

        results[name] = {
            "model": model,
            "auc":auc,
            "auc_pr": auc_pr,
            "cv_auc_mean": cv_scores.mean(),
            "cv_auc_std": cv_scores.std(),
            "accuracy": accuracy,
            "precision":precision,
            "recall": recall,
            "f1":f1,
            "y_pred": y_pred,
            "y_pred_proba": y_pred_proba,
        }
        logger.info(
            f" AUC={auc:.4f}  AUC-PR={auc_pr:.4f}  "
            f"CV-AUC={cv_scores.mean():.4f}±{cv_scores.std():.4f}  "
            f"Recall={recall:.4f}  F1={f1:.4f}"
        )

        if auc > best_auc:
            best_auc   = auc
            best_model = model
            best_name  = name

    return results, best_name, best_model, best_auc

# for monthly auto-retraining
def run_training(customers_path: str = None,behavior_path: str = None) -> dict:
    """
    Full training pipeline — trains cold start + full model and saves .pkl files.
    Called by scheduler.py for monthly auto-retraining
    """
    params  = load_params()
    rs = params["data"]["random_state"]
    models_dir = os.path.join(PROJECT_ROOT, "models")
    os.makedirs(models_dir, exist_ok=True)
    _customers_path = customers_path or os.path.join(PROJECT_ROOT, "data", "customers.csv")
    _behavior_path  = behavior_path  or os.path.join(PROJECT_ROOT, "data", "credit_behavior_monthly.csv")
    data_path       = os.path.join(PROJECT_ROOT, "data", "model_snapshots.csv")
    logger.info("=" * 70)
    logger.info("TRAINING PIPELINE START")
    logger.info("=" * 70)
    logger.info("Loading data via snap pipeline...")
    ok = run_snap_pipeline(_customers_path, _behavior_path, data_path)
    if not ok:
        logger.warning("Snap pipeline failed — attempting to use existing model_snapshots.csv")

    df = pd.read_csv(data_path)
    df = df.drop(columns=["customer_id"], errors="ignore")
    logger.info(f"  Total samples:  {df.shape[0]:,}")
    logger.info(f"  Total features: {df.shape[1]}")
    logger.info(f"  Default rate:   {df['default_next_1m'].mean():.4f}")

    # Feature sets 
    logger.info("Defining feature sets...")

    static_features = [
        "age", "employment_status", "education_level", "monthly_income",
        "credit_limit", "city_tier", "dependents", "residence_type", "account_age_months",
    ]
    behavioral_features = [
        "util_avg_3m", "payment_ratio_avg_3m", "max_outstanding_3m",
        "avg_txn_amt_3m", "avg_txn_count_3m", "late_payments_3m",
        "missed_due_count_3m", "missed_due_last_1m", "payment_ratio_last_1m",
        "outstanding_delta_3m", "bnpl_active_last_1m",
        "consecutive_missed_due", "payment_ratio_min_3m", "worst_util_3m",
        "ever_defaulted", "default_count_history", "months_since_last_default",
        "outstanding_to_income_pct", "outstanding_to_limit_pct",
        "income_affordability_score", "debt_burden_category",
        "payment_ratio_trend", "utilization_trend", "outstanding_growth_rate",
        "is_deteriorating", "active_months_3m", "avg_util_when_active",
        "snapshot_account_age", "account_age_bucket", "snapshot_month",
    ]
    static_in_data     = [f for f in static_features     if f in df.columns]
    behavioral_in_data = [f for f in behavioral_features if f in df.columns]
    all_features       = static_in_data + behavioral_in_data
    logger.info(f"  Static: {len(static_in_data)}  Behavioral: {len(behavioral_in_data)}  Total: {len(all_features)}")

    # Prepare splits
    logger.info("Preparing train/test splits...")
    y = df["default_next_1m"]
    X_static = df[static_in_data].copy()
    X_full = df[all_features].copy()

    static_cat, static_num = get_feature_types(X_static)
    full_cat,   full_num   = get_feature_types(X_full)

    X_static_train, X_static_test, y_train, y_test = train_test_split(
        X_static, y, test_size=0.2, random_state=rs, stratify=y
    )
    X_full_train, X_full_test, _, _ = train_test_split(
        X_full, y, test_size=0.2, random_state=rs, stratify=y
    )
    logger.info(f"  Train: {len(X_static_train):,}  |  Test: {len(X_static_test):,}")

    # Build preprocessors 
    logger.info(" Building preprocessing pipelines...")
    static_preprocessor = build_preprocessor(static_num, static_cat)
    full_preprocessor   = build_preprocessor(full_num,   full_cat)

    # Train models 
    with mlflow.start_run(run_name=f"Train_{datetime.now().strftime('%Y%m%d_%H%M')}"):
        mlflow.log_param("test_size",0.2)
        mlflow.log_param("random_state",rs)
        mlflow.log_param("static_features", len(static_in_data))
        mlflow.log_param("all_features", len(all_features))

        # Cold Start Model
        logger.info("Training COLD START model")
        cs_results, cs_best_name, cs_best_model, cs_best_auc = train_and_evaluate(
            make_classifiers(params, rs), static_preprocessor,
            X_static_train, X_static_test, y_train, y_test, label="ColdStart",
        )
        logger.info(f"  ★ Best Cold Start: {cs_best_name} (AUC={cs_best_auc:.4f})")
        cs_best = cs_results[cs_best_name]
        mlflow.log_metric("cold_start_auc",    cs_best_auc)
        mlflow.log_metric("cold_start_auc_pr", cs_best["auc_pr"])
        mlflow.log_metric("cold_start_cv_auc", cs_best["cv_auc_mean"])
        mlflow.log_metric("cold_start_recall", cs_best["recall"])

        # Full Model
        logger.info("Training FULL model")
        full_results, full_best_name, full_best_model, full_best_auc = train_and_evaluate(
            make_classifiers(params, rs), full_preprocessor,
            X_full_train, X_full_test, y_train, y_test, label="Full",
        )
        logger.info(f"Best Full Model: {full_best_name} (AUC={full_best_auc:.4f})")
        full_best = full_results[full_best_name]
        mlflow.log_metric("full_model_auc",    full_best_auc)
        mlflow.log_metric("full_model_auc_pr", full_best["auc_pr"])
        mlflow.log_metric("full_model_cv_auc", full_best["cv_auc_mean"])
        mlflow.log_metric("full_model_recall", full_best["recall"])

        #  Save models & artifacts
        logger.info("Saving models and artifacts...")
        timestamp = datetime.now().strftime("%Y%m%d_%H%M")
        cs_path   = os.path.join(models_dir, "cold_start_model.pkl")
        full_path = os.path.join(models_dir, "credit_score_model.pkl")
        cfg_path  = os.path.join(models_dir, "feature_config.pkl")
        roc_path  = os.path.join(models_dir, "model_comparison_roc.png")

        # Save latest
        joblib.dump(cs_best_model,   cs_path)
        joblib.dump(full_best_model, full_path)

        # Save versioned copies
        cs_version = save_versioned_model(
            cs_best_model, "cold_start_model", models_dir,
            auc=cs_best_auc, algorithm=cs_best_name,
        )
        full_version = save_versioned_model(
            full_best_model, "credit_score_model", models_dir,
            auc=full_best_auc, algorithm=full_best_name,
        )
        logger.info(f"  Saved: {cs_path}  ({cs_best_name})")
        logger.info(f"  Saved: {full_path} ({full_best_name})")
        logger.info(f"  Versioned: cold_start_model v{cs_version}")
        logger.info(f"  Versioned: credit_score_model v{full_version}")

        feature_config = {
            "static_features": static_in_data,
            "behavioral_features": behavioral_in_data,
            "all_features": all_features,
            "static_categorical": static_cat,
            "static_numerical": static_num,
            "full_categorical": full_cat,
            "full_numerical": full_num,
        }
        joblib.dump(feature_config, cfg_path)
        mlflow.log_artifact(cfg_path)
        mlflow.sklearn.log_model(cs_best_model,"cold_start_model")
        mlflow.sklearn.log_model(full_best_model,"full_model")

        # ROC curves
        fig, axes = plt.subplots(1, 2, figsize=(14, 6))
        for ax, results_dict, title in [
            (axes[0], cs_results, "Cold Start Model\n(Static Features Only)"),
            (axes[1], full_results, "Full Model\n(All Features)"),
        ]:
            for name, res in results_dict.items():
                fpr, tpr, _ = roc_curve(y_test, res["y_pred_proba"])
                ax.plot(fpr, tpr, lw=2, label=f"{name} (AUC={res['auc']:.3f})")
            ax.plot([0, 1], [0, 1], "k--", lw=1, label="Random")
            ax.set_xlabel("False Positive Rate")
            ax.set_ylabel("True Positive Rate")
            ax.set_title(title)
            ax.legend(loc="lower right", fontsize=8)
            ax.grid(True, alpha=0.3)
        plt.tight_layout()
        plt.savefig(roc_path, dpi=150, bbox_inches="tight")
        plt.close()
        mlflow.log_artifact(roc_path)

        logger.info("TRAINING COMPLETE — all artifacts logged to MLflow.")

    return {
        "cold_start_auc":  round(cs_best_auc,  4),
        "full_model_auc":  round(full_best_auc, 4),
        "cold_start_algo": cs_best_name,
        "full_model_algo": full_best_name,
    }

if __name__ == "__main__":
    metrics = run_training()
    # Quick validation on 5 archetypal customers
    _cs_model = joblib.load(os.path.join(PROJECT_ROOT, "models", "cold_start_model.pkl"))

    def _prob_to_score(p: float) -> int:
        return int(max(300, min(900, 900 - p * 600)))

    def _get_decision(score: int) -> str:
        if   score >= 750: return "Approve"
        elif score >= 650: return "Approve_Low_Limit"
        elif score >= 550: return "Conditional"
        else:              return "Reject"

    test_customers = [
        {"name": "High Income Salaried",        "age": 35, "employment_status": "Salaried",
         "education_level": "Graduate",         "monthly_income": 80_000,  "credit_limit": 1_00_000,
         "city_tier": "Tier-1", "dependents": 1, "residence_type": "Owned", "account_age_months": 1},
        {"name": "Very High Income Executive",  "age": 45, "employment_status": "Salaried",
         "education_level": "Postgraduate",     "monthly_income": 1_50_000, "credit_limit": 1_00_000,
         "city_tier": "Tier-1", "dependents": 2, "residence_type": "Owned", "account_age_months": 0},
        {"name": "Middle Income Self-Employed", "age": 38, "employment_status": "Self-Employed",
         "education_level": "Graduate",         "monthly_income": 45_000, "credit_limit": 60_000,
         "city_tier": "Tier-2", "dependents": 2, "residence_type": "Rented", "account_age_months": 2},
        {"name": "Low Income Daily Wage",       "age": 32, "employment_status": "Daily Wage",
         "education_level": "Secondary",        "monthly_income": 15_000, "credit_limit": 10_000,
         "city_tier": "Tier-3", "dependents": 3, "residence_type": "Rented", "account_age_months": 0},
        {"name": "Fresh Graduate",              "age": 22, "employment_status": "Salaried",
         "education_level": "Graduate",         "monthly_income": 25_000, "credit_limit": 20_000,
         "city_tier": "Tier-2", "dependents": 0, "residence_type": "Rented", "account_age_months": 0},
    ]

    print(f"\n{'Customer Profile':<35} {'Prob':>6}  {'Score':>5}  Decision")
    print("-" * 65)
    for cust in test_customers:
        name = cust.pop("name")
        cdf  = pd.DataFrame([cust])
        prob = _cs_model.predict_proba(cdf)[0, 1]
        score = _prob_to_score(prob)
        print(f"{name:<35} {prob:.4f}  {score:>5}  {_get_decision(score)}")
    print("-" * 65)
    print(f"""
Files generated:
  models/cold_start_model.pkl — {metrics['cold_start_algo']}  (AUC={metrics['cold_start_auc']:.4f})
  models/credit_score_model.pkl — {metrics['full_model_algo']} (AUC={metrics['full_model_auc']:.4f})
  models/feature_config.pkl — feature lists
  models/model_comparison_roc.png — ROC curves

Auto-retraining usage (scheduler):
  from src.train_cold_start_model import run_training
  metrics = run_training()
""")
