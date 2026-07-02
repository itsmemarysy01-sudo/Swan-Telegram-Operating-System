"""
Migration Guide for Event Types Optimization (v2.3.2 → v2.3.3)

This document outlines the breaking changes introduced by the event_types.py optimization
and provides step-by-step instructions for migrating existing code and data.

Changes Overview:
- CanonicalEvent.raw (Dict) → raw_id (str reference)
- Lists → Tuples for immutable collections
- Strings → Enums for resource types, actor types, roles
- list[str] → frozenset[str] for permissions
"""

# ============================================================================
# BREAKING CHANGES SUMMARY
# ============================================================================

BREAKING_CHANGES = {
    "CanonicalEvent": {
        "old": "raw: Dict[str, Any]",
        "new": "raw_id: Optional[str]",
        "impact": "HIGH - All code accessing event.raw will fail",
        "migration": "Replace with kv.get(['cache', 'raw', raw_id])",
    },
    "PollAnswerEvent": {
        "old": "options: list[int]",
        "new": "options: tuple[int, ...]",
        "impact": "MEDIUM - List methods (append, extend) will fail",
        "migration": "Use options property; convert to tuple for creation",
    },
    "ExecutionPlan": {
        "old": "state_mutations: list[StateMutation]",
        "new": "state_mutations: tuple[StateMutation, ...]",
        "impact": "MEDIUM - List mutations will fail",
        "migration": "Convert lists to tuples during creation",
    },
    "OutboxEntry": {
        "old": "buttons: Optional[list[Dict[str, str]]]",
        "new": "buttons: Optional[tuple[Dict[str, str], ...]]",
        "impact": "MEDIUM - List operations on buttons will fail",
        "migration": "Convert button lists to tuples",
    },
    "Actor": {
        "old": "permissions: list[str]",
        "new": "permissions: frozenset[str]",
        "impact": "MEDIUM - List iteration will work, but membership tests change",
        "migration": "Use Actor.model_validate() for automatic conversion",
    },
    "AuditEntry": {
        "old": "resource_type: str",
        "new": "resource_type: ResourceType (enum)",
        "impact": "HIGH - String comparisons will fail",
        "migration": "Replace with ResourceType.POST, ResourceType.TICKET, etc.",
    },
    "StateMutation": {
        "old": "key: list[str]",
        "new": "key: tuple[str, ...]",
        "impact": "MEDIUM - List operations will fail",
        "migration": "Convert key paths to tuples",
    },
}

# ============================================================================
# ENUM MAPPINGS
# ============================================================================

RESOURCE_TYPE_MAPPING = {
    "post": "ResourceType.POST",
    "ticket": "ResourceType.TICKET",
    "member": "ResourceType.MEMBER",
    "broadcast": "ResourceType.BROADCAST",
}

ACTOR_TYPE_MAPPING = {
    "user": "ActorType.USER",
    "bot": "ActorType.BOT",
    "group": "ActorType.GROUP",
    "channel": "ActorType.CHANNEL",
}

ACTOR_ROLE_MAPPING = {
    "OWNER": "ActorRole.OWNER",
    "EDITOR": "ActorRole.EDITOR",
    "MEMBER": "ActorRole.MEMBER",
    "GUEST": "ActorRole.GUEST",
}

# ============================================================================
# PHASE 1: IDENTIFY AFFECTED CODE
# ============================================================================

SEARCH_PATTERNS = {
    "raw_access": [
        r"event\.raw",
        r"\.raw\[",
        r"\.raw\.get\(",
    ],
    "list_operations": [
        r"\.append\(",
        r"\.extend\(",
        r"\.pop\(",
        r"\[0\]",  # Index access
    ],
    "string_resource_types": [
        r'"post"',
        r'"ticket"',
        r'"member"',
        r'"broadcast"',
        r"'post'",
        r"'ticket'",
        r"'member'",
        r"'broadcast'",
    ],
    "permissions_list": [
        r"permissions\s*:\s*List\[str\]",
        r"permissions\s*=\s*\[",
    ],
}

# ============================================================================
# MIGRATION EXECUTION ORDER
# ============================================================================

MIGRATION_PHASES = [
    {
        "phase": 1,
        "name": "Setup Raw Object Cache",
        "description": "Create cache infrastructure for raw Telegram objects",
        "steps": [
            "Create cache_service.py",
            "Implement cache_raw_object(raw: Dict) -> str",
            "Implement retrieve_raw_object(raw_id: str) -> Dict",
            "Add cache cleanup job (TTL-based)",
        ],
    },
    {
        "phase": 2,
        "name": "Update Model Creation Code",
        "description": "Update all code that creates CanonicalEvent instances",
        "steps": [
            "Find all CanonicalEvent(..., raw=...) calls",
            "Replace with: raw_id = cache_raw(raw_dict); CanonicalEvent(..., raw_id=raw_id)",
            "Update factory functions",
            "Add tests for new flow",
        ],
    },
    {
        "phase": 3,
        "name": "Update Raw Object Access",
        "description": "Replace direct event.raw access with cache lookups",
        "steps": [
            "Find all event.raw accesses",
            "Replace with: raw_obj = retrieve_raw(event.raw_id)",
            "Add null checks",
            "Update error handling",
        ],
    },
    {
        "phase": 4,
        "name": "Convert Collections to Tuples",
        "description": "Replace list operations with tuple-safe code",
        "steps": [
            "Find list assignments in ExecutionPlan, OutboxEntry, StateMutation",
            "Convert to tuple(...) during creation",
            "Remove any list mutations (append, extend, pop)",
            "Update tests",
        ],
    },
    {
        "phase": 5,
        "name": "Convert String Enums",
        "description": "Replace string literals with enum values",
        "steps": [
            "Find all resource_type string assignments",
            "Replace with ResourceType enum values",
            "Find actor_type string assignments",
            "Replace with ActorType enum values",
            "Find role string assignments",
            "Replace with ActorRole enum values",
        ],
    },
    {
        "phase": 6,
        "name": "Migrate Stored Data",
        "description": "Migrate existing KV data to new format",
        "steps": [
            "Run data_migration_job.py",
            "Backup before migration",
            "Handle errors gracefully",
            "Verify data integrity",
            "Run in production with monitoring",
        ],
    },
    {
        "phase": 7,
        "name": "Update Tests & Validation",
        "description": "Ensure all tests pass with new types",
        "steps": [
            "Update unit tests",
            "Update integration tests",
            "Update fixtures",
            "Add new tests for cache operations",
            "Add compatibility tests",
        ],
    },
]
