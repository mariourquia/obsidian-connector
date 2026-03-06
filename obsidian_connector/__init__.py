"""obsidian-connector: Python wrapper for the Obsidian CLI."""

from obsidian_connector.cache import CLICache
from obsidian_connector.audit import log_action
from obsidian_connector.client import (
    ObsidianCLIError,
    list_tasks,
    log_to_daily,
    read_note,
    run_obsidian,
    search_notes,
)
from obsidian_connector.doctor import run_doctor
from obsidian_connector.envelope import error_envelope, success_envelope
from obsidian_connector.errors import (
    CommandTimeout,
    MalformedCLIOutput,
    ObsidianNotFound,
    ObsidianNotRunning,
    VaultNotFound,
)
from obsidian_connector.search import enrich_search_results
from obsidian_connector.workflows import (
    create_research_note,
    find_prior_work,
    log_decision,
)

__all__ = [
    "CLICache",
    "CommandTimeout",
    "MalformedCLIOutput",
    "ObsidianCLIError",
    "ObsidianNotFound",
    "ObsidianNotRunning",
    "VaultNotFound",
    "create_research_note",
    "enrich_search_results",
    "error_envelope",
    "find_prior_work",
    "list_tasks",
    "log_action",
    "log_decision",
    "log_to_daily",
    "read_note",
    "run_doctor",
    "run_obsidian",
    "search_notes",
    "success_envelope",
]
