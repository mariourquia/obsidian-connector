"""Smoke test: graphify submodules import cleanly when networkx is installed.

graphify ships as an optional extra (`pip install 'obsidian-connector[graphify]'`).
This test skips silently if networkx is not available in the environment so the
base test suite stays green without the extra, and verifies the lazy __init__
dispatch resolves to the right callables when the extra is installed.

Note on test ordering: the lazy __getattr__ tests run before the explicit
submodule import test because `from pkg.graphify import cluster as _m` caches
the submodule on the parent package, which then shadows the same-named
function in the lazy dispatch.
"""
from __future__ import annotations

import importlib

import pytest


pytest.importorskip("networkx")


def test_package_imports_without_networkx_dependency() -> None:
    """Importing the package itself must not pull networkx at module load."""
    mod = importlib.import_module("obsidian_connector.graphify")
    assert mod.__name__ == "obsidian_connector.graphify"


@pytest.mark.parametrize(
    "attr",
    [
        "extract",
        "collect_files",
        "build_from_json",
        "cluster",
        "score_all",
        "cohesion_score",
        "god_nodes",
        "surprising_connections",
        "suggest_questions",
        "generate",
        "to_json",
        "to_html",
        "to_svg",
        "to_canvas",
        "to_wiki",
    ],
)
def test_lazy_attr_resolves_to_callable(attr: str) -> None:
    import obsidian_connector.graphify as g

    resolved = getattr(g, attr)
    assert callable(resolved), f"{attr} did not resolve to a callable"


def test_unknown_attr_raises_attribute_error() -> None:
    import obsidian_connector.graphify as g

    with pytest.raises(AttributeError):
        _ = g.definitely_not_a_real_graphify_attr


def test_all_submodules_importable() -> None:
    """Every graphify submodule must import cleanly once networkx is present.

    Runs last so the submodule imports do not shadow the lazy attr dispatch
    for same-named public functions (extract, cluster) in earlier tests.
    """
    from obsidian_connector.graphify import analyze as _analyze  # noqa: F401
    from obsidian_connector.graphify import build as _build  # noqa: F401
    from obsidian_connector.graphify import cache as _cache  # noqa: F401
    from obsidian_connector.graphify import cluster as _cluster  # noqa: F401
    from obsidian_connector.graphify import detect as _detect  # noqa: F401
    from obsidian_connector.graphify import export as _export  # noqa: F401
    from obsidian_connector.graphify import extract as _extract  # noqa: F401
    from obsidian_connector.graphify import hooks as _hooks  # noqa: F401
    from obsidian_connector.graphify import ingest as _ingest  # noqa: F401
    from obsidian_connector.graphify import manifest as _manifest  # noqa: F401
    from obsidian_connector.graphify import report as _report  # noqa: F401
    from obsidian_connector.graphify import security as _security  # noqa: F401
    from obsidian_connector.graphify import transcribe as _transcribe  # noqa: F401
    from obsidian_connector.graphify import validate as _validate  # noqa: F401
    from obsidian_connector.graphify import watch as _watch  # noqa: F401
    from obsidian_connector.graphify import wiki as _wiki  # noqa: F401
