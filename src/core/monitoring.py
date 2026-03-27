"""
Model Monitoring — Drift Detection & AUC Alerting
Tracks prediction distribution over time to detect model drift.
Provides alerts when model performance may be degrading.
"""
import logging
import statistics
from collections import deque
from datetime import datetime
from typing import Dict, List, Optional

logger = logging.getLogger(__name__)

# Configuration - automatic alerts if model performance falls below this 
AUC_ALERT_THRESHOLD = 0.65      
DRIFT_WINDOW_SIZE = 1000        
DRIFT_ALERT_SHIFT = 0.10       

class PredictionTracker:
    """
    Tracks recent predictions to detect model drift.
    Maintains a rolling window of predictions and compares the
    distribution to a baseline captured at model load time.
    """
    def __init__(self, window_size: int = DRIFT_WINDOW_SIZE) -> None:
        self.window_size = window_size
        self.predictions: deque = deque(maxlen=window_size)
        self.baseline_mean: Optional[float] = None
        self.baseline_std: Optional[float] = None
        self.baseline_set_at: Optional[str] = None
        self.last_known_auc: Optional[float] = None
        self.auc_updated_at: Optional[str] = None
        self.decision_counts: Dict[str, int] = {
            "Approve": 0,
            "Approve_Low_Limit": 0,
            "Conditional": 0,
            "Reject": 0,
        }
        self.total_predictions: int = 0

    def record(self,probability: float,score: int,decision: str,) -> None:
        self.predictions.append({
            "probability": probability,
            "score": score,
            "decision": decision,
            "timestamp": datetime.now().isoformat(),
        })
        self.total_predictions += 1
        if decision in self.decision_counts:
            self.decision_counts[decision] += 1

    def set_baseline(self) -> None:
        """
        Capture current prediction distribution as the baseline.
        Call this after model training / loading.
        """
        if len(self.predictions) < 50:
            logger.warning("Not enough predictions to set baseline (need ≥50)")
            return

        probs = [p["probability"] for p in self.predictions]
        self.baseline_mean = statistics.mean(probs)
        self.baseline_std = statistics.stdev(probs) if len(probs) > 1 else 0.0
        self.baseline_set_at = datetime.now().isoformat()
        logger.info(
            f"Baseline set: mean={self.baseline_mean:.4f}, "
            f"std={self.baseline_std:.4f}, n={len(probs)}"
        )

    def update_auc(self, cold_start_auc: float, full_model_auc: float) -> None:
        self.last_known_auc = full_model_auc  # primary model AUC
        self.auc_updated_at = datetime.now().isoformat()

    def get_drift_metrics(self) -> Dict:
        """
        Compute drift metrics comparing current predictions to baseline.
        """
        alerts: List[str] = []
        current_mean = None
        current_std = None
        drift_detected = False
        mean_shift = None

        if len(self.predictions) >= 20:
            probs = [p["probability"] for p in self.predictions]
            current_mean = statistics.mean(probs)
            current_std = statistics.stdev(probs) if len(probs) > 1 else 0.0

            # Check drift against baseline
            if self.baseline_mean is not None:
                mean_shift = abs(current_mean - self.baseline_mean)
                if mean_shift > DRIFT_ALERT_SHIFT:
                    drift_detected = True
                    direction = "higher" if current_mean > self.baseline_mean else "lower"
                    alerts.append(
                        f"⚠️ Prediction drift detected: mean probability shifted "
                        f"{direction} by {mean_shift:.4f} (threshold: {DRIFT_ALERT_SHIFT})"
                    )

        # AUC threshold alert
        if self.last_known_auc is not None and self.last_known_auc < AUC_ALERT_THRESHOLD:
            alerts.append(
                f"🚨 AUC below threshold: {self.last_known_auc:.4f} < {AUC_ALERT_THRESHOLD}"
            )

        # Decision distribution skew alert
        total = sum(self.decision_counts.values())
        if total > 100:
            reject_pct = self.decision_counts.get("Reject", 0) / total
            approve_pct = self.decision_counts.get("Approve", 0) / total
            if reject_pct > 0.50:
                alerts.append(
                    f"⚠️ High rejection rate: {reject_pct:.1%} of predictions are Reject"
                )
            if approve_pct > 0.90:
                alerts.append(
                    f"⚠️ Too permissive: {approve_pct:.1%} of predictions are Approve"
                )

        return {
            "total_predictions": self.total_predictions,
            "window_size": len(self.predictions),
            "current_distribution": {
                "mean_probability": round(current_mean, 4) if current_mean else None,
                "std_probability": round(current_std, 4) if current_std else None,
            },
            "baseline": {
                "mean_probability": round(self.baseline_mean, 4) if self.baseline_mean else None,
                "std_probability": round(self.baseline_std, 4) if self.baseline_std else None,
                "set_at": self.baseline_set_at,
            },
            "drift": {
                "detected": drift_detected,
                "mean_shift": round(mean_shift, 4) if mean_shift is not None else None,
                "alert_threshold": DRIFT_ALERT_SHIFT,
            },
            "auc": {
                "last_known": self.last_known_auc,
                "alert_threshold": AUC_ALERT_THRESHOLD,
                "updated_at": self.auc_updated_at,
            },
            "decision_distribution": {
                k: {"count": v, "pct": round(v / total * 100, 1) if total > 0 else 0}
                for k, v in self.decision_counts.items()
            },
            "alerts": alerts,
        }


# Global singleton 
prediction_tracker = PredictionTracker()
