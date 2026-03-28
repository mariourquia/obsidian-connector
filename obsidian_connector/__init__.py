"""obsidian-connector: Python wrapper for the Obsidian CLI."""

__version__ = "0.4.0"

from obsidian_connector.cache import CLICache
from obsidian_connector.audit import log_action
from obsidian_connector.client import (
    batch_read_notes,
    list_tasks,
    log_to_daily,
    read_note,
    run_obsidian,
    search_notes,
)
from obsidian_connector.config import resolve_vault_path
from obsidian_connector.doctor import run_doctor
from obsidian_connector.envelope import error_envelope, success_envelope
from obsidian_connector.errors import (
    CommandTimeout,
    MalformedCLIOutput,
    ObsidianCLIError,
    ObsidianNotFound,
    ObsidianNotRunning,
    VaultNotFound,
)
from obsidian_connector.graph import (
    NoteEntry,
    NoteIndex,
    build_note_index,
    extract_frontmatter,
    extract_links,
    extract_tags,
    resolve_note_path,
)
from obsidian_connector.index_store import IndexStore, load_or_build_index
from obsidian_connector.search import enrich_search_results
from obsidian_connector.thinking import (
    deep_ideas,
    drift_analysis,
    ghost_voice_profile,
    trace_idea,
)
from obsidian_connector.project_sync import (
    RepoEntry,
    SessionEntry,
    SyncConfig,
    get_active_threads,
    get_project_status,
    get_running_todo,
    log_session,
    sync_projects,
)
from obsidian_connector.idea_router import (
    float_idea,
    incubate_project,
    list_idea_files,
    list_incubating,
)
from obsidian_connector.vault_factory import (
    create_vault,
    discard_vault,
    list_existing_vaults,
)
from obsidian_connector.vault_guardian import (
    detect_unorganized,
    mark_auto_generated,
    organize_file,
)
from obsidian_connector.vault_init import (
    discover_repos,
    init_vault,
)
from obsidian_connector.workflows import (
    challenge_belief,
    check_in,
    close_day_reflection,
    connect_domains,
    context_load_full,
    create_research_note,
    detect_delegations,
    emerge_ideas,
    find_prior_work,
    graduate_candidates,
    graduate_execute,
    list_open_loops,
    log_decision,
    my_world_snapshot,
    today_brief,
)

__all__ = [
    "CLICache",
    "CommandTimeout",
    "IndexStore",
    "MalformedCLIOutput",
    "NoteEntry",
    "NoteIndex",
    "ObsidianCLIError",
    "ObsidianNotFound",
    "ObsidianNotRunning",
    "VaultNotFound",
    "batch_read_notes",
    "build_note_index",
    "challenge_belief",
    "check_in",
    "deep_ideas",
    "drift_analysis",
    "close_day_reflection",
    "connect_domains",
    "context_load_full",
    "create_research_note",
    "detect_delegations",
    "emerge_ideas",
    "enrich_search_results",
    "error_envelope",
    "extract_frontmatter",
    "extract_links",
    "extract_tags",
    "find_prior_work",
    "ghost_voice_profile",
    "graduate_candidates",
    "graduate_execute",
    "list_open_loops",
    "list_tasks",
    "load_or_build_index",
    "log_action",
    "log_decision",
    "log_to_daily",
    "my_world_snapshot",
    "read_note",
    "resolve_note_path",
    "resolve_vault_path",
    "run_doctor",
    "run_obsidian",
    "search_notes",
    "success_envelope",
    "today_brief",
    "trace_idea",
    # project_sync
    "RepoEntry",
    "SessionEntry",
    "SyncConfig",
    "get_active_threads",
    "get_project_status",
    "get_running_todo",
    "log_session",
    "sync_projects",
    # idea_router
    "float_idea",
    "incubate_project",
    "list_idea_files",
    "list_incubating",
    # vault_factory
    "create_vault",
    "discard_vault",
    "list_existing_vaults",
    # vault_guardian
    "detect_unorganized",
    "mark_auto_generated",
    "organize_file",
    # vault_init
    "discover_repos",
    "init_vault",
]
