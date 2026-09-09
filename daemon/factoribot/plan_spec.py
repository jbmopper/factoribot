"""Public, strictly validated contract for continuous factory optimization."""
from __future__ import annotations

import math

from .solver import SolverError


class PlanError(SolverError):
    def __init__(self, code: str, message: str, **details):
        super().__init__(message)
        self.code = code
        self.details = details


NUMBER = {"type": "number", "minimum": 0}
NAMES = {"type": "array", "items": {"type": "string", "minLength": 1}, "uniqueItems": True}
OBJECTIVES = [
    "maximize_ratio", "maximize_outputs", "minimize_inputs",
    "minimize_machines", "minimize_power", "feasible",
]


def mapping(values: dict) -> dict:
    return {"type": "object", "additionalProperties": values}


PLAN_SCHEMA = {
    "type": "object",
    "additionalProperties": False,
    "required": ["inputs", "outputs", "objective"],
    "properties": {
        "inputs": {
            **mapping({"anyOf": [NUMBER, {"type": "null"}]}),
            "description": "Available external inputs per second. null explicitly means unlimited. Unlisted inputs are unavailable.",
        },
        "outputs": {
            **mapping({
                "type": "object", "additionalProperties": False,
                "properties": {
                    "rate": NUMBER, "min": NUMBER, "max": NUMBER,
                    "ratio": {"type": "number", "exclusiveMinimum": 0},
                },
            }),
            "minProperties": 1,
            "description": "NET exports after internal consumption. rate is exact; min/max bound exports; ratio links selected exports to a common scale.",
        },
        "objective": {
            "type": "object", "additionalProperties": False, "required": ["kind"],
            "properties": {
                "kind": {"enum": OBJECTIVES},
                "weights": mapping({"type": "number", "exclusiveMinimum": 0}),
            },
            "description": "maximize_outputs and minimize_inputs require explicit positive weights keyed by output/input. Weighted output maximization does not ensure fairness; use maximize_ratio for proportions.",
        },
        "machines": mapping({"type": "string"}),
        "modules": mapping({"type": "array", "items": {"type": "string"}}),
        "beacons": mapping({
            "type": "object", "additionalProperties": False, "required": ["count", "modules"],
            "properties": {
                "count": {"type": "integer", "minimum": 0},
                "modules": {"type": "array", "items": {"type": "string"}},
                "beacon": {"type": "string"},
            },
        }),
        "recipes": mapping({"type": "string"}),
        "use_recipes": NAMES,
        "available_recipes": {
            **NAMES,
            "description": "Optional exhaustive recipe allowlist. Optimizer may mix these recipes, with no automatic dependency expansion. Omit to expand canonical/pinned recipes from outputs.",
        },
        "byproducts": {**NAMES, "description": "Items allowed to leave as surplus. All other non-output items must balance to zero."},
        "machine_limits": {**mapping(NUMBER), "description": "recipe -> maximum fractional machine equivalents. Not an integer placement model."},
        "max_power_w": {**NUMBER, "description": "Upper bound on modeled active crafting-machine power, excluding beacon and infrastructure power."},
    },
}


def validate_plan(request: dict) -> None:
    try:
        from jsonschema import Draft202012Validator
    except ImportError as e:
        raise PlanError("missing_dependency", "Install factoribot[planning] or factoribot[mcp].") from e
    error = next(Draft202012Validator(PLAN_SCHEMA).iter_errors(request), None)
    if error:
        path = ".".join(map(str, error.absolute_path)) or "request"
        raise PlanError("bad_request", f"{path}: {error.message}")

    def finite(value):
        if isinstance(value, (int, float)) and not isinstance(value, bool):
            try:
                valid = math.isfinite(value)
            except OverflowError:
                valid = False
            if not valid:
                raise PlanError("bad_request", "All numbers must be finite; use null only for unlimited inputs.")
        elif isinstance(value, dict):
            for child in value.values():
                finite(child)
        elif isinstance(value, list):
            for child in value:
                finite(child)

    finite(request)
    outputs = request["outputs"]
    kind = request["objective"]["kind"]
    ratios = []
    for item, cfg in outputs.items():
        if "rate" in cfg and ("min" in cfg or "max" in cfg):
            raise PlanError("bad_request", f"{item}: rate cannot be combined with min/max.")
        if cfg.get("max", math.inf) < cfg.get("min", 0):
            raise PlanError("bad_request", f"{item}: max must be >= min.")
        if "ratio" in cfg:
            ratios.append(item)
    if (kind == "maximize_ratio") != bool(ratios):
        raise PlanError("bad_request", "Ratios require maximize_ratio, and maximize_ratio requires at least one ratio.")
    weights = request["objective"].get("weights", {})
    if kind in ("maximize_outputs", "minimize_inputs"):
        domain = outputs if kind == "maximize_outputs" else request["inputs"]
        if not weights or set(weights) - set(domain):
            raise PlanError("bad_request", f"{kind} requires nonempty weights keyed by declared {'outputs' if kind == 'maximize_outputs' else 'inputs'}.")
        if kind == "minimize_inputs" and set(weights) != set(domain):
            raise PlanError("bad_request", "Give every declared input a cost weight for minimize_inputs.")
    elif "weights" in request["objective"]:
        raise PlanError("bad_request", f"weights are not used by {kind}.")
    if "available_recipes" in request and (request.get("recipes") or request.get("use_recipes")):
        raise PlanError("bad_request", "Use available_recipes OR recipes/use_recipes, not both.")
    overlap = set(request.get("byproducts", [])) & (set(outputs) | set(request["inputs"]))
    if overlap:
        raise PlanError("bad_request", "Declared inputs/outputs cannot also be surplus sinks.", items=sorted(overlap))
    # The core currently excludes beacon power; don't optimize a misleading total.
    if request.get("beacons") and (kind == "minimize_power" or "max_power_w" in request):
        raise PlanError("unsupported_feature", "Power constraints/objectives with beacons require a beacon sharing and power model.")
