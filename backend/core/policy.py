from dataclasses import dataclass


VALID_POLICIES = ("eco", "balanced", "perf")


@dataclass(frozen=True)
class PolicyConfig:
    name: str
    min_hotspot_confidence: float
    optimized_flags: tuple[str, ...]
    baseline_flags: tuple[str, ...]


POLICY_CONFIGS = {
    "eco": PolicyConfig(
        name="eco",
        min_hotspot_confidence=0.6,
        optimized_flags=("-O2",),
        baseline_flags=("-O2",),
    ),
    "balanced": PolicyConfig(
        name="balanced",
        min_hotspot_confidence=0.75,
        optimized_flags=("-O3",),
        baseline_flags=("-O3",),
    ),
    "perf": PolicyConfig(
        name="perf",
        min_hotspot_confidence=0.9,
        optimized_flags=("-O3",),
        baseline_flags=("-O3",),
    ),
}


def normalize_policy(policy_name: str) -> str:
    normalized = (policy_name or "balanced").strip().lower()
    return normalized if normalized in VALID_POLICIES else "balanced"


def decide_transformation(has_hotspot: bool, policy_name: str, hotspot_confidence: float):
    policy = POLICY_CONFIGS[normalize_policy(policy_name)]
    if not has_hotspot:
        return {
            "apply_transform": False,
            "reason": "No hotspot detected by analyzer.",
            "policy": policy.name,
        }
    if hotspot_confidence < policy.min_hotspot_confidence:
        return {
            "apply_transform": False,
            "reason": (
                f"Hotspot confidence {hotspot_confidence:.2f} below "
                f"{policy.name} threshold {policy.min_hotspot_confidence:.2f}."
            ),
            "policy": policy.name,
        }
    return {
        "apply_transform": True,
        "reason": f"{policy.name} policy approved transformation.",
        "policy": policy.name,
    }
