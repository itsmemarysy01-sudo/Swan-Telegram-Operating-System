# STOS V2.3.2 — Architecture Layer

**IMMUTABLE SYSTEM SPECIFICATION**

This document defines the architectural constraints that all STOS implementations must satisfy. These rules are fundamental to how STOS operates and **change only with major version releases** (e.g., v2.3.2 → v3.0.0).

---

## Three-Layer Architecture (Fixed)

```
┌─────────────────────────────────────────────────────────────┐
│              POLICY LAYER (Deployment-Specific)              │
│  • Content policies                                          │
│  • Moderation rules                                          │
│  • Permission frameworks                                     │
│  • Approval workflows                                        │
│  • Community rules                                           │
│  • Entitlements & quotas                                     │
│  ⬆️  CAN CHANGE without touching architecture                │
└──────────────────────────┬──────────────────────────────────┘
                           │
┌──────────────────────────▼──────────────────────────────────┐
│         INTERNAL MODULES (Layer 1 — Intent Only)             │
│                                                              │
│  • Content Engine       — Manage posts, drafts, media        │
│  • Button Engine       — Render inline keyboards            │
│  • Automation Engine   — Schedule, broadcast, reminders      │
│  • Community Engine    — Members, polls, topics             │
│  • Customer Service    — FAQ, guides, tickets               │
│  • Delivery Engine     — Dispatch to channels/groups/users  │
│                                                              │
│  ✅ MUST: Generate intent only                              │
│  ❌ MUST NOT: Mutate state, call Telegram, call each other  │
└─────────────────────────────────────────────────────────────┘
                           │
┌──────────────────────────▼──────────────────────────────────┐
│   RUNTIME SERVICES (Layer 2 — 13-Step Pipeline)             │
│                                                              │
│  Step  1  Event Ingestion          (normalize)              │
│  Step  2  Identity Resolution      (who is actor?)          │
│  Step  3  Permission Validation    (allowed?) 🔵 POLICY    │
│  Step  4  Route Resolution         (which handler?)         │
│  Step  5  Execution Planning       (what mutations?)         │
│  Step  6  FSM Processing           (next state?) 🔵 POLICY  │
│  Step  7  KV Atomic Commit         (write all-or-nothing)   │
│  Step  8  Outbox Management        (stage messages)         │
│  Step  9  Queue Processing         (retry, dedupe)          │
│  Step 10  Delivery Coordination    (send to Telegram)       │
│  Step 11  Audit Recording          (log immutably)          │
│  Step 12  Idempotency Control      (prevent duplicates)     │
│  Step 13  Lock Management          (prevent concurrency)    │
│                                                              │
│  ✅ MUST: Execute in fixed sequential order                 │
│  ✅ MUST: Only layer authorized to mutate state             │
│  ❌ MUST NOT: Skip steps, reorder steps, or branch logic    │
└─────────────────────────────────────────────────────────────┘
                           │
┌──────────────────────────▼──────────────────────────────────┐
│     EXTERNAL TOOLS (Layer 3 — Effects Only)                 │
│                                                              │
│  • Telegram Bot API      (send messages, edit, delete)      │
│  • Deno Runtime          (execute code)                     │
│  • Deno KV               (persistent key-value storage)     │
│  • Deno KV Queue         (durable message queue)            │
│  • HTTPS Webhook         (receive Telegram updates)         │
│                                                              │
│  ✅ MUST: Execute effects only                              │
│  ❌ MUST NOT: Mutate STOS state directly                    │
└─────────────────────────────────────────────────────────────┘
```

---

## Invariants (Never Violate)

| # | Invariant | Enforced By | Check |
|---|-----------|-------------|-------|
| INV-01 | All mutations commit atomically | Layer 2, Step 7 | Single transaction for state + audit + aggregates + outbox + queue |
| INV-02 | Internal Modules never mutate state | Design (Layer 1 isolation) | Code review: no KV calls in Layer 1 |
| INV-03 | Only Runtime Services mutate state | Design (Layer 2 monopoly) | Code review: KV calls only in Layer 2 Step 7 |
| INV-04 | Outbox entries in atomic commit | Layer 2, Step 7 | Outbox written same transaction as state |
| INV-05 | Idempotency check before execution | Layer 2, Step 12 | Early return if update_id already processed |
| INV-06 | Lock acquired before FSM | Layer 2, Step 6 | Acquire lock at Step 6 start |
| INV-07 | Audit entries immutable | Storage (KV key structure) | Audit keys write-once, no updates |
| INV-08 | Exactly one owner | Schema | `storage/owner/*` singleton structure |
| INV-09 | Webhook returns 200 to Telegram | Code (finally block) | HTTP 200 in all code paths |
| INV-10 | Secret token validated first | HTTPS middleware | Validation before routing |
| INV-11 | Modules don't share state or call each other | Design | Layer 1 isolation |
| INV-12 | Pipeline steps execute in fixed order | Code (sequential executor) | No branching in step order |
| INV-13 | Telegram is output surface only | Design (Layer 3 isolation) | No FSM decisions based on Telegram events |

---

## Data Model (Fixed)

All persistent state lives in Deno KV with hierarchical key prefixes:

```
storage/
├── system/              # Global config (system-level)
├── owner/               # Owner credentials & control panel
├── users/               # User metadata, states
├── groups/              # Group records
├── channels/            # Channel records
├── posts/
│   ├── drafts/          # Unpublished
│   ├── scheduled/       # Future-dated
│   ├── published/       # Live
│   └── archived/        # Soft-deleted
├── community/           # Join requests, member logs
├── tickets/             # Support tickets
├── polls/               # Poll definitions
├── topics/              # Forum topics
├── broadcasts/          # Mass send jobs
├── reminders/           # User alerts
├── scheduler/           # Timetable indices
├── audit/               # Immutable logs
├── aggregates/          # Counters & metrics
├── outbox/              # Staged messages
├── queue/               # Delivery work items
├── locks/               # Concurrency locks
└── idempotency/         # Processed update IDs
```

---

## Event Types (Fixed)

```python
# All events normalized to this canonical form
class CanonicalEvent(BaseModel):
    event: Literal["message", "callback", "join_request"]
    platform: Literal["telegram"]
    chat_id: int
    user_id: Optional[int]
    username: Optional[str]
    timestamp: int
    text: Optional[str]
    raw: Dict[str, Any]  # Original Telegram object
```

---

## Atomic Commit Structure (Fixed)

Every pipeline execution commits exactly **five outputs atomically**:

```python
class AtomicCommit(BaseModel):
    """All-or-nothing transaction."""
    
    state_mutations: Dict[str, Any]      # New FSM positions
    audit_entry: AuditEntry             # Operation log
    aggregate_updates: Dict[str, int]    # Counters
    outbox_entries: List[OutboxEntry]   # Staged messages
    queue_items: List[QueueItem]         # Delivery tasks
```

If any write fails → **all writes aborted**. No partial commits.

---

## FSM State Machine (Fixed Structure)

All state machines follow this pattern:

```python
{
    "DRAFT": {
        "PREVIEW": "PREVIEW",
        "PUBLISH": "PUBLISHED",  # May become PENDING_APPROVAL (policy)
        "DELETE": "ARCHIVED",
    },
    "PREVIEW": {
        "PUBLISH": "PUBLISHED",
        "SAVE_DRAFT": "DRAFT",
    },
    "PUBLISHED": {
        "UPDATE": "PREVIEW",
        "ARCHIVE": "ARCHIVED",
    },
    "ARCHIVED": {},  # Terminal state
}
```

**Policy May Influence:** Destination state (e.g., "PUBLISHED" → "PENDING_APPROVAL")  
**Policy Cannot Change:** Available transitions or state names

---

## Security Boundaries (Fixed)

```
┌─────────────────────────────────────────────────────────┐
│  HTTPS Webhook (TLS encryption)                         │
│  ↓                                                      │
│  Secret Token Validation (Step 10, Layer 2)            │
│  ├─ X-Telegram-Bot-Api-Secret-Token header match       │
│  └─ 403 Forbidden if invalid → stop processing         │
│  ↓                                                      │
│  Identity Resolution (Step 2, Layer 2)                 │
│  ├─ Extract user_id and chat_id from event            │
│  └─ Resolve ownership (is this the owner?)            │
│  ↓                                                      │
│  Permission Validation (Step 3, Layer 2)               │
│  ├─ Check RBAC role (OWNER / MEMBER / GUEST)          │
│  ├─ Check resource access (can edit this post?)       │
│  └─ 403 if denied → log audit, exit pipeline          │
│  ↓                                                      │
│  KV Namespace Isolation (Step 7, Layer 2)             │
│  ├─ `system/*` and `owner/*` owner-only              │
│  ├─ `users/123/*` user 123 only                       │
│  └─ Enforced by key prefix, not if-checks            │
│  ↓                                                      │
│  Audit Trail (Step 11, Layer 2)                        │
│  └─ All mutations recorded immutably                   │
└─────────────────────────────────────────────────────────┘
```

---

## Deployment Topology (Fixed)

```
GitHub Repository (source code)
  ↓
Deno Deploy (build & serve)
  ↓
HTTPS Webhook (receive updates)
  ↓
Runtime Pipeline (13 steps)
  ├─ Layer 1: Intent generators
  ├─ Layer 2: State mutations
  └─ Layer 3: Telegram delivery
  ↓
Deno KV (atomic storage)
  ↓
Telegram Bot API (send messages)
  ↓
📢 Channels  👥 Groups  👤 Users
```

---

## What CANNOT Change Without Major Version Bump

❌ Number of layers  
❌ 13-step pipeline order  
❌ Atomic commit structure  
❌ KV namespace hierarchy  
❌ FSM state machine pattern  
❌ Security boundary positions  
❌ Invariants  

---

## What CAN Change (Policy Layer)

✅ Content restrictions  
✅ Permission rules  
✅ Moderation policies  
✅ Approval workflows  
✅ Quotas & rate limits  
✅ Community rules  
✅ Entitlements  

See `POLICY.md` for all Policy Layer specifications.

---

## Version History

- **v2.3.2** (current) — Three-layer architecture, 13-step pipeline, atomic commits
- **v3.0.0** (future) — Any architectural changes

