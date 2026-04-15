"""Non-interactive onboarding walkthrough (Task 34).

Exposes the canonical 6-step bootstrap sequence for a brand-new
obsidian-connector install: vault setup, capture-service URL and token,
MCP registration, first sync.

The data shape is intentionally flat so callers can either render it
(``format_onboarding``) or serialize it (``obsx onboarding --json``)
without coupling to the CLI layer. Pure Python, no I/O, no network.

Kept paired with the capture-service walkthrough at
``docs/onboarding/ONBOARDING.md`` in the companion repo; the first step
of this connector-side sequence references that file.
"""
from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class OnboardingStep:
    index: int
    title: str
    summary: str
    commands: tuple[str, ...] = ()
    doc_refs: tuple[str, ...] = ()

    def to_dict(self) -> dict:
        return {
            "index": self.index,
            "title": self.title,
            "summary": self.summary,
            "commands": list(self.commands),
            "doc_refs": list(self.doc_refs),
        }


# Six steps, in the order a new operator should execute them. Each entry
# is self-contained so `--json` consumers can present a stable contract.
ONBOARDING_STEPS: tuple[OnboardingStep, ...] = (
    OnboardingStep(
        index=1,
        title="Vault setup",
        summary=(
            "Ensure the target Obsidian vault exists. For a fresh machine, "
            "initialize the scaffolding with `obsx init` so project tracking, "
            "Dashboards, and Commitments folders are present before capture "
            "traffic arrives."
        ),
        commands=("obsx init",),
        doc_refs=("README.md", "docs/index.md"),
    ),
    OnboardingStep(
        index=2,
        title="Capture-service URL",
        summary=(
            "Point the connector at the Mac-side capture service. The CLI "
            "and MCP tools read `OBSIDIAN_CAPTURE_SERVICE_URL` (default "
            "http://127.0.0.1:8787 for local dev, Tailscale DNS for remote)."
        ),
        commands=(
            'export OBSIDIAN_CAPTURE_SERVICE_URL="http://100.x.y.z:8787"',
        ),
        doc_refs=("CLAUDE.md",),
    ),
    OnboardingStep(
        index=3,
        title="Bearer token",
        summary=(
            "Share the same Bearer token the capture service emitted. The "
            "connector reads `OBSIDIAN_CAPTURE_SERVICE_TOKEN`; the Mac side "
            "generated this during `python -m app.setup_wizard`."
        ),
        commands=(
            'export OBSIDIAN_CAPTURE_SERVICE_TOKEN="paste-token-here"',
        ),
        doc_refs=(
            "../obsidian-capture-service/docs/onboarding/ONBOARDING.md",
        ),
    ),
    OnboardingStep(
        index=4,
        title="MCP registration",
        summary=(
            "Wire the MCP server into Claude Desktop (or any MCP client). "
            "The editable install exposes `obsidian-connector-mcp` as a "
            "console script, so the Desktop config only needs the command "
            "name plus PYTHONPATH/cwd."
        ),
        commands=(
            'which obsidian-connector-mcp',
            'obsidian-connector-mcp --help',
        ),
        doc_refs=("docs/setup-guide.md", "TOOLS_CONTRACT.md"),
    ),
    OnboardingStep(
        index=5,
        title="First sync",
        summary=(
            "Run an end-of-session sync so the vault picks up existing "
            "project state and any capture-service commitments already "
            "persisted to SQLite."
        ),
        commands=("obsx sync-projects",),
        doc_refs=("docs/daily-optimization.md",),
    ),
    OnboardingStep(
        index=6,
        title="Verify",
        summary=(
            "Use the MCP client (or `obsx doctor`) to confirm the connector "
            "sees the vault, service, and token. Follow the capture-service "
            "walkthrough once the connector side is green."
        ),
        commands=("obsx doctor",),
        doc_refs=(
            "../obsidian-capture-service/docs/onboarding/ONBOARDING.md",
        ),
    ),
)


def get_onboarding_payload() -> dict:
    """Return the serializable onboarding payload (stable contract)."""

    return {
        "version": 1,
        "total_steps": len(ONBOARDING_STEPS),
        "steps": [step.to_dict() for step in ONBOARDING_STEPS],
    }


def format_onboarding(payload: dict | None = None) -> str:
    """Render the walkthrough as a human-readable string."""

    payload = payload or get_onboarding_payload()
    lines: list[str] = [
        "obsidian-connector onboarding walkthrough",
        "=" * 42,
        f"{payload['total_steps']} steps. Execute top to bottom.",
        "",
    ]
    for step in payload["steps"]:
        lines.append(f"Step {step['index']}: {step['title']}")
        lines.append(f"  {step['summary']}")
        for cmd in step.get("commands") or ():
            lines.append(f"    $ {cmd}")
        refs = step.get("doc_refs") or ()
        if refs:
            lines.append(f"  docs: {', '.join(refs)}")
        lines.append("")
    lines.append("Full walkthrough: docs/ONBOARDING.md")
    return "\n".join(lines).rstrip() + "\n"
