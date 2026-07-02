# STOS V2.3.2 — Domain Model Layer

**BUSINESS ENTITY SPECIFICATIONS**

This document defines the domain entities (Draft, Ticket, Member, Poll, etc.) with their complete Finite State Machine (FSM) transitions, invariants, and data contracts. These entities are referenced by the ExecutionPlan during Layer 2 processing.

---

## Entity Hierarchy

```
┌────────────────────────────────────────────────────────────┐
│                    DOMAIN ENTITIES                         │
│                                                            │
│  ├─ Content Entities                                      │
│  │  ├─ Draft          (unpublished post)                  │
│  │  ├─ Post           (published content)                 │
│  │  ├─ Media          (images, videos, documents)         │
│  │  └─ Button         (inline keyboard button)            │
│  │                                                        │
│  ├─ Community Entities                                    │
│  │  ├─ Member         (user in group/channel)            │
│  │  ├─ Poll           (voting mechanism)                 │
│  │  ├─ Topic          (forum thread)                     │
│  │  └─ JoinRequest    (pending membership)              │
│  │                                                        │
│  ├─ Support Entities                                      │
│  │  ├─ Ticket         (customer support request)         │
│  │  ├─ FAQ            (frequently asked question)        │
│  │  └─ Guide          (documentation)                    │
│  │                                                        │
│  ├─ Delivery Entities                                     │
│  │  ├─ Broadcast      (mass send job)                    │
│  │  ├─ Reminder       (scheduled alert)                  │
│  │  └─ QueueItem      (delivery work)                    │
│  │                                                        │
│  └─ System Entities                                       │
│     ├─ Owner          (system owner)                     │
│     ├─ User           (Telegram user)                    │
│     ├─ Channel        (Telegram channel)                 │
│     └─ Group          (Telegram group)                   │
└────────────────────────────────────────────────────────────┘
```

---

## 1. Content Entities

### 1.1 Draft

**Storage Location:** `storage/posts/drafts/{owner_id}/{draft_id}`

**Description:** Unpublished post that exists only in draft state.

```python
from datetime import datetime
from typing import Optional, List, Dict, Any
from enum import Enum

class DraftState(str, Enum):
    DRAFT = "DRAFT"
    PREVIEW = "PREVIEW"
    PUBLISHED = "PUBLISHED"
    PENDING_APPROVAL = "PENDING_APPROVAL"
    ARCHIVED = "ARCHIVED"

class Draft(BaseModel):
    """Unpublished post content."""
    
    # Identifiers
    draft_id: str                           # UUID
    owner_id: int                           # Telegram user_id
    created_at: datetime
    updated_at: datetime
    
    # Content
    text: str                               # Post text
    media_ids: List[str] = []              # References to Media entities
    button_groups: List[Dict[str, Any]] = []  # Inline keyboards
    
    # Metadata
    target: Literal["channel", "group", "user"]
    target_id: int                          # Channel/Group/User ID
    scheduled_at: Optional[datetime] = None # For delayed posting
    
    # State
    state: DraftState = DraftState.DRAFT
    
    # Tracking
    version: int = 1                        # For optimistic locking
    
    class Config:
        use_enum_values = True
```

**FSM Transitions (Fixed):**

```
DRAFT → PREVIEW              (action: preview_draft)
DRAFT → PUBLISHED            (action: publish)
DRAFT → ARCHIVED             (action: delete)

PREVIEW → PUBLISHED          (action: publish_preview)
PREVIEW → DRAFT              (action: save_draft)

PUBLISHED → PREVIEW          (action: update)
PUBLISHED → ARCHIVED         (action: archive)

ARCHIVED → [terminal]        (no outgoing transitions)
```

**Policy Overrides (Can Change):**

- PUBLISHED may transition to PENDING_APPROVAL if approval workflow policy applies
- PENDING_APPROVAL may auto-transition to PUBLISHED or ARCHIVED based on approval policy timeout

**Invariants:**

- `INV-D01`: Draft cannot be published if text is empty
- `INV-D02`: Draft cannot reference non-existent media IDs
- `INV-D03`: Only owner can transition draft state
- `INV-D04`: Scheduled draft must have scheduled_at in future
- `INV-D05`: Draft version increments on every update

---

### 1.2 Post

**Storage Location:** `storage/posts/{state}/{owner_id}/{post_id}`

**Description:** Published content delivered to Telegram target (channel, group, or user).

```python
class PostState(str, Enum):
    PUBLISHED = "PUBLISHED"
    UPDATED = "UPDATED"
    ARCHIVED = "ARCHIVED"

class Post(BaseModel):
    """Published post (terminal state from Draft)."""
    
    # Identifiers
    post_id: str                            # UUID (same as draft_id origin)
    owner_id: int
    published_at: datetime
    
    # Content (immutable snapshot from Draft)
    text: str
    media_ids: List[str]
    button_groups: List[Dict[str, Any]]
    
    # Delivery
    target: Literal["channel", "group", "user"]
    target_id: int
    telegram_message_id: int                # Telegram's message_id for this post
    
    # State
    state: PostState = PostState.PUBLISHED
    
    # Tracking
    view_count: int = 0
    interaction_count: int = 0
    
class Config:
        use_enum_values = True
```

**FSM Transitions (Fixed):**

```
PUBLISHED → UPDATED          (action: update_post)
PUBLISHED → ARCHIVED         (action: archive_post)

UPDATED → ARCHIVED           (action: archive_post)

ARCHIVED → [terminal]        (no outgoing transitions)
```

**Invariants:**

- `INV-P01`: Post is immutable once published (except state transition)
- `INV-P02`: Post must reference valid Telegram message_id
- `INV-P03`: Only owner can transition post state

---

### 1.3 Media

**Storage Location:** `storage/posts/media/{owner_id}/{media_id}`

**Description:** Reusable media asset (photo, video, document, audio).

```python
class MediaType(str, Enum):
    PHOTO = "photo"
    VIDEO = "video"
    DOCUMENT = "document"
    AUDIO = "audio"

class Media(BaseModel):
    """Reusable media asset."""
    
    # Identifiers
    media_id: str                           # UUID
    owner_id: int
    uploaded_at: datetime
    
    # Content
    type: MediaType
    file_id: str                            # Telegram file_id
    file_size: int                          # Bytes
    
    # Metadata
    filename: Optional[str] = None
    mime_type: Optional[str] = None
    duration_sec: Optional[int] = None      # For video/audio
    
    # Tracking
    usage_count: int = 0                    # How many posts reference this
    
    class Config:
        use_enum_values = True
```

**Invariants:**

- `INV-M01`: Media must have valid Telegram file_id
- `INV-M02`: Only owner can delete media if usage_count == 0
- `INV-M03`: Media type must match MIME type

---

### 1.4 Button

**Storage Location:** Embedded in Draft/Post `button_groups`

**Description:** Inline keyboard button configuration.

```python
class ButtonType(str, Enum):
    URL = "url"
    CALLBACK = "callback"
    SWITCH_INLINE = "switch_inline"

class Button(BaseModel):
    """Inline keyboard button."""
    
    # Identifiers
    button_id: str                          # UUID
    
    # Display
    text: str                               # Button label (1-64 chars)
    
    # Action
    type: ButtonType
    action: str                             # URL, callback_data, or inline query
    
    class Config:
        use_enum_values = True

class ButtonGroup(BaseModel):
    """Row of buttons in inline keyboard."""
    
    buttons: List[Button]                   # 1-8 buttons per row
    row_index: int                          # Keyboard row number
```

**Invariants:**

- `INV-B01`: Button text must be 1-64 characters
- `INV-B02`: Callback data must be ≤64 characters
- `INV-B03`: Maximum 10 buttons per keyboard (policy-driven)
- `INV-B04`: Maximum 3 rows of buttons

---

## 2. Community Entities

### 2.1 Member

**Storage Location:** `storage/community/members/{group_id}/{user_id}`

**Description:** User membership in a group or channel with role and permissions.

```python
class MemberRole(str, Enum):
    ADMIN = "ADMIN"
    MODERATOR = "MODERATOR"
    MEMBER = "MEMBER"

class MemberState(str, Enum):
    ACTIVE = "ACTIVE"
    SUSPENDED = "SUSPENDED"
    BANNED = "BANNED"
    LEFT = "LEFT"

class Member(BaseModel):
    """Community member (user in group/channel)."""
    
    # Identifiers
    user_id: int
    group_id: int
    joined_at: datetime
    
    # Role & Permissions
    role: MemberRole
    
    # State
    state: MemberState = MemberState.ACTIVE
    suspended_until: Optional[datetime] = None
    
    # Tracking
    message_count: int = 0
    last_activity: datetime = datetime.now()
    violation_count: int = 0
    
    class Config:
        use_enum_values = True
```

**FSM Transitions (Fixed):**

```
ACTIVE → SUSPENDED           (action: suspend)
ACTIVE → BANNED              (action: ban)
ACTIVE → LEFT                (action: leave)

SUSPENDED → ACTIVE           (action: unsuspend, if not expired)
SUSPENDED → BANNED           (action: ban)

BANNED → [terminal]          (no outgoing transitions)

LEFT → [terminal]            (no outgoing transitions)
```

**Policy Overrides (Can Change):**

- Auto-suspend after N violations (moderation policy)
- Auto-ban after M violations (moderation policy)
- Auto-remove inactive members after X days (community policy)

**Invariants:**

- `INV-M01`: Only admin/owner can change member role
- `INV-M02`: Member cannot be both ACTIVE and SUSPENDED
- `INV-M03`: BANNED/LEFT are terminal states
- `INV-M04`: Suspension must have expiry time

---

### 2.2 Poll

**Storage Location:** `storage/polls/{owner_id}/{poll_id}`

**Description:** Voting mechanism with options and user votes.

```python
class PollState(str, Enum):
    DRAFT = "DRAFT"
    OPEN = "OPEN"
    CLOSED = "CLOSED"

class PollOption(BaseModel):
    """Single poll option."""
    
    option_id: str
    text: str
    vote_count: int = 0

class Poll(BaseModel):
    """Voting poll."""
    
    # Identifiers
    poll_id: str                            # UUID
    owner_id: int
    created_at: datetime
    
    # Content
    question: str
    options: List[PollOption]               # 2-10 options
    allows_multiple: bool = False
    
    # State
    state: PollState = PollState.DRAFT
    opened_at: Optional[datetime] = None
    closed_at: Optional[datetime] = None
    
    # Metadata
    target: Literal["channel", "group", "user"]
    target_id: int
    
    class Config:
        use_enum_values = True
```

**FSM Transitions (Fixed):**

```
DRAFT → OPEN                 (action: publish_poll)
DRAFT → CLOSED               (action: abandon)

OPEN → CLOSED                (action: close_poll)

CLOSED → [terminal]          (no outgoing transitions)
```

**Invariants:**

- `INV-PL01`: Poll must have 2-10 options
- `INV-PL02`: Poll question must be 1-300 characters
- `INV-PL03`: Only owner can close poll
- `INV-PL04`: User can only vote once per poll (unless allows_multiple=true)

---

### 2.3 JoinRequest

**Storage Location:** `storage/community/join_requests/{group_id}/{user_id}`

**Description:** Pending membership request to join group.

```python
class JoinRequestState(str, Enum):
    PENDING = "PENDING"
    APPROVED = "APPROVED"
    REJECTED = "REJECTED"

class JoinRequest(BaseModel):
    """Pending group membership request."""
    
    # Identifiers
    request_id: str                         # UUID
    user_id: int
    group_id: int
    created_at: datetime
    
    # Application
    message: Optional[str] = None           # User's message
    answer_to_question: Optional[str] = None  # If join question required
    
    # State
    state: JoinRequestState = JoinRequestState.PENDING
    reviewed_at: Optional[datetime] = None
    reviewed_by: Optional[int] = None       # Admin who reviewed
    rejection_reason: Optional[str] = None
    
    class Config:
        use_enum_values = True
```

**FSM Transitions (Fixed):**

```
PENDING → APPROVED           (action: approve_join)
PENDING → REJECTED           (action: reject_join)

APPROVED → [terminal]        (becomes Member record)

REJECTED → [terminal]        (terminal state)
```

**Policy Overrides (Can Change):**

- Auto-approve if community policy allows (auto_approve_joins=true)
- Require answer to join question (if configured)

**Invariants:**

- `INV-JR01`: Only one pending request per (user_id, group_id)
- `INV-JR02`: Approved request must create Member record
- `INV-JR03`: APPROVED/REJECTED are terminal states

---

## 3. Support Entities

### 3.1 Ticket

**Storage Location:** `storage/tickets/{user_id}/{ticket_id}`

**Description:** Customer support request from user to owner.

```python
class TicketState(str, Enum):
    OPEN = "OPEN"
    IN_PROGRESS = "IN_PROGRESS"
    WAITING_CUSTOMER = "WAITING_CUSTOMER"
    RESOLVED = "RESOLVED"
    CLOSED = "CLOSED"

class TicketPriority(str, Enum):
    LOW = "LOW"
    NORMAL = "NORMAL"
    HIGH = "HIGH"
    URGENT = "URGENT"

class Ticket(BaseModel):
    """Customer support request."""
    
    # Identifiers
    ticket_id: str                          # UUID
    user_id: int                            # Requester
    created_at: datetime
    
    # Content
    subject: str
    description: str
    priority: TicketPriority = TicketPriority.NORMAL
    
    # State
    state: TicketState = TicketState.OPEN
    assigned_to: Optional[int] = None       # Owner/staff member
    
    # Tracking
    message_count: int = 0
    last_update: datetime = datetime.now()
    resolved_at: Optional[datetime] = None
    
    class Config:
        use_enum_values = True
```

**FSM Transitions (Fixed):**

```
OPEN → IN_PROGRESS           (action: assign_ticket)
OPEN → CLOSED                (action: close_abandoned)

IN_PROGRESS → WAITING_CUSTOMER  (action: await_response)
IN_PROGRESS → RESOLVED       (action: mark_resolved)

WAITING_CUSTOMER → IN_PROGRESS  (action: customer_responds)
WAITING_CUSTOMER → CLOSED    (action: close_no_response)

RESOLVED → CLOSED            (action: confirm_closed)

CLOSED → [terminal]          (no outgoing transitions)
```

**Policy Overrides (Can Change):**

- Auto-escalate after N hours without response (customer service policy)
- Auto-close resolved tickets after X days (customer service policy)
- Auto-close waiting-customer after Y days no response (customer service policy)

**Invariants:**

- `INV-T01`: Ticket must have non-empty subject and description
- `INV-T02`: Only owner can assign or close ticket
- `INV-T03`: CLOSED is terminal state
- `INV-T04`: Ticket cannot have zero messages

---

## 4. Delivery Entities

### 4.1 Broadcast

**Storage Location:** `storage/broadcasts/{owner_id}/{broadcast_id}`

**Description:** Mass message delivery to multiple recipients.

```python
class BroadcastState(str, Enum):
    DRAFT = "DRAFT"
    PENDING_APPROVAL = "PENDING_APPROVAL"
    APPROVED = "APPROVED"
    SCHEDULED = "SCHEDULED"
    IN_PROGRESS = "IN_PROGRESS"
    COMPLETED = "COMPLETED"
    CANCELLED = "CANCELLED"

class BroadcastTarget(BaseModel):
    """Target for broadcast delivery."""
    
    target_type: Literal["channel", "group", "users"]
    target_ids: List[int]                   # Channel/Group/User IDs

class Broadcast(BaseModel):
    """Mass message delivery job."""
    
    # Identifiers
    broadcast_id: str                       # UUID
    owner_id: int
    created_at: datetime
    
    # Content
    text: str
    media_ids: List[str] = []
    button_groups: List[Dict[str, Any]] = []
    
    # Targeting
    targets: List[BroadcastTarget]
    total_recipients: int = 0
    
    # Scheduling
    scheduled_at: Optional[datetime] = None
    
    # State
    state: BroadcastState = BroadcastState.DRAFT
    
    # Tracking
    sent_count: int = 0
    failed_count: int = 0
    completed_at: Optional[datetime] = None
    
    class Config:
        use_enum_values = True
```

**FSM Transitions (Fixed):**

```
DRAFT → PENDING_APPROVAL     (action: submit_for_approval)
DRAFT → CANCELLED            (action: cancel)

PENDING_APPROVAL → APPROVED  (action: approve_broadcast)
PENDING_APPROVAL → CANCELLED (action: reject_broadcast)

APPROVED → SCHEDULED         (action: schedule_broadcast)
APPROVED → IN_PROGRESS       (action: start_broadcast)
APPROVED → CANCELLED         (action: cancel)

SCHEDULED → IN_PROGRESS      (when scheduled_at reached)
SCHEDULED → CANCELLED        (action: cancel_scheduled)

IN_PROGRESS → COMPLETED      (all recipients sent)

COMPLETED → [terminal]       (no outgoing transitions)

CANCELLED → [terminal]       (no outgoing transitions)
```

**Policy Overrides (Can Change):**

- Require approval before sending (automation policy)
- Auto-skip blocked users (delivery policy)

**Invariants:**

- `INV-BR01`: Broadcast must have at least one target
- `INV-BR02`: Only owner can approve or cancel
- `INV-BR03`: COMPLETED/CANCELLED are terminal states
- `INV-BR04`: Cannot send to more than max_broadcast_recipients (policy-driven)

---

### 4.2 Reminder

**Storage Location:** `storage/reminders/{user_id}/{reminder_id}`

**Description:** Scheduled alert to user.

```python
class ReminderState(str, Enum):
    SCHEDULED = "SCHEDULED"
    SENT = "SENT"
    CANCELLED = "CANCELLED"
    FAILED = "FAILED"

class Reminder(BaseModel):
    """Scheduled user reminder."""
    
    # Identifiers
    reminder_id: str                        # UUID
    user_id: int
    created_at: datetime
    
    # Content
    message: str
    
    # Scheduling
    scheduled_at: datetime
    repeat: Optional[str] = None            # "daily", "weekly", "monthly"
    
    # State
    state: ReminderState = ReminderState.SCHEDULED
    sent_at: Optional[datetime] = None
    
    # Tracking
    attempt_count: int = 0
    
    class Config:
        use_enum_values = True
```

**FSM Transitions (Fixed):**

```
SCHEDULED → SENT             (when scheduled_at reached)
SCHEDULED → CANCELLED        (action: cancel_reminder)
SCHEDULED → FAILED           (after max retries)

SENT → SCHEDULED             (if repeat configured, reschedule next occurrence)

CANCELLED → [terminal]       (no outgoing transitions)

FAILED → [terminal]          (no outgoing transitions)
```

**Invariants:**

- `INV-REM01`: Reminder must have message
- `INV-REM02`: scheduled_at must be in future
- `INV-REM03`: User cannot have more than max_reminders_per_user (policy-driven)
- `INV-REM04`: Only user or owner can cancel reminder

---

## 5. System Entities

### 5.1 Owner

**Storage Location:** `storage/owner/profile`

**Description:** System owner (Telegram user who controls the bot).

```python
class OwnerRole(str, Enum):
    OWNER = "OWNER"

class Owner(BaseModel):
    """Bot owner (system administrator)."""
    
    # Identifiers
    owner_id: int                           # Telegram user_id
    created_at: datetime
    
    # Profile
    username: Optional[str] = None
    first_name: Optional[str] = None
    last_name: Optional[str] = None
    
    # Settings
    bot_token: str                          # Encrypted Telegram bot token
    webhook_url: str                        # HTTPS endpoint for Telegram
    webhook_secret: str                     # Secret token for webhook validation
    
    # Preferences
    timezone: str = "UTC"
    language: str = "en"
    
    class Config:
        use_enum_values = True
```

**Invariants:**

- `INV-O01`: Exactly one owner per system (singleton)
- `INV-O02`: bot_token must be non-empty and valid
- `INV-O03`: webhook_secret must be at least 16 characters

---

### 5.2 User

**Storage Location:** `storage/users/{user_id}`

**Description:** Telegram user interacting with the bot.

```python
class UserRole(str, Enum):
    MEMBER = "MEMBER"
    GUEST = "GUEST"

class UserState(str, Enum):
    ACTIVE = "ACTIVE"
    BANNED = "BANNED"

class User(BaseModel):
    """Telegram user."""
    
    # Identifiers
    user_id: int
    created_at: datetime
    
    # Profile
    username: Optional[str] = None
    first_name: Optional[str] = None
    last_name: Optional[str] = None
    
    # Role & State
    role: UserRole = UserRole.GUEST
    state: UserState = UserState.ACTIVE
    
    # Tracking
    last_seen: datetime = datetime.now()
    message_count: int = 0
    
    class Config:
        use_enum_values = True
```

**FSM Transitions (Fixed):**

```
ACTIVE → BANNED              (action: ban_user)

BANNED → [terminal]          (no outgoing transitions)
```

**Invariants:**

- `INV-U01`: user_id must be valid Telegram ID
- `INV-U02`: Role determines available actions
- `INV-U03`: BANNED is terminal state

---

## Integration with ExecutionPlan

**ExecutionPlan** (Step 5, Layer 2) references these domain entities when planning mutations:

```python
class ExecutionPlan(BaseModel):
    """Step 5: What mutations to apply."""
    
    entity_mutations: List[EntityMutation]  # References domain entities
    state_transitions: List[StateTransition]  # FSM transitions
    
class EntityMutation(BaseModel):
    entity_type: Literal[
        "Draft", "Post", "Media", "Button",
        "Member", "Poll", "JoinRequest",
        "Ticket", "Broadcast", "Reminder",
        "Owner", "User", "Channel", "Group"
    ]
    entity_id: str
    current_state: str                      # Current FSM state
    next_state: str                         # Next FSM state (after policy override)
    mutations: Dict[str, Any]               # Fields to update
    
class StateTransition(BaseModel):
    entity_type: str
    entity_id: str
    from_state: str
    to_state: str
    action: str                             # User-initiated action
    reason: Optional[str] = None            # Why state changed
```

---

## Summary Table

| Entity | Storage Prefix | Primary State | Terminal States | Policy Hooks |
|--------|---|---|---|---|
| Draft | posts/drafts | DRAFT | ARCHIVED | Approval workflow |
| Post | posts/{state} | PUBLISHED | ARCHIVED | Update/archive policy |
| Member | community/members | ACTIVE | BANNED, LEFT | Auto-ban, suspend |
| Poll | polls | OPEN | CLOSED | Closing timeout |
| JoinRequest | community/join_requests | PENDING | APPROVED, REJECTED | Auto-approve |
| Ticket | tickets | OPEN | CLOSED | Escalation, SLA |
| Broadcast | broadcasts | DRAFT | COMPLETED, CANCELLED | Approval required |
| Reminder | reminders | SCHEDULED | SENT, CANCELLED, FAILED | Retry policy |
| User | users | ACTIVE | BANNED | Moderation policy |
| Member | community/members | ACTIVE | BANNED, LEFT | Community policy |

All FSM transitions enforce the **fixed invariants** while allowing **policy layer overrides** at designated decision points.

