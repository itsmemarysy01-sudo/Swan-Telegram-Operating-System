"""
Step-by-step migration instructions for event_types.py optimization.

Execute these steps in order to safely migrate your system.
"""

from typing import Dict, Any, List
import logging
from datetime import datetime

logger = logging.getLogger(__name__)


class MigrationInstructions:
    """
    Step-by-step migration guide with code examples.
    """
    
    @staticmethod
    def phase_1_setup_cache():
        """
        PHASE 1: Setup Raw Object Cache
        
        This phase creates the infrastructure to cache raw Telegram objects
        instead of storing them inline.
        """
        print("""
╔════════════════════════════════════════════════════════════════════════════╗
║                   PHASE 1: SETUP RAW OBJECT CACHE                          ║
╚════════════════════════════════════════════════════════════════════════════╝

OBJECTIVE:
  Create cache infrastructure for raw Telegram objects

STEPS:

1. Create cache service file:
   - File: src/services/cache_service.py
   - Implement: RawObjectCacheService class
   - Features:
     ✓ cache_raw_object(raw: Dict) -> str
     ✓ retrieve_raw_object(raw_id: str) -> Dict
     ✓ cleanup_expired_cache() job

2. Add cache initialization:
   - In main.py or startup.py:
     cache_service = RawObjectCacheService(kv_client, ttl_seconds=3600)
   - Wire into dependency injection

3. Schedule cleanup job:
   - Run cleanup every 30 minutes
   - Or run on-demand before critical operations

4. Test cache operations:
   - Unit tests: test_cache_service.py
   - Integration tests: test_cache_integration.py

EXPECTED OUTCOME:
  ✓ Cache service running
  ✓ Raw objects stored with TTL
  ✓ Cleanup job scheduled
        """)
    
    @staticmethod
    def phase_2_update_model_creation():
        """
        PHASE 2: Update Model Creation Code
        
        Update all code that creates CanonicalEvent instances to use raw_id.
        """
        print("""
╔════════════════════════════════════════════════════════════════════════════╗
║               PHASE 2: UPDATE MODEL CREATION CODE                          ║
╚════════════════════════════════════════════════════════════════════════════╝

OBJECTIVE:
  Update all code that creates CanonicalEvent instances

BEFORE (OLD):
  event = CanonicalEvent(
      event_id="abc123",
      event_type="message",
      platform="telegram",
      user_id=123,
      chat_id=456,
      timestamp=1234567890,
      text="Hello",
      raw={"update_id": 123, "message": {...}}  # ❌ Large dict stored inline
  )

AFTER (NEW):
  # 1. Cache the raw object
  raw_id = await cache_service.cache_raw_object({
      "update_id": 123,
      "message": {...}
  })
  
  # 2. Create event with raw_id reference
  event = CanonicalEvent(
      event_id="abc123",
      event_type="message",
      platform="telegram",
      user_id=123,
      chat_id=456,
      timestamp=1234567890,
      text="Hello",
      raw_id=raw_id  # ✓ Small string reference
  )

STEPS:

1. Find all CanonicalEvent creation sites:
   grep -r "CanonicalEvent(" src/
   grep -r "MessageEvent(" src/
   grep -r "CallbackQueryEvent(" src/

2. For each site, add cache.cache_raw_object() call:
   - Extract raw dict from parameters
   - Call cache_service.cache_raw_object(raw)
   - Pass raw_id instead

3. Update factory functions:
   - Look for normalize_telegram_update()
   - Look for parse_webhook_update()
   - Update to use raw_id pattern

4. Add tests for each conversion:
   test_canonical_event_creation.py
   test_message_event_creation.py

EXAMPLE FILE CHANGES:

File: src/normalization/telegram_normalizer.py

  BEFORE:
    def normalize_telegram_update(update: Dict) -> CanonicalEvent:
        return CanonicalEvent(
            event_id=str(update["update_id"]),
            raw=update,  # ❌ Stores entire update
            ...
        )

  AFTER:
    async def normalize_telegram_update(
        update: Dict,
        cache_service
    ) -> CanonicalEvent:
        raw_id = await cache_service.cache_raw_object(update)
        return CanonicalEvent(
            event_id=str(update["update_id"]),
            raw_id=raw_id,  # ✓ Stores reference
            ...
        )

EXPECTED OUTCOME:
  ✓ All CanonicalEvent creations use raw_id
  ✓ Tests passing for new pattern
  ✓ No inline raw objects
        """)
    
    @staticmethod
    def phase_3_update_raw_access():
        """
        PHASE 3: Update Raw Object Access
        
        Replace all direct event.raw accesses with cache lookups.
        """
        print("""
╔════════════════════════════════════════════════════════════════════════════╗
║              PHASE 3: UPDATE RAW OBJECT ACCESS                             ║
╚════════════════════════════════════════════════════════════════════════════╝

OBJECTIVE:
  Replace event.raw direct access with cache-based retrieval

BEFORE (OLD):
  def process_event(event: CanonicalEvent):
      raw_data = event.raw  # ❌ Direct access to large dict
      update_id = raw_data["update_id"]
      message = raw_data["message"]
      ...

AFTER (NEW):
  async def process_event(
      event: CanonicalEvent,
      cache_service
  ):
      raw_data = await cache_service.retrieve_raw_object(event.raw_id)
      if not raw_data:
          logger.error(f"Raw object not in cache: {event.raw_id}")
          return
      
      update_id = raw_data["update_id"]
      message = raw_data["message"]
      ...

STEPS:

1. Find all event.raw accesses:
   grep -r "event\.raw" src/
   grep -rn "\.raw\[" src/
   grep -rn "\.raw\.get" src/

2. Replace with cache lookups:
   - event.raw → await cache_service.retrieve_raw_object(event.raw_id)
   - Add null check for cache misses
   - Add error logging

3. Update function signatures:
   - Add cache_service parameter
   - Make functions async if not already

4. Handle cache misses gracefully:
   - Log warning/error
   - Fallback behavior (skip, retry, etc.)

EXAMPLE FILE CHANGES:

File: src/handlers/event_handler.py

  BEFORE:
    def handle_message_event(event: MessageEvent):
        original_update = event.raw
        bot_data = original_update.get("message", {}).get("bot", {})
        ...

  AFTER:
    async def handle_message_event(
        event: MessageEvent,
        cache_service: RawObjectCacheService
    ):
        original_update = await cache_service.retrieve_raw_object(event.raw_id)
        if not original_update:
            logger.error(f"Failed to retrieve raw: {event.raw_id}")
            return None
        
        bot_data = original_update.get("message", {}).get("bot", {})
        ...

TESTING:
  - Test with cache hits
  - Test with cache misses
  - Test with expired cache entries

EXPECTED OUTCOME:
  ✓ No direct event.raw access
  ✓ All accesses use cache_service.retrieve_raw_object()
  ✓ Error handling for cache misses
        """)
    
    @staticmethod
    def phase_4_convert_collections():
        """
        PHASE 4: Convert Collections to Tuples
        
        Replace list operations with tuple-safe code.
        """
        print("""
╔════════════════════════════════════════════════════════════════════════════╗
║             PHASE 4: CONVERT COLLECTIONS TO TUPLES                         ║
╚════════════════════════════════════════════════════════════════════════════╝

OBJECTIVE:
  Replace list operations with immutable tuples

COLLECTIONS AFFECTED:
  - ExecutionPlan.state_mutations: list → tuple
  - ExecutionPlan.outbox_entries: list → tuple
  - ExecutionPlan.queue_items: list → tuple
  - OutboxEntry.buttons: list → tuple
  - StateMutation.key: list → tuple
  - PollAnswerEvent.options: list → tuple
  - Actor.permissions: list → frozenset

STEPS:

1. Find list assignments:
   grep -rn "state_mutations = \[" src/
   grep -rn "outbox_entries = \[" src/
   grep -rn "buttons = \[" src/
   grep -rn "options = \[" src/

2. Convert to tuples during creation:
   - mutations = [mutation1, mutation2]  # ❌ OLD
   + mutations = tuple([mutation1, mutation2])  # ✓ NEW
   + OR: mutations = (mutation1, mutation2)  # ✓ CLEANER

3. Remove list mutations:
   - ❌ mutations.append(new_mutation)
   - ❌ mutations.extend([m1, m2])
   - ❌ mutations.pop(0)
   + ✓ Build list, convert to tuple

4. Update tests:
   - Test tuple immutability
   - Test tuple indexing
   - Test tuple iteration

EXAMPLE FILE CHANGES:

File: src/planning/execution_planner.py

  BEFORE:
    def create_execution_plan(intent: Intent) -> ExecutionPlan:
        mutations = []
        mutations.append(StateMutation(...))
        mutations.append(StateMutation(...))
        
        outbox = []
        outbox.append(OutboxEntry(...))
        
        return ExecutionPlan(
            state_mutations=mutations,  # ❌ Lists
            outbox_entries=outbox,
            ...
        )

  AFTER:
    def create_execution_plan(intent: Intent) -> ExecutionPlan:
        mutations = [
            StateMutation(...),
            StateMutation(...),
        ]
        
        outbox = [
            OutboxEntry(...),
        ]
        
        return ExecutionPlan(
            state_mutations=tuple(mutations),  # ✓ Tuples
            outbox_entries=tuple(outbox),
            ...
        )

File: src/models/poll.py

  BEFORE:
    poll_event = PollAnswerEvent(
        poll_id="poll123",
        options=[1, 2, 3],  # ❌ List
        ...
    )

  AFTER:
    poll_event = PollAnswerEvent(
        poll_id="poll123",
        options=(1, 2, 3),  # ✓ Tuple
        ...
    )
    
    # OR use option_set property for membership testing
    if 2 in poll_event.option_set:  # O(1) lookup
        ...

PERMISSIONS CONVERSION (frozenset):

  BEFORE:
    actor = Actor(
        actor_id=123,
        permissions=["read", "write"]  # ❌ List
    )

  AFTER:
    actor = Actor(
        actor_id=123,
        permissions=frozenset(["read", "write"])  # ✓ Frozenset
    )
    
    # Automatic conversion via Actor.model_validate()
    actor = Actor.model_validate({
        "actor_id": 123,
        "permissions": ["read", "write"]  # ✓ Auto-converted to frozenset
    })

EXPECTED OUTCOME:
  ✓ All collections use immutable types
  ✓ No list mutations
  ✓ Tests passing with tuples/frozensets
        """)
    
    @staticmethod
    def phase_5_convert_enums():
        """
        PHASE 5: Convert String Enums
        
        Replace string literals with enum values.
        """
        print("""
╔════════════════════════════════════════════════════════════════════════════╗
║              PHASE 5: CONVERT STRING ENUMS                                 ║
╚════════════════════════════════════════════════════════════════════════════╝

OBJECTIVE:
  Replace string resource types, actor types, and roles with enums

NEW ENUMS:
  - ResourceType: POST, TICKET, MEMBER, BROADCAST
  - ActorType: USER, BOT, GROUP, CHANNEL
  - ActorRole: OWNER, EDITOR, MEMBER, GUEST

STEPS:

1. Find string assignments:
   grep -rn '"post"\\|"ticket"\\|"member"\\|"broadcast"' src/
   grep -rn "'post'\\|'ticket'\\|'member'\\|'broadcast'" src/
   grep -rn '"user"\\|"bot"\\|"group"\\|"channel"' src/
   grep -rn '"OWNER"\\|"EDITOR"' src/

2. Replace with enum imports and values:
   from src.architecture.event_types import (
       ResourceType, ActorType, ActorRole
   )

3. Update assignments:
   - resource_type="post"  → resource_type=ResourceType.POST
   - actor_type="user"     → actor_type=ActorType.USER
   - role="OWNER"          → role=ActorRole.OWNER

4. Update comparisons:
   - if resource_type == "post"  → if resource_type == ResourceType.POST
   - if actor_type == "user"     → if actor_type == ActorType.USER

EXAMPLE FILE CHANGES:

File: src/audit/audit_logger.py

  BEFORE:
    audit = AuditEntry(
        audit_id="audit123",
        resource_type="post",  # ❌ String
        action="publish",
        ...
    )

  AFTER:
    from src.architecture.event_types import ResourceType
    
    audit = AuditEntry(
        audit_id="audit123",
        resource_type=ResourceType.POST,  # ✓ Enum
        action="publish",
        ...
    )

File: src/permissions/rbac.py

  BEFORE:
    actor = Actor(
        actor_id=123,
        actor_type="user",  # ❌ String
        role="OWNER",       # ❌ String
        permissions=["read"]
    )

  AFTER:
    from src.architecture.event_types import ActorType, ActorRole
    
    actor = Actor(
        actor_id=123,
        actor_type=ActorType.USER,  # ✓ Enum
        role=ActorRole.OWNER,       # ✓ Enum
        permissions=["read"]
    )

File: src/handlers/resource_handler.py

  BEFORE:
    def handle_resource(audit: AuditEntry):
        if audit.resource_type == "post":
            process_post()
        elif audit.resource_type == "ticket":
            process_ticket()

  AFTER:
    from src.architecture.event_types import ResourceType
    
    def handle_resource(audit: AuditEntry):
        if audit.resource_type == ResourceType.POST:
            process_post()
        elif audit.resource_type == ResourceType.TICKET:
            process_ticket()

TESTING:
  - Test enum creation
  - Test enum comparisons
  - Test enum serialization/deserialization

EXPECTED OUTCOME:
  ✓ All string resource types replaced with ResourceType enum
  ✓ All string actor types replaced with ActorType enum
  ✓ All string roles replaced with ActorRole enum
  ✓ Better type safety and IDE support
        """)
    
    @staticmethod
    def phase_6_migrate_data():
        """
        PHASE 6: Migrate Stored Data
        
        Run migration job to convert existing KV data.
        """
        print("""
╔════════════════════════════════════════════════════════════════════════════╗
║               PHASE 6: MIGRATE STORED DATA                                 ║
╚════════════════════════════════════════════════════════════════════════════╝

OBJECTIVE:
  Migrate existing KV data from old format to new format

PREREQUISITES:
  ✓ Phases 1-5 completed
  ✓ All code updated to use new types
  ✓ Tests passing locally

BEFORE MIGRATION:
  1. Create backup of entire KV
  2. Run validation (dry_run=True)
  3. Verify no issues

MIGRATION STEPS:

1. Create migration script:
   File: src/scripts/run_migration.py
   
   async def main():
       kv = kv_client()
       job = MigrationJob(kv)
       
       # Test run first
       result = await job.execute(dry_run=True)
       if result["errors"]:
           print(f"Dry run failed: {result['errors']}")
           return
       
       # If dry run passes, run actual migration
       result = await job.execute(dry_run=False)
       return result

2. Run dry run migration:
   python src/scripts/run_migration.py --dry-run
   
   Expected output:
   ✓ All audit entries have enum resource_type
   ✓ All actor records have frozenset permissions
   ✓ All outbox entries have tuple buttons

3. If dry run passes, run actual migration:
   python src/scripts/run_migration.py
   
   This will:
   - Backup all data
   - Convert audit entries
   - Convert actor records
   - Convert outbox entries
   - Validate results
   - Report statistics

4. Monitor migration:
   - Check logs for errors
   - Verify conversion stats match expectations
   - Monitor KV usage before/after

5. Post-migration validation:
   - Run full validation suite
   - Test critical paths
   - Verify cache operations
   - Check performance metrics

ROLLBACK PROCEDURE:
If migration fails:
   python src/scripts/rollback_migration.py
   
   This will:
   - Restore from backup
   - Verify restoration
   - Report status

MIGRATION CODE TEMPLATE:

  from src.migration.migration_service import MigrationJob
  
  async def run_migration():
      # Initialize
      job = MigrationJob(kv_client)
      
      # Test first
      print("Running dry-run validation...")
      result = await job.execute(dry_run=True)
      
      if result["errors"]:
          print(f"❌ Dry run failed:")
          for error in result["errors"]:
              print(f"  - {error}")
          return False
      
      print("✓ Dry run passed")
      print(result["validation_result"])
      
      # Run actual migration
      print("\\nRunning actual migration...")
      result = await job.execute(dry_run=False)
      
      if result["errors"]:
          print(f"❌ Migration failed:")
          for error in result["errors"]:
              print(f"  - {error}")
          return False
      
      print("✅ Migration completed successfully")
      print(result["migration_stats"])
      return True

EXPECTED OUTCOME:
  ✓ All existing data converted
  ✓ No data loss
  ✓ Zero downtime (backup/restore available)
  ✓ Full validation passing
        """)
    
    @staticmethod
    def phase_7_testing():
        """
        PHASE 7: Update Tests & Validation
        
        Ensure all tests pass with new types.
        """
        print("""
╔════════════════════════════════════════════════════════════════════════════╗
║            PHASE 7: UPDATE TESTS & VALIDATION                              ║
╚════════════════════════════════════════════════════════════════════════════╝

OBJECTIVE:
  Ensure all tests pass with new model types

TEST CATEGORIES:

1. UNIT TESTS - Model Creation & Conversion
   File: tests/test_event_types_migration.py
   
   - Test CanonicalEvent with raw_id
   - Test PollAnswerEvent with tuple options
   - Test ExecutionPlan with tuple mutations
   - Test Actor with frozenset permissions
   - Test enum conversions

2. INTEGRATION TESTS - End-to-End Flow
   File: tests/test_migration_integration.py
   
   - Test event creation → caching → access
   - Test cache miss handling
   - Test TTL expiration
   - Test data conversion pipeline

3. CACHE TESTS - Cache Service
   File: tests/test_cache_service.py
   
   - Test cache_raw_object()
   - Test retrieve_raw_object()
   - Test cache TTL
   - Test cleanup job

4. MIGRATION TESTS - Data Migration
   File: tests/test_data_migration.py
   
   - Test audit entry migration
   - Test actor record migration
   - Test outbox entry migration
   - Test validation
   - Test rollback

5. BACKWARD COMPATIBILITY TESTS
   File: tests/test_compatibility.py
   
   - Test old format → new format conversion
   - Test graceful handling of mixed formats
   - Test error cases

TEST EXECUTION:

1. Run unit tests:
   pytest tests/test_event_types_migration.py -v

2. Run integration tests:
   pytest tests/test_migration_integration.py -v

3. Run cache tests:
   pytest tests/test_cache_service.py -v

4. Run migration tests:
   pytest tests/test_data_migration.py -v

5. Run all tests:
   pytest tests/ -k migration -v

6. Run with coverage:
   pytest tests/ -k migration --cov=src --cov-report=html

EXAMPLE TEST:

  import pytest
  from src.architecture.event_types import (
      CanonicalEvent, PollAnswerEvent, ResourceType, ActorType, ActorRole
  )
  from src.migration.migration_service import ModelConverter
  
  @pytest.mark.asyncio
  async def test_canonical_event_raw_id():
      # Create event with raw_id instead of raw
      event = CanonicalEvent(
          event_id="test123",
          event_type="message",
          platform="telegram",
          chat_id=456,
          timestamp=1234567890,
          raw_id="cache_ref_123"
      )
      
      assert event.raw_id == "cache_ref_123"
      assert event.text is None
  
  def test_poll_event_tuple_options():
      # Options should be tuple
      event = PollAnswerEvent(
          event_id="poll123",
          poll_id="p1",
          options=(1, 2, 3),
          chat_id=456,
          timestamp=1234567890
      )
      
      assert isinstance(event.options, tuple)
      assert event.options == (1, 2, 3)
      assert 2 in event.option_set
  
  def test_enum_conversions():
      # Test enum conversions
      converter = ModelConverter()
      
      assert converter.string_to_resource_type("post") == ResourceType.POST
      assert converter.string_to_actor_type("user") == ActorType.USER
      assert converter.string_to_actor_role("OWNER") == ActorRole.OWNER

CRITICAL PATH TESTS:
  ✓ Event ingestion & normalization
  ✓ Permission validation
  ✓ Execution plan creation
  ✓ KV commit operations
  ✓ Audit logging
  ✓ Outbox delivery

EXPECTED OUTCOME:
  ✓ All tests passing
  ✓ 100% coverage on migration code
  ✓ Performance tests validating improvements
  ✓ Load tests validating memory savings
        """)
    
    @staticmethod
    def print_summary():
        """Print complete migration summary."""
        print("""
╔════════════════════════════════════════════════════════════════════════════╗
║         EVENT TYPES OPTIMIZATION MIGRATION - COMPLETE GUIDE                ║
╚════════════════════════════════════════════════════════════════════════════╝

TIMELINE:
  Phase 1: Setup Cache              (1-2 days)
  Phase 2: Update Creation Code     (2-3 days)
  Phase 3: Update Access Code       (2-3 days)
  Phase 4: Convert Collections      (1-2 days)
  Phase 5: Convert Enums            (1-2 days)
  Phase 6: Migrate Data             (1 day + validation)
  Phase 7: Testing & Validation     (2-3 days)
  
  TOTAL: 10-18 days

KEY BENEFITS AFTER MIGRATION:
  ✓ 40-60% reduction in memory per event
  ✓ Faster tuple operations vs lists
  ✓ O(1) permission lookups with frozensets
  ✓ Type-safe enums instead of strings
  ✓ Better IDE/type-checker support

ROLLBACK CAPABILITY:
  ✓ Full backup before each phase
  ✓ Automatic rollback on validation failure
  ✓ Manual rollback available anytime
  ✓ Zero data loss

MONITORING DURING MIGRATION:
  - Cache hit/miss rates
  - Memory usage before/after
  - Conversion stats
  - Error rates
  - Performance metrics

NEXT STEPS:
  1. Review this guide
  2. Prepare infrastructure (Phase 1)
  3. Execute phases sequentially
  4. Monitor and validate after each phase
  5. Run full test suite before production
  6. Deploy to production
  7. Monitor post-deployment

SUPPORT:
  - Keep backup of original data
  - Have rollback procedure ready
  - Monitor logs closely
  - Test in staging first
        """)


# Run guide
if __name__ == "__main__":
    guide = MigrationInstructions()
    guide.phase_1_setup_cache()
    guide.phase_2_update_model_creation()
    guide.phase_3_update_raw_access()
    guide.phase_4_convert_collections()
    guide.phase_5_convert_enums()
    guide.phase_6_migrate_data()
    guide.phase_7_testing()
    guide.print_summary()
