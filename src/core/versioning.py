"""
Model Versioning Utility
Provides timestamped model saving with rollback capability.
Instead of overwriting `cold_start_model.pkl` every training run,
this module:
  1. Saves versioned copies:  models/cold_start_model_20260306_021500.pkl
  2. Updates a symlink/copy:  models/cold_start_model.pkl  (always latest)
  3. Maintains a manifest:    models/model_manifest.json
"""
import glob
import json
import logging
import os
import shutil
from datetime import datetime
from typing import Dict, List, Optional

import joblib

logger = logging.getLogger(__name__)

MANIFEST_FILE = "model_manifest.json"
MAX_VERSIONS_KEPT = 10  # keep last N versions, prune older ones

def _manifest_path(models_dir: str) -> str:
    return os.path.join(models_dir, MANIFEST_FILE)

def _load_manifest(models_dir: str) -> Dict:
    path = _manifest_path(models_dir)
    if os.path.exists(path):
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    return {"models": {}}

def _save_manifest(models_dir: str, manifest: Dict) -> None:
    path = _manifest_path(models_dir)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(manifest, f, indent=2, default=str)

def save_versioned_model(model: object,base_name: str,models_dir: str = "models",auc: Optional[float] = None,algorithm: Optional[str] = None,) -> str:
    """
    Save a model with a timestamped version and update the 'latest' copy.
    """
    os.makedirs(models_dir, exist_ok=True)
    # Generate version timestamp
    version = datetime.now().strftime("%Y%m%d_%H%M%S")
    versioned_name = f"{base_name}_{version}.pkl"
    versioned_path = os.path.join(models_dir, versioned_name)
    latest_path = os.path.join(models_dir, f"{base_name}.pkl")

    # Save versioned copy
    joblib.dump(model, versioned_path)
    logger.info(f"Saved versioned model: {versioned_path}")

    # Update latest (overwrite)
    shutil.copy2(versioned_path, latest_path)
    logger.info(f"Updated latest: {latest_path}")

    # Update manifest
    manifest = _load_manifest(models_dir)
    if base_name not in manifest["models"]:
        manifest["models"][base_name] = {"current_version": None, "versions": []}

    entry = manifest["models"][base_name]
    entry["current_version"] = version
    entry["versions"].append({
        "version": version,
        "filename": versioned_name,
        "saved_at": datetime.now().isoformat(),
        "auc": auc,
        "algorithm": algorithm,
    })

    # Prune old versions
    if len(entry["versions"]) > MAX_VERSIONS_KEPT:
        to_remove = entry["versions"][:-MAX_VERSIONS_KEPT]
        entry["versions"] = entry["versions"][-MAX_VERSIONS_KEPT:]
        for old in to_remove:
            old_path = os.path.join(models_dir, old["filename"])
            if os.path.exists(old_path):
                os.remove(old_path)
                logger.info(f"Pruned old version: {old_path}")

    _save_manifest(models_dir, manifest)
    return version


def list_model_versions(base_name: str,models_dir: str = "models") -> List[Dict]:
    """
    List all saved versions of a model.
    """
    manifest = _load_manifest(models_dir)
    entry = manifest.get("models", {}).get(base_name, {})
    versions = entry.get("versions", [])
    # Also check for any versioned files on disk not in manifest
    pattern = os.path.join(models_dir, f"{base_name}_*.pkl")
    disk_files = sorted(glob.glob(pattern))
    manifest_files = {v["filename"] for v in versions}

    for f in disk_files:
        fname = os.path.basename(f)
        if fname not in manifest_files:
            # Extract version from filename
            ver = fname.replace(f"{base_name}_", "").replace(".pkl", "")
            versions.append({
                "version": ver,
                "filename": fname,
                "saved_at": None,
                "auc": None,
                "algorithm": None,
            })

    return sorted(versions, key=lambda v: v["version"])


def rollback_model(base_name: str,version: str,models_dir: str = "models",) -> bool:
    """
    Roll back a model to a specific version.
    Copies the versioned .pkl file over the latest .pkl file and updates
    the manifest's current_version.
    """
    versioned_path = os.path.join(models_dir, f"{base_name}_{version}.pkl")
    latest_path = os.path.join(models_dir, f"{base_name}.pkl")

    if not os.path.exists(versioned_path):
        logger.error(f"Version not found: {versioned_path}")
        return False

    shutil.copy2(versioned_path, latest_path)

    # Update manifest
    manifest = _load_manifest(models_dir)
    if base_name in manifest.get("models", {}):
        manifest["models"][base_name]["current_version"] = version
        _save_manifest(models_dir, manifest)

    logger.info(f"Rolled back {base_name} to version {version}")
    return True

def get_current_version(base_name: str,models_dir: str = "models") -> Optional[str]:
    """Return the current version string for a model, or None."""
    manifest = _load_manifest(models_dir)
    entry = manifest.get("models", {}).get(base_name, {})
    return entry.get("current_version")
