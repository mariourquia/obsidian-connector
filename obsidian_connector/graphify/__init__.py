"""graphify - extract · build · cluster · analyze · report."""


def __getattr__(name):
    # Lazy imports so the package is importable before heavy deps (networkx, etc.)
    # are in place. Install extras with: pip install 'obsidian-connector[graphify]'.
    # Every branch below uses a hardcoded absolute import so the allowlist is
    # statically visible to security linters.
    if name == "extract":
        from obsidian_connector.graphify.extract import extract
        return extract
    if name == "collect_files":
        from obsidian_connector.graphify.extract import collect_files
        return collect_files
    if name == "build_from_json":
        from obsidian_connector.graphify.build import build_from_json
        return build_from_json
    if name == "cluster":
        from obsidian_connector.graphify.cluster import cluster
        return cluster
    if name == "score_all":
        from obsidian_connector.graphify.cluster import score_all
        return score_all
    if name == "cohesion_score":
        from obsidian_connector.graphify.cluster import cohesion_score
        return cohesion_score
    if name == "god_nodes":
        from obsidian_connector.graphify.analyze import god_nodes
        return god_nodes
    if name == "surprising_connections":
        from obsidian_connector.graphify.analyze import surprising_connections
        return surprising_connections
    if name == "suggest_questions":
        from obsidian_connector.graphify.analyze import suggest_questions
        return suggest_questions
    if name == "generate":
        from obsidian_connector.graphify.report import generate
        return generate
    if name == "to_json":
        from obsidian_connector.graphify.export import to_json
        return to_json
    if name == "to_html":
        from obsidian_connector.graphify.export import to_html
        return to_html
    if name == "to_svg":
        from obsidian_connector.graphify.export import to_svg
        return to_svg
    if name == "to_canvas":
        from obsidian_connector.graphify.export import to_canvas
        return to_canvas
    if name == "to_wiki":
        from obsidian_connector.graphify.wiki import to_wiki
        return to_wiki
    raise AttributeError(f"module 'graphify' has no attribute {name!r}")
