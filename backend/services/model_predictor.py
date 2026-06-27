from __future__ import annotations

from functools import lru_cache
from pathlib import Path
from typing import Iterable

import numpy as np


MODEL_DIR = Path(__file__).resolve().parents[1] / "models"

# The order is part of the model interface. It comes from both type-fix training
# notebooks and is also embedded in the two serialized XGBoost models.
FEATURE_NAMES = (
    "hor_depth",
    "int",
    "depth",
    "distance",
    "wwr",
    "hori_rot_eff",
    "ver_rot_eff",
    "glazing_u_value",
    "thermal_load_index",
    "wwr_ver_rot",
    "wwr_int",
    "shade_balance",
    "type_1",
    "type_2",
    "type_3",
    "mat_1",
    "mat_2",
    "mat_3",
    "win_1",
    "win_2",
    "win_3",
    "win_4",
)

GLAZING_U_VALUES = {1: 3.54, 2: 1.84, 3: 2.59, 4: 1.71}

MATERIAL_PROPS = {
    "thickness": {1: 50, 2: 5, 3: 5},
    "ce_factor": {1: 385, 2: 56231, 3: 16400},
    "density": {1: 2400, 2: 2770, 3: 8000},
    "distance": {1: 40, 2: 500, 3: 500},
    "replacement": {1: 1, 2: 2, 3: 2},
}

WINDOW_PARAMS = {
    1: {"initial_cost": 265, "maintenance_interval": 5, "maintenance_cost": 120, "residual_rate": 0.375, "replacement_times": 1},
    2: {"initial_cost": 450, "maintenance_interval": 5, "maintenance_cost": 120, "residual_rate": 0.375, "replacement_times": 1},
    3: {"initial_cost": 260, "maintenance_interval": 5, "maintenance_cost": 120, "residual_rate": 0.375, "replacement_times": 1},
    4: {"initial_cost": 700, "maintenance_interval": 5, "maintenance_cost": 120, "residual_rate": 0.375, "replacement_times": 1},
}

MATERIAL_COST_PARAMS = {
    1: {"initial_cost": 450, "maintenance_interval": 10, "maintenance_cost": 150, "residual_rate": 0.0, "replacement_times": 0},
    2: {"initial_cost": 420, "maintenance_interval": 5, "maintenance_cost": 75, "residual_rate": 0.30, "replacement_times": 1},
    3: {"initial_cost": 700, "maintenance_interval": 5, "maintenance_cost": 40, "residual_rate": 0.25, "replacement_times": 0},
}

ROOM_AREA = 90.0
WALL_AREA = 11.0 * 3.9
BUILDING_LIFE = 50
ELECTRICITY_PRICE = 0.8262
OPERATION_FACTOR = 0.3748 * BUILDING_LIFE


def _to_model_params(params: dict) -> dict:
    """Convert FacadeGPT UI units to the units used by the training dataset."""
    return {
        "hor_depth": float(params["horizontal_depth"]) / 100.0,
        "type": int(round(params["shading_type"])),
        "mat": int(round(params["material"])),
        "int": float(params["spacing"]) / 100.0,
        "hori_rot": float(params["h_rotation"]) / 10.0,
        "ver_rot": float(params["v_rotation"]) / 10.0,
        "depth": float(params["blade_depth"]) / 100.0,
        "distance": float(params["window_distance"]) / 100.0,
        "wwr": float(params["wwr"]) / 10.0,
        "win": int(round(params["glass_type"])),
    }


def _build_feature_row(design: dict) -> list[float]:
    shading_type = design["type"]
    material = design["mat"]
    window = design["win"]
    if shading_type not in (1, 2, 3):
        raise ValueError(f"Unsupported shading_type: {shading_type}")
    if material not in (1, 2, 3):
        raise ValueError(f"Unsupported material: {material}")
    if window not in GLAZING_U_VALUES:
        raise ValueError(f"Unsupported glass_type: {window}")
    if design["wwr"] <= 0:
        raise ValueError("wwr must be greater than zero")

    hori_rot_eff = design["hori_rot"] if shading_type in (1, 3) else 0.0
    ver_rot_eff = design["ver_rot"] if shading_type in (2, 3) else 0.0
    glazing_u_value = GLAZING_U_VALUES[window]

    return [
        design["hor_depth"],
        design["int"],
        design["depth"],
        design["distance"],
        design["wwr"],
        hori_rot_eff,
        ver_rot_eff,
        glazing_u_value,
        (design["wwr"] / 100.0) * glazing_u_value,
        design["wwr"] * ver_rot_eff,
        design["wwr"] * design["int"],
        design["hor_depth"] / design["wwr"],
        *[1.0 if shading_type == value else 0.0 for value in (1, 2, 3)],
        *[1.0 if material == value else 0.0 for value in (1, 2, 3)],
        *[1.0 if window == value else 0.0 for value in (1, 2, 3, 4)],
    ]


def _model_feature_names(model) -> list[str]:
    names = getattr(model, "feature_names_in_", None)
    if names is None and hasattr(model, "get_booster"):
        names = model.get_booster().feature_names
    return [] if names is None else list(names)


@lru_cache(maxsize=1)
def _load_models():
    try:
        import joblib
    except ImportError as exc:  # pragma: no cover - exercised only on broken deployments
        raise RuntimeError("Model runtime is missing; install backend/requirements.txt") from exc

    energy_model = joblib.load(MODEL_DIR / "energy_model.pkl")
    sda_model = joblib.load(MODEL_DIR / "sDA_mode.pkl")
    for label, model in (("energy", energy_model), ("sDA", sda_model)):
        actual = _model_feature_names(model)
        if actual and actual != list(FEATURE_NAMES):
            raise RuntimeError(f"{label} model feature interface does not match the type-fix training code")
    return energy_model, sda_model


def calculate_lcce(annual_energy: float, design: dict) -> float:
    """Calculate 50-year life-cycle carbon emissions in kgCO2/m2."""
    horizontal_depth = design["hor_depth"] / 10.0
    blade_depth = design["depth"] / 10.0
    spacing = design["int"] / 10.0
    material = design["mat"]
    shading_type = design["type"]
    if spacing <= 0:
        raise ValueError("spacing must be greater than zero")

    horizontal_volume = horizontal_depth * 11.0 * (50.0 / 1000.0)
    if shading_type == 1:
        count = int(11.0 / spacing)
        area = count * 3.9 * blade_depth
    elif shading_type == 2:
        count = int(3.9 / spacing)
        area = count * 11.0 * blade_depth
    else:
        horizontal_count = int(3.9 / spacing)
        vertical_count = int(11.0 / spacing)
        area = horizontal_count * 11.0 * blade_depth + vertical_count * 3.9 * blade_depth
    volume = area * (MATERIAL_PROPS["thickness"][material] / 1000.0)

    production = (
        horizontal_volume * MATERIAL_PROPS["ce_factor"][1]
        + volume * MATERIAL_PROPS["ce_factor"][material]
    ) / ROOM_AREA
    transport_concrete = horizontal_volume * MATERIAL_PROPS["density"][1] * MATERIAL_PROPS["distance"][1] * 0.001 * 0.143
    transport_material = volume * MATERIAL_PROPS["density"][material] * MATERIAL_PROPS["distance"][material] * 0.001 * 0.143
    transportation = (transport_concrete + transport_material) * MATERIAL_PROPS["replacement"][material] / ROOM_AREA
    operation = annual_energy * OPERATION_FACTOR
    construction = 39.5 * area * MATERIAL_PROPS["replacement"][material] ** 2 / ROOM_AREA
    demolition_transport = (
        horizontal_volume * MATERIAL_PROPS["density"][1] * 40.0
        + volume * MATERIAL_PROPS["density"][material] * 40.0
    ) * 0.001 * 0.143
    demolition = (36.0 * area + demolition_transport) * MATERIAL_PROPS["replacement"][material] / ROOM_AREA
    return production + transportation + operation + construction + demolition


def _shading_area(design: dict) -> float:
    spacing = design["int"] / 10.0
    blade_depth = design["depth"] / 10.0
    if spacing <= 0:
        raise ValueError("spacing must be greater than zero")
    total = 0.0
    if design["type"] in (1, 3):
        total += (11.0 / spacing) * (11.0 * blade_depth)
    if design["type"] in (2, 3):
        total += (3.9 / spacing) * (3.9 * blade_depth)
    return total


def calculate_lcc(annual_energy: float, design: dict) -> float:
    """Calculate undiscounted 50-year life-cycle cost in yuan/m2."""
    shading_area = _shading_area(design)
    horizontal_depth = design["hor_depth"] / 10.0
    window_area = (design["wwr"] / 10.0) * WALL_AREA
    material = MATERIAL_COST_PARAMS[design["mat"]]
    window = WINDOW_PARAMS[design["win"]]

    initial = (
        material["initial_cost"] * shading_area
        + horizontal_depth * 11.0 * 450.0
        + window["initial_cost"] * window_area
    ) / ROOM_AREA
    maintenance = (
        (BUILDING_LIFE // material["maintenance_interval"]) * material["maintenance_cost"] * shading_area
        + (BUILDING_LIFE // window["maintenance_interval"]) * window["maintenance_cost"] * window_area
    ) / ROOM_AREA
    replacement = (
        material["replacement_times"] * material["initial_cost"] * shading_area
        + window["replacement_times"] * window["initial_cost"] * window_area
    ) / ROOM_AREA
    residual = (
        material["initial_cost"] * shading_area * material["residual_rate"]
        + window["initial_cost"] * window_area * window["residual_rate"]
    ) / ROOM_AREA
    energy_cost = annual_energy * ELECTRICITY_PRICE * BUILDING_LIFE
    return initial + maintenance + replacement - residual + energy_cost


def predict_performance_many(params_list: Iterable[dict], orientation: str = "") -> list[dict]:
    """Predict energy/sDA in one batch, then derive LCCE and LCC from that energy."""
    del orientation  # Orientation was not a feature in either supplied training model.
    params_list = list(params_list)
    if not params_list:
        return []
    designs = [_to_model_params(params) for params in params_list]
    features = np.asarray([_build_feature_row(design) for design in designs], dtype=float)
    energy_model, sda_model = _load_models()
    energy_predictions = energy_model.predict(features)
    sda_predictions = np.clip(sda_model.predict(features), 0, 100)

    return [
        {
            "lcce": round(calculate_lcce(float(energy), design), 2),
            "lcc": round(calculate_lcc(float(energy), design), 2),
            "sda": round(float(sda), 2),
        }
        for design, energy, sda in zip(designs, energy_predictions, sda_predictions)
    ]


def predict_performance(params: dict, orientation: str) -> dict:
    return predict_performance_many([params], orientation)[0]


def rank_performance(perf: dict) -> dict:
    return {
        "lcce_rank": "优" if perf["lcce"] <= 2850 else "中" if perf["lcce"] <= 2950 else "待优化",
        "lcc_rank": "优" if perf["lcc"] <= 6800 else "中" if perf["lcc"] <= 7300 else "待优化",
        "sda_rank": "优" if perf["sda"] >= 75 else "中" if perf["sda"] >= 50 else "待优化",
    }


def fitness(perf: dict, weights: dict, bounds: dict | None = None) -> float:
    bounds = bounds or {"lcce": (2800.0, 3200.0), "lcc": (6000.0, 8500.0), "sda": (0.0, 100.0)}

    def quality(key: str, lower_is_better: bool) -> float:
        low, high = bounds[key]
        if high <= low:
            return 1.0
        value = (perf[key] - low) / (high - low)
        value = max(0.0, min(1.0, value))
        return 1.0 - value if lower_is_better else value

    score = (
        weights["lcce"] * quality("lcce", True)
        + weights["lcc"] * quality("lcc", True)
        + weights["sda"] * quality("sda", False)
    )
    return round(score, 3)
