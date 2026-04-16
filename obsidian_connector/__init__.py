"""obsidian-connector: Python wrapper for the Obsidian CLI."""

__version__ = "0.10.0"

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
# v0.6.0 modules
from obsidian_connector.write_manager import (
    atomic_write,
    check_protected,
    list_snapshots,
    preview,
    rollback,
    snapshot,
)
from obsidian_connector.draft_manager import (
    approve_draft,
    clean_stale_drafts,
    draft_summary,
    list_drafts,
    reject_draft,
)
from obsidian_connector.vault_registry import VaultEntry, VaultRegistry
from obsidian_connector.retrieval import hybrid_search
from obsidian_connector.template_engine import TemplateEngine, init_templates
from obsidian_connector.scheduler import Scheduler
from obsidian_connector.reports import generate_report
from obsidian_connector.telemetry import TelemetryCollector
from obsidian_connector.project_intelligence import (
    project_changelog,
    project_health,
    project_packet,
)
from obsidian_connector.commitment_notes import (
    ActionInput,
    WriteResult as CommitmentWriteResult,
    find_commitment_note,
    render_commitment_note,
    resolve_commitment_path,
    write_commitment_note,
)
from obsidian_connector.commitment_dashboards import (
    DASHBOARDS_DIR,
    DEFAULT_MERGE_JACCARD,
    DEFAULT_MERGE_WINDOW_DAYS,
    DEFAULT_STALE_DAYS,
    REVIEW_DASHBOARDS_DIR,
    DashboardResult,
    generate_commitments_dashboard,
    generate_daily_review_dashboard,
    generate_due_soon_dashboard,
    generate_merge_candidates_dashboard,
    generate_postponed_dashboard,
    generate_stale_dashboard,
    generate_waiting_on_me_dashboard,
    generate_weekly_review_dashboard,
    title_jaccard,
    update_all_dashboards,
    update_all_review_dashboards,
)
from obsidian_connector.entity_notes import (
    EntityInput,
    EntityWriteResult,
    LinkedAction as EntityLinkedAction,
    render_first_pass_wiki_body,
    resolve_entity_path,
    write_entity_note,
)
from obsidian_connector.errors import (
    ProtectedFolderError,
    RollbackError,
    WriteLockError,
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
    # v0.6.0 -- write safety
    "atomic_write",
    "check_protected",
    "list_snapshots",
    "preview",
    "rollback",
    "snapshot",
    "ProtectedFolderError",
    "RollbackError",
    "WriteLockError",
    # v0.6.0 -- draft management
    "approve_draft",
    "clean_stale_drafts",
    "draft_summary",
    "list_drafts",
    "reject_draft",
    # v0.6.0 -- vault registry
    "VaultEntry",
    "VaultRegistry",
    # v0.6.0 -- retrieval
    "hybrid_search",
    # v0.6.0 -- templates
    "TemplateEngine",
    "init_templates",
    # v0.6.0 -- scheduler
    "Scheduler",
    # v0.6.0 -- reports
    "generate_report",
    # v0.6.0 -- telemetry
    "TelemetryCollector",
    # v0.6.0 -- project intelligence
    "project_changelog",
    "project_health",
    "project_packet",
    # commitment notes (capture-service action representation)
    "ActionInput",
    "CommitmentWriteResult",
    "find_commitment_note",
    "render_commitment_note",
    "resolve_commitment_path",
    "write_commitment_note",
    # commitment dashboards
    "DASHBOARDS_DIR",
    "REVIEW_DASHBOARDS_DIR",
    "DEFAULT_STALE_DAYS",
    "DEFAULT_MERGE_WINDOW_DAYS",
    "DEFAULT_MERGE_JACCARD",
    "DashboardResult",
    "generate_commitments_dashboard",
    "generate_daily_review_dashboard",
    "generate_due_soon_dashboard",
    "generate_merge_candidates_dashboard",
    "generate_postponed_dashboard",
    "generate_stale_dashboard",
    "generate_waiting_on_me_dashboard",
    "generate_weekly_review_dashboard",
    "title_jaccard",
    "update_all_dashboards",
    "update_all_review_dashboards",
    # entity notes (Task 15.A / 30)
    "EntityInput",
    "EntityWriteResult",
    "EntityLinkedAction",
    "render_first_pass_wiki_body",
    "resolve_entity_path",
    "write_entity_note",
]
