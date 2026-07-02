"""
Migration utilities and code generation for event_types.py optimization.

This module provides tools to:
1. Convert between old and new model formats
2. Migrate stored data in KV
3. Validate migration completeness
"""

from typing import Dict, Any, List, Optional, Tuple
from datetime import datetime
import asyncio
import logging

logger = logging.getLogger(__name__)


# ============================================================================
# CONVERSION UTILITIES
# ============================================================================

class ModelConverter:
    """Converts between old and new model formats."""
    
    @staticmethod
    def raw_dict_to_raw_id(raw: Dict[str, Any], cache_service) -> str:
        """
        Convert raw Telegram object to cached reference.
        
        Args:
            raw: Raw Telegram dict object
            cache_service: Cache service instance
        
        Returns:
            raw_id string for lookup
        """
        if not raw:
            return None
        
        # Store raw object in cache
        raw_id = cache_service.cache_raw_object(raw)
        logger.info(f"Cached raw object: {raw_id}")
        return raw_id
    
    @staticmethod
    def list_to_tuple(items: List[Any]) -> Tuple:
        """Convert list to immutable tuple."""
        if items is None:
            return None
        return tuple(items)
    
    @staticmethod
    def list_to_frozenset(items: List[str]) -> frozenset:
        """Convert list of strings to frozenset for O(1) lookup."""
        if items is None:
            return frozenset()
        return frozenset(items)
    
    @staticmethod
    def string_to_resource_type(resource_type: str):
        """Convert string to ResourceType enum."""
        from src.architecture.event_types import ResourceType
        
        mapping = {
            "post": ResourceType.POST,
            "ticket": ResourceType.TICKET,
            "member": ResourceType.MEMBER,
            "broadcast": ResourceType.BROADCAST,
        }
        
        if resource_type not in mapping:
            raise ValueError(f"Unknown resource type: {resource_type}")
        
        return mapping[resource_type]
    
    @staticmethod
    def string_to_actor_type(actor_type: str):
        """Convert string to ActorType enum."""
        from src.architecture.event_types import ActorType
        
        mapping = {
            "user": ActorType.USER,
            "bot": ActorType.BOT,
            "group": ActorType.GROUP,
            "channel": ActorType.CHANNEL,
        }
        
        if actor_type not in mapping:
            raise ValueError(f"Unknown actor type: {actor_type}")
        
        return mapping[actor_type]
    
    @staticmethod
    def string_to_actor_role(role: str):
        """Convert string to ActorRole enum."""
        from src.architecture.event_types import ActorRole
        
        mapping = {
            "OWNER": ActorRole.OWNER,
            "EDITOR": ActorRole.EDITOR,
            "MEMBER": ActorRole.MEMBER,
            "GUEST": ActorRole.GUEST,
        }
        
        if role not in mapping:
            raise ValueError(f"Unknown actor role: {role}")
        
        return mapping[role]


# ============================================================================
# CACHE SERVICE
# ============================================================================

class RawObjectCacheService:
    """
    Manages caching of raw Telegram objects to reduce memory footprint.
    
    Raw Telegram objects are often large and redundant. This service:
    - Stores raw objects with TTL
    - Returns references (raw_id) for events
    - Cleans up expired entries
    """
    
    def __init__(self, kv_client, ttl_seconds: int = 3600):
        """
        Initialize cache service.
        
        Args:
            kv_client: Deno KV or equivalent client
            ttl_seconds: Cache time-to-live (default 1 hour)
        """
        self.kv = kv_client
        self.ttl_seconds = ttl_seconds
    
    async def cache_raw_object(self, raw: Dict[str, Any]) -> str:
        """
        Cache a raw Telegram object and return reference ID.
        
        Args:
            raw: Raw Telegram object dict
        
        Returns:
            raw_id string for later retrieval
        """
        import uuid
        
        raw_id = str(uuid.uuid4())
        expiration = datetime.now().timestamp() + self.ttl_seconds
        
        key = ["cache", "raw", raw_id]
        value = {
            "data": raw,
            "expiration": expiration,
            "created_at": datetime.now().isoformat(),
        }
        
        await self.kv.set(key, value)
        logger.debug(f"Cached raw object: {raw_id} (expires: {expiration})")
        
        return raw_id
    
    async def retrieve_raw_object(self, raw_id: Optional[str]) -> Optional[Dict[str, Any]]:
        """
        Retrieve cached raw object.
        
        Args:
            raw_id: Reference ID from CanonicalEvent.raw_id
        
        Returns:
            Raw Telegram object dict or None
        """
        if not raw_id:
            return None
        
        key = ["cache", "raw", raw_id]
        cached = await self.kv.get(key)
        
        if not cached:
            logger.warning(f"Cache miss for raw_id: {raw_id}")
            return None
        
        # Check expiration
        if datetime.now().timestamp() > cached.get("expiration", 0):
            logger.warning(f"Cached raw object expired: {raw_id}")
            await self.kv.delete(key)
            return None
        
        logger.debug(f"Retrieved cached raw object: {raw_id}")
        return cached.get("data")
    
    async def cleanup_expired_cache(self) -> int:
        """
        Remove expired cache entries.
        
        Returns:
            Number of entries cleaned up
        """
        prefix = ["cache", "raw"]
        cleaned = 0
        current_time = datetime.now().timestamp()
        
        # Scan cache entries
        async for entry in self.kv.list(prefix):
            if entry.get("expiration", 0) < current_time:
                await self.kv.delete(entry["key"])
                cleaned += 1
                logger.debug(f"Cleaned expired cache: {entry['key']}")
        
        logger.info(f"Cache cleanup completed: {cleaned} entries removed")
        return cleaned


# ============================================================================
# DATA MIGRATION
# ============================================================================

class DataMigrator:
    """
    Migrates existing KV data from old to new format.
    
    Handles:
    - Audit entries with string resource_type → enum
    - State mutations with list keys → tuple keys
    - Outbox entries with list buttons → tuple buttons
    - Actor records with list permissions → frozenset
    """
    
    def __init__(self, kv_client, cache_service):
        """Initialize migrator."""
        self.kv = kv_client
        self.cache = cache_service
        self.converter = ModelConverter()
        self.stats = {
            "audits_migrated": 0,
            "actors_migrated": 0,
            "outbox_migrated": 0,
            "errors": [],
        }
    
    async def migrate_audit_entries(self) -> int:
        """
        Migrate audit entries: string resource_type → enum.
        
        Returns:
            Number of entries migrated
        """
        prefix = ["audit"]
        migrated = 0
        
        try:
            async for entry in self.kv.list(prefix):
                try:
                    data = entry.value
                    
                    # Convert resource_type string to enum
                    if isinstance(data.get("resource_type"), str):
                        data["resource_type"] = self.converter.string_to_resource_type(
                            data["resource_type"]
                        )
                        
                        # Update KV
                        await self.kv.set(entry.key, data)
                        migrated += 1
                        logger.debug(f"Migrated audit entry: {entry.key}")
                
                except Exception as e:
                    error_msg = f"Error migrating {entry.key}: {str(e)}"
                    logger.error(error_msg)
                    self.stats["errors"].append(error_msg)
        
        except Exception as e:
            logger.error(f"Audit migration failed: {str(e)}")
            self.stats["errors"].append(str(e))
        
        self.stats["audits_migrated"] = migrated
        return migrated
    
    async def migrate_actor_records(self) -> int:
        """
        Migrate actor records: permissions list → frozenset.
        
        Returns:
            Number of entries migrated
        """
        prefix = ["users"]
        migrated = 0
        
        try:
            async for entry in self.kv.list(prefix):
                try:
                    data = entry.value
                    
                    # Convert permissions list to frozenset
                    if isinstance(data.get("permissions"), list):
                        data["permissions"] = self.converter.list_to_frozenset(
                            data["permissions"]
                        )
                        
                        # Convert actor_type if string
                        if isinstance(data.get("actor_type"), str):
                            data["actor_type"] = self.converter.string_to_actor_type(
                                data["actor_type"]
                            )
                        
                        # Convert role if string
                        if isinstance(data.get("role"), str):
                            data["role"] = self.converter.string_to_actor_role(
                                data["role"]
                            )
                        
                        # Update KV
                        await self.kv.set(entry.key, data)
                        migrated += 1
                        logger.debug(f"Migrated actor: {entry.key}")
                
                except Exception as e:
                    error_msg = f"Error migrating {entry.key}: {str(e)}"
                    logger.error(error_msg)
                    self.stats["errors"].append(error_msg)
        
        except Exception as e:
            logger.error(f"Actor migration failed: {str(e)}")
            self.stats["errors"].append(str(e))
        
        self.stats["actors_migrated"] = migrated
        return migrated
    
    async def migrate_outbox_entries(self) -> int:
        """
        Migrate outbox entries: list buttons → tuple buttons.
        
        Returns:
            Number of entries migrated
        """
        prefix = ["outbox"]
        migrated = 0
        
        try:
            async for entry in self.kv.list(prefix):
                try:
                    data = entry.value
                    
                    # Convert buttons list to tuple
                    if isinstance(data.get("buttons"), list):
                        data["buttons"] = self.converter.list_to_tuple(
                            data["buttons"]
                        )
                        
                        # Update KV
                        await self.kv.set(entry.key, data)
                        migrated += 1
                        logger.debug(f"Migrated outbox entry: {entry.key}")
                
                except Exception as e:
                    error_msg = f"Error migrating {entry.key}: {str(e)}"
                    logger.error(error_msg)
                    self.stats["errors"].append(error_msg)
        
        except Exception as e:
            logger.error(f"Outbox migration failed: {str(e)}")
            self.stats["errors"].append(str(e))
        
        self.stats["outbox_migrated"] = migrated
        return migrated
    
    async def run_full_migration(self) -> Dict[str, Any]:
        """
        Run complete migration across all data types.
        
        Returns:
            Migration statistics
        """
        logger.info("Starting full data migration...")
        
        await self.migrate_audit_entries()
        await self.migrate_actor_records()
        await self.migrate_outbox_entries()
        
        logger.info(f"Migration completed: {self.stats}")
        return self.stats


# ============================================================================
# VALIDATION
# ============================================================================

class MigrationValidator:
    """
    Validates that migration was successful and data integrity maintained.
    """
    
    def __init__(self, kv_client):
        self.kv = kv_client
        self.errors = []
    
    async def validate_audit_entries(self) -> bool:
        """
        Validate that all audit entries have enum resource_type.
        
        Returns:
            True if all valid
        """
        from src.architecture.event_types import ResourceType
        
        prefix = ["audit"]
        valid_types = {e.value for e in ResourceType}
        
        try:
            async for entry in self.kv.list(prefix):
                data = entry.value
                resource_type = data.get("resource_type")
                
                if isinstance(resource_type, str):
                    self.errors.append(
                        f"Audit {entry.key}: Still has string resource_type: {resource_type}"
                    )
                    return False
                
                if not isinstance(resource_type, ResourceType):
                    self.errors.append(
                        f"Audit {entry.key}: Invalid resource_type type: {type(resource_type)}"
                    )
                    return False
        
        except Exception as e:
            self.errors.append(f"Audit validation error: {str(e)}")
            return False
        
        logger.info("✅ Audit entries validated")
        return True
    
    async def validate_actor_records(self) -> bool:
        """
        Validate that all actor records have frozenset permissions.
        
        Returns:
            True if all valid
        """
        from src.architecture.event_types import ActorType, ActorRole
        
        prefix = ["users"]
        
        try:
            async for entry in self.kv.list(prefix):
                data = entry.value
                permissions = data.get("permissions")
                actor_type = data.get("actor_type")
                role = data.get("role")
                
                # Check permissions
                if permissions is not None and not isinstance(permissions, frozenset):
                    self.errors.append(
                        f"Actor {entry.key}: permissions not frozenset: {type(permissions)}"
                    )
                    return False
                
                # Check actor_type
                if isinstance(actor_type, str):
                    self.errors.append(
                        f"Actor {entry.key}: Still has string actor_type: {actor_type}"
                    )
                    return False
                
                # Check role
                if isinstance(role, str):
                    self.errors.append(
                        f"Actor {entry.key}: Still has string role: {role}"
                    )
                    return False
        
        except Exception as e:
            self.errors.append(f"Actor validation error: {str(e)}")
            return False
        
        logger.info("✅ Actor records validated")
        return True
    
    async def validate_outbox_entries(self) -> bool:
        """
        Validate that all outbox entries have tuple buttons.
        
        Returns:
            True if all valid
        """
        prefix = ["outbox"]
        
        try:
            async for entry in self.kv.list(prefix):
                data = entry.value
                buttons = data.get("buttons")
                
                if buttons is not None and not isinstance(buttons, tuple):
                    self.errors.append(
                        f"Outbox {entry.key}: buttons not tuple: {type(buttons)}"
                    )
                    return False
        
        except Exception as e:
            self.errors.append(f"Outbox validation error: {str(e)}")
            return False
        
        logger.info("✅ Outbox entries validated")
        return True
    
    async def run_full_validation(self) -> Tuple[bool, Dict[str, Any]]:
        """
        Run complete validation.
        
        Returns:
            (success: bool, report: dict)
        """
        logger.info("Starting migration validation...")
        
        results = {
            "audits_valid": await self.validate_audit_entries(),
            "actors_valid": await self.validate_actor_records(),
            "outbox_valid": await self.validate_outbox_entries(),
            "errors": self.errors,
        }
        
        success = all([
            results["audits_valid"],
            results["actors_valid"],
            results["outbox_valid"],
        ]) and len(self.errors) == 0
        
        logger.info(f"Validation complete: {results}")
        return success, results


# ============================================================================
# ROLLBACK
# ============================================================================

class MigrationRollback:
    """
    Allows rollback to previous state if migration fails.
    """
    
    def __init__(self, kv_client, backup_prefix: str = "migration_backup"):
        self.kv = kv_client
        self.backup_prefix = backup_prefix
    
    async def backup_before_migration(self, prefixes: List[str]) -> bool:
        """
        Create backup of data before migration.
        
        Args:
            prefixes: KV prefixes to backup (e.g., ["audit", "users", "outbox"])
        
        Returns:
            True if successful
        """
        logger.info(f"Creating backup for prefixes: {prefixes}")
        
        for prefix in prefixes:
            try:
                async for entry in self.kv.list(prefix):
                    backup_key = [self.backup_prefix] + entry.key
                    await self.kv.set(backup_key, entry.value)
                    logger.debug(f"Backed up: {entry.key}")
            
            except Exception as e:
                logger.error(f"Backup failed for {prefix}: {str(e)}")
                return False
        
        logger.info("✅ Backup created successfully")
        return True
    
    async def rollback_from_backup(self, prefixes: List[str]) -> bool:
        """
        Restore data from backup.
        
        Args:
            prefixes: KV prefixes to restore
        
        Returns:
            True if successful
        """
        logger.info(f"Rolling back prefixes: {prefixes}")
        
        for prefix in prefixes:
            try:
                # Delete current data
                async for entry in self.kv.list(prefix):
                    await self.kv.delete(entry.key)
                
                # Restore from backup
                backup_prefix = [self.backup_prefix] + prefix
                async for entry in self.kv.list(backup_prefix):
                    # Extract original key by removing backup prefix
                    original_key = entry.key[1:]  # Remove first element (backup prefix)
                    await self.kv.set(original_key, entry.value)
                    logger.debug(f"Restored: {original_key}")
            
            except Exception as e:
                logger.error(f"Rollback failed for {prefix}: {str(e)}")
                return False
        
        logger.info("✅ Rollback completed successfully")
        return True


# ============================================================================
# MIGRATION JOB
# ============================================================================

class MigrationJob:
    """
    Orchestrates complete migration process with validation and rollback.
    """
    
    def __init__(self, kv_client):
        self.kv = kv_client
        self.cache_service = RawObjectCacheService(kv_client)
        self.migrator = DataMigrator(kv_client, self.cache_service)
        self.validator = MigrationValidator(kv_client)
        self.rollback = MigrationRollback(kv_client)
    
    async def execute(self, dry_run: bool = False) -> Dict[str, Any]:
        """
        Execute complete migration.
        
        Args:
            dry_run: If True, validate only without modifying data
        
        Returns:
            Migration report
        """
        logger.info(f"Starting migration job (dry_run={dry_run})")
        
        report = {
            "timestamp": datetime.now().isoformat(),
            "dry_run": dry_run,
            "migration_stats": None,
            "validation_result": None,
            "errors": [],
        }
        
        # Step 1: Backup
        prefixes_to_migrate = ["audit", "users", "outbox"]
        if not await self.rollback.backup_before_migration(prefixes_to_migrate):
            report["errors"].append("Backup failed")
            logger.error("❌ Migration aborted: backup failed")
            return report
        
        # Step 2: Migrate (skip if dry run)
        if not dry_run:
            try:
                report["migration_stats"] = await self.migrator.run_full_migration()
            except Exception as e:
                report["errors"].append(f"Migration failed: {str(e)}")
                logger.error(f"❌ Migration failed: {str(e)}")
                await self.rollback.rollback_from_backup(prefixes_to_migrate)
                return report
        
        # Step 3: Validate
        try:
            success, validation_report = await self.validator.run_full_validation()
            report["validation_result"] = validation_report
            
            if not success:
                report["errors"].append("Validation failed")
                logger.error("❌ Validation failed")
                if not dry_run:
                    await self.rollback.rollback_from_backup(prefixes_to_migrate)
                return report
        
        except Exception as e:
            report["errors"].append(f"Validation error: {str(e)}")
            logger.error(f"❌ Validation error: {str(e)}")
            if not dry_run:
                await self.rollback.rollback_from_backup(prefixes_to_migrate)
            return report
        
        logger.info("✅ Migration completed successfully")
        report["status"] = "success"
        return report
