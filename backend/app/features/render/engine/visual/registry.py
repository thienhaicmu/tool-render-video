"""
registry.py — Visual provider capability manifest + registry (CU-7).

The seam (``resolve_scene_visual``) dispatches by provider NAME. To ROUTE by cost
and capability (CU-8 Decision Tree / budget), each provider declares a manifest:
what it produces, whether it needs a key / network, its rough cost tier, and
(for later) whether it supports reference-image / seed conditioning.

Purely descriptive + additive — no behaviour change. A new provider (Flux / Pika /
Runway) becomes routable simply by adding its manifest here.
"""
from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class ProviderManifest:
    name: str
    kind: str                 # "flexible" (local) | "image" | "video"
    online: bool              # needs network
    needs_key: bool           # needs an API key to function
    # Rough relative cost per asset (0 = free/local). Used only for ordering +
    # budget estimation, not billing. Override via env in decision.estimate_cost.
    cost_tier: int
    # Forward-looking capability flags consumed by consistency v2/v3 (CU-11).
    supports_reference: bool = False
    supports_seed: bool = False


PROVIDER_MANIFESTS: dict[str, ProviderManifest] = {
    "local": ProviderManifest(
        name="local", kind="flexible", online=False, needs_key=False, cost_tier=0,
    ),
    "stock": ProviderManifest(
        name="stock", kind="image", online=True, needs_key=True, cost_tier=1,
    ),
    "ai_image": ProviderManifest(
        name="ai_image", kind="image", online=True, needs_key=True, cost_tier=2,
        supports_reference=True, supports_seed=True,
    ),
    "ai_video": ProviderManifest(
        name="ai_video", kind="video", online=True, needs_key=True, cost_tier=3,
        supports_reference=False, supports_seed=False,
    ),
}


def get_manifest(provider: str) -> ProviderManifest:
    """Return the manifest for a provider, defaulting to 'local' for unknowns."""
    return PROVIDER_MANIFESTS.get((provider or "").strip().lower(), PROVIDER_MANIFESTS["local"])


def list_providers() -> list[ProviderManifest]:
    return list(PROVIDER_MANIFESTS.values())


def is_online(provider: str) -> bool:
    return get_manifest(provider).online


__all__ = ["ProviderManifest", "PROVIDER_MANIFESTS", "get_manifest", "list_providers", "is_online"]
