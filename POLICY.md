# TELEGBOT Operating System — Policy Layer Specification

**DEPLOYABLE BUSINESS LOGIC**

This document defines all policy layers that sit **above** the fixed architecture. Policies can change frequently without touching the core system.

---

## Policy Layer Overview

```
┌─────────────────────────────────────────────────────────────┐
│                  POLICY LAYER (Deployable)                  │
│                                                              │
│  ✅ Content policies                                         │
│  ✅ Permission & RBAC                                        │
│  ✅ Moderation rules                                         │
│  ✅ Approval workflows                                       │
│  ✅ Quotas & rate limits                                     │
│  ✅ Community rules                                          │
│  ✅ Customer service procedures                              │
│  ✅ Entitlements & features                                  │
│                                                              │
│  Change Frequency: Often                                     │
│  Requires Code Changes: No (configuration only)              │
│  Impacts Architecture: No (policies don't touch core)        │
└─────────────────────────────────────────────────────────────┘
                           │
        ┌──────────────────┴──────────────────┐
        │                                     │
        ▼                                     ▼
   Step 3: Permission Validation         Step 6: FSM Processing
   (Runtime Pipeline)                     (Runtime Pipeline)
```

---

## 1. Content Policy

**Controls what content is allowed in the system.**

### Configuration

```yaml
ContentPolicy:
  # Quotas
  max_drafts_per_owner: 1000
  max_scheduled_posts: 100
  max_media_per_post: 10
  max_post_length: 4096
  max_buttons_per_keyboard: 10
  
  # Restrictions
  prohibited_words: []
  allowed_media_types:
    - photo
    - video
    - document
    - audio
  
  # Workflows
  require_approval_for_publication: false
  auto_archive_after_days: 90
  
  # Channel-specific
  channel:
    max_post_length: 1024
    require_media: false
  
  # Group-specific
  group:
    max_post_length: 2048
    require_media: false
```

### Implementation

```python
from pydantic import BaseModel
from typing import List, Optional

class ContentPolicy(BaseModel):
    """Content creation and publication rules."""
    
    # Quotas
    max_drafts_per_owner: int = 1000
    max_scheduled_posts: int = 100
    max_media_per_post: int = 10
    max_post_length: int = 4096
    max_buttons_per_keyboard: int = 10
    
    # Restrictions
    prohibited_words: List[str] = []
    allowed_media_types: List[str] = ["photo", "video", "document"]
    
    # Workflows
    require_approval_for_publication: bool = False
    auto_archive_after_days: Optional[int] = 90
    
    async def validate_content(self, content: str, target: str) -> tuple[bool, Optional[str]]:
        """
        Validate content before allowing publication.
        
        Args:
            content: The content text
            target: "channel", "group", or "user"
        
        Returns:
            (is_valid, reason_if_invalid)
        """
        # Check length
        if len(content) > self.max_post_length:
            return False, f"Content exceeds {self.max_post_length} characters"
        
        # Check prohibited words
        for word in self.prohibited_words:
            if word.lower() in content.lower():
                return False, f"Content contains prohibited term: {word}"
        
        return True, None
    
    async def check_quota(self, owner_id: int, quota_type: str) -> bool:
        """
        Check if owner has quota remaining.
        
        Args:
            owner_id: Owner identifier
            quota_type: "drafts", "scheduled", or "media"
        
        Returns:
            True if quota available
        """
        # Implementation checks KV for usage counts
        pass
```

---

## 2. Permission Policy (RBAC)

**Controls who can do what.**

### Configuration

```yaml
PermissionPolicy:
  roles:
    OWNER:
      permissions:
        - "*"  # All permissions
    
    EDITOR:
      permissions:
        - create_post
        - edit_post
        - publish_post
        - view_analytics
    
    MEMBER:
      permissions:
        - create_ticket
        - view_faq
        - view_guides
        - vote_poll
        - join_group
    
    GUEST:
      permissions:
        - view_faq
        - view_public_posts
  
  # Resource-level permissions
  resource_permissions:
    post:
      edit: "owner_only"  # Only post creator can edit
      delete: "owner_only"
    ticket:
      create: "authenticated"  # Any authenticated user
      close: "owner_only"
    channel:
      post: "owner_only"
```

### Implementation

```python
from enum import Enum
from typing import List, Dict

class Role(str, Enum):
    OWNER = "OWNER"
    EDITOR = "EDITOR"
    MEMBER = "MEMBER"
    GUEST = "GUEST"

class PermissionPolicy(BaseModel):
    """Role-based access control."""
    
    roles: Dict[Role, List[str]] = {
        Role.OWNER: ["*"],  # All permissions
        Role.MEMBER: ["create_ticket", "view_faq"],
        Role.GUEST: ["view_faq"],
    }
    
    async def get_actor_role(self, actor_id: int) -> Role:
        """Retrieve actor's assigned role from storage."""
        # Look up in KV: storage/users/{actor_id}/role
        pass
    
    async def check_permission(self, actor_id: int, action: str) -> bool:
        """
        Check if actor is allowed to perform action.
        
        Args:
            actor_id: Actor identifier
            action: Action name (e.g., "publish_post")
        
        Returns:
            True if allowed
        """
        role = await self.get_actor_role(actor_id)
        role_permissions = self.roles.get(role, [])
        
        # Owner has all permissions
        if "*" in role_permissions:
            return True
        
        return action in role_permissions
    
    async def check_resource_permission(
        self,
        actor_id: int,
        resource_type: str,
        action: str,
        resource_id: str,
    ) -> bool:
        """
        Check resource-level permission.
        
        Args:
            actor_id: Actor identifier
            resource_type: "post", "ticket", "channel"
            action: "edit", "delete", "create"
            resource_id: Specific resource ID
        
        Returns:
            True if allowed
        """
        # First check general permission
        if not await self.check_permission(actor_id, action):
            return False
        
        # Then check resource ownership
        if resource_type == "post":
            post = await kv.get(["posts", "published", resource_id])
            return post.owner_id == actor_id
        
        return True
```

---

## 3. Moderation Policy

**Controls spam, abuse, and content violations.**

### Configuration

```yaml
ModerationPolicy:
  # Rate limiting
  rate_limit:
    messages_per_min: 10
    posts_per_hour: 5
    join_requests_per_day: 50
  
  # Content filtering
  prohibited_domains: []
  spam_keywords:
    - "buy now"
    - "click here"
  
  # User escalation
  auto_timeout_after_violations: 3
  timeout_duration_hours: 24
  
  # Automated actions
  auto_delete_spam: true
  auto_ban_after_violations: 10
```

### Implementation

```python
class ModerationPolicy(BaseModel):
    """Spam and abuse prevention."""
    
    rate_limit_messages_per_min: int = 10
    rate_limit_posts_per_hour: int = 5
    
    prohibited_domains: List[str] = []
    spam_keywords: List[str] = []
    
    auto_timeout_after_violations: int = 3
    auto_ban_after_violations: int = 10
    
    async def check_rate_limit(self, actor_id: int, action_type: str) -> bool:
        """
        Check if actor exceeds rate limit.
        
        Args:
            actor_id: Actor identifier
            action_type: "message", "post", "join_request"
        
        Returns:
            True if within limits
        """
        # Check action count in last minute/hour from KV
        pass
    
    async def detect_violations(self, content: str) -> List[str]:
        """
        Detect policy violations in content.
        
        Args:
            content: Content to scan
        
        Returns:
            List of violations found
        """
        violations = []
        
        for domain in self.prohibited_domains:
            if domain in content:
                violations.append(f"PROHIBITED_DOMAIN: {domain}")
        
        for keyword in self.spam_keywords:
            if keyword.lower() in content.lower():
                violations.append(f"SPAM_KEYWORD: {keyword}")
        
        return violations
    
    async def escalate_user(self, actor_id: int, violation_count: int) -> Optional[str]:
        """
        Determine escalation action based on violation count.
        
        Returns:
            Action: "none", "timeout", "ban", or None
        """
        if violation_count >= self.auto_ban_after_violations:
            return "ban"
        elif violation_count >= self.auto_timeout_after_violations:
            return "timeout"
        return None
```

---

## 4. Approval Workflow Policy

**Controls when content requires owner approval.**

### Configuration

```yaml
ApprovalWorkflowPolicy:
  # What requires approval?
  require_approval_for_channel_posts: false
  require_approval_for_broadcasts: true
  require_approval_for_new_members: false
  
  # Approval routing
  approval_timeout_hours: 24
  auto_publish_if_not_approved: false
  escalate_to_owner: true
  
  # Notification
  notify_owner_on_pending: true
  notify_submitter_on_rejection: true
```

### Implementation

```python
class ApprovalWorkflowPolicy(BaseModel):
    """When and how approval workflows execute."""
    
    require_approval_for_channel_posts: bool = False
    require_approval_for_broadcasts: bool = True
    require_approval_for_new_members: bool = False
    
    approval_timeout_hours: int = 24
    auto_publish_if_not_approved: bool = False
    
    async def should_require_approval(
        self,
        intent_type: str,
        target: str,
        actor_id: int,
    ) -> bool:
        """
        Determine if this intent requires approval.
        
        Args:
            intent_type: "publish", "broadcast", "join_request"
            target: "channel", "group", "user"
            actor_id: Actor identifier
        
        Returns:
            True if approval required
        """
        if intent_type == "publish" and target == "channel":
            return self.require_approval_for_channel_posts
        
        if intent_type == "broadcast":
            return self.require_approval_for_broadcasts
        
        if intent_type == "join_request":
            return self.require_approval_for_new_members
        
        return False
    
    async def route_for_approval(self, intent_id: str, intent: Dict) -> None:
        """Route intent to owner for review."""
        # Transition FSM state to "PENDING_APPROVAL"
        # Store intent in KV: storage/approvals/pending/{intent_id}
        # Notify owner via Telegram
        pass
```

---

## 5. Community Policy

**Controls group and community features.**

### Configuration

```yaml
CommunityPolicy:
  # Join rules
  auto_approve_joins: false
  require_answer_to_join_question: true
  join_question: "What brings you here?"
  
  # Member rules
  member_inactivity_removal_days: 90
  max_members: null  # Unlimited
  
  # Engagement
  allow_polls: true
  allow_forum_topics: true
  allow_member_announcements: false
  
  # Moderation
  auto_remove_inactive: true
```

### Implementation

```python
class CommunityPolicy(BaseModel):
    """Community and group engagement rules."""
    
    auto_approve_joins: bool = False
    require_answer_to_join_question: bool = False
    join_question: Optional[str] = None
    
    member_inactivity_removal_days: Optional[int] = None
    max_members: Optional[int] = None
    
    allow_polls: bool = True
    allow_forum_topics: bool = True
    allow_member_announcements: bool = False
    
    async def validate_join_request(
        self,
        request: Dict,
    ) -> tuple[bool, Optional[str]]:
        """
        Validate join request.
        
        Returns:
            (approved, reason_if_denied)
        """
        if self.auto_approve_joins:
            return True, None
        
        if self.require_answer_to_join_question:
            if not request.get("answer"):
                return False, "Must answer join question"
        
        return True, None
    
    async def can_post_announcement(self, actor_id: int) -> bool:
        """Check if member can post announcements."""
        if not self.allow_member_announcements:
            return False
        
        # Check role or membership level
        pass
```

---

## 6. Customer Service Policy

**Controls support ticket handling.**

### Configuration

```yaml
CustomerServicePolicy:
  # Escalation
  auto_escalate_after_hours: 24
  escalation_target: null  # Owner ID or group
  
  # Requirements
  faq_required_before_ticket: true
  guides_required_before_ticket: true
  
  # Ticket limits
  max_open_tickets_per_user: 5
  auto_close_resolved_after_days: 7
  
  # SLA
  first_response_sla_hours: 4
  resolution_sla_hours: 48
```

### Implementation

```python
class CustomerServicePolicy(BaseModel):
    """Support ticket and customer service rules."""
    
    auto_escalate_after_hours: int = 24
    faq_required_before_ticket: bool = True
    guides_required_before_ticket: bool = True
    
    max_open_tickets_per_user: int = 5
    auto_close_resolved_after_days: int = 7
    
    async def can_create_ticket(self, user_id: int) -> tuple[bool, Optional[str]]:
        """Check if user can create a support ticket."""
        open_tickets = await kv.get([
            "tickets",
            "by_user",
            user_id,
            "open",
        ]) or []
        
        if len(open_tickets) >= self.max_open_tickets_per_user:
            return False, f"Maximum {self.max_open_tickets_per_user} open tickets allowed"
        
        return True, None
```

---

## 7. Delivery Policy

**Controls how messages are sent.**

### Configuration

```yaml
DeliveryPolicy:
  # Batching
  batch_messages_per_second: 10
  max_message_age_before_discard: 86400  # 24 hours
  
  # Retry strategy
  max_retries: 5
  base_retry_delay_sec: 2
  retry_backoff_multiplier: 2.0
  
  # Throttling
  rate_limit_per_user_per_min: 30
  rate_limit_per_channel_per_hour: 100
  
  # Failure handling
  skip_blocked_users: true
  skip_deactivated_accounts: true
```

### Implementation

```python
class DeliveryPolicy(BaseModel):
    """Message delivery and retry rules."""
    
    max_retries: int = 5
    base_retry_delay_sec: int = 2
    retry_backoff_multiplier: float = 2.0
    
    rate_limit_per_user_per_min: int = 30
    rate_limit_per_channel_per_hour: int = 100
    
    skip_blocked_users: bool = True
    skip_deactivated_accounts: bool = True
    
    async def should_retry_delivery(
        self,
        attempt_count: int,
        error_type: str,
    ) -> bool:
        """Determine if delivery should be retried."""
        if attempt_count >= self.max_retries:
            return False
        
        # Don't retry if user blocked bot
        if self.skip_blocked_users and error_type == "USER_BLOCKED":
            return False
        
        return True
    
    def calculate_retry_delay(self, attempt_count: int) -> int:
        """
        Calculate exponential backoff delay.
        
        Args:
            attempt_count: Number of attempts made
        
        Returns:
            Delay in seconds
        """
        return int(
            self.base_retry_delay_sec
            * (self.retry_backoff_multiplier ** attempt_count)
        )
```

---

## 8. Automation Policy

**Controls scheduling and background automation.**

### Configuration

```yaml
AutomationPolicy:
  # Scheduling
  max_scheduled_jobs: 100
  min_schedule_interval_sec: 60
  max_schedule_interval_days: 365
  
  # Broadcasting
  max_broadcast_recipients: 10000
  require_approval_for_broadcast: true
  
  # Reminders
  max_reminders_per_user: 10
  min_reminder_interval_sec: 60
```

### Implementation

```python
class AutomationPolicy(BaseModel):
    """Automation and scheduling rules."""
    
    max_scheduled_jobs: int = 100
    min_schedule_interval_sec: int = 60
    max_schedule_interval_days: int = 365
    
    max_broadcast_recipients: int = 10000
    require_approval_for_broadcast: bool = True
    
    max_reminders_per_user: int = 10
    
    async def validate_schedule(
        self,
        schedule: Dict,
    ) -> tuple[bool, Optional[str]]:
        """Validate scheduled job."""
        interval_sec = schedule.get("interval_sec")
        
        if interval_sec < self.min_schedule_interval_sec:
            return False, f"Interval must be at least {self.min_schedule_interval_sec}s"
        
        return True, None
```

---

## Policy Integration with Runtime Pipeline

### Step 3: Permission Validation

```python
# Step 3 implementation
async def permission_validation_step(
    event: CanonicalEvent,
    policies: PolicyService,
) -> tuple[bool, Optional[str]]:
    """
    Step 3: PERMISSION VALIDATION
    
    Check:
    1. Is actor authenticated?
    2. Does actor have role permission?
    3. Is actor rate-limited (moderation)?
    4. Does actor have quota (content)?
    """
    
    # Check RBAC
    has_permission = await policies.permission.check_permission(
        event.user_id,
        event.action,
    )
    if not has_permission:
        return False, "Permission denied"
    
    # Check rate limits
    within_limits = await policies.moderation.check_rate_limit(
        event.user_id,
        event.action,
    )
    if not within_limits:
        return False, "Rate limit exceeded"
    
    # Check quota
    has_quota = await policies.content.check_quota(
        event.user_id,
        "drafts",
    )
    if not has_quota:
        return False, "Quota exceeded"
    
    return True, None
```

### Step 6: FSM Processing

```python
# Step 6 implementation
async def fsm_processing_step(
    intent: Intent,
    current_state: str,
    policies: PolicyService,
) -> str:
    """
    Step 6: FSM PROCESSING
    
    1. Get next state from FSM state machine
    2. Check if policy requires approval
    3. Apply policy override if needed
    """
    
    # Get next state from fixed FSM
    fsm = get_fsm_state_machine()
    next_state = fsm[current_state].get(intent.action)
    
    # Check if approval workflow applies
    needs_approval = await policies.approval.should_require_approval(
        intent.action,
        intent.target,
        intent.actor_id,
    )
    
    if needs_approval and next_state == "PUBLISHED":
        next_state = "PENDING_APPROVAL"  # Policy override
    
    return next_state
```

---

## Deployment Scenarios

### Enterprise (Strict)

```yaml
# policies/enterprise.yaml
ContentPolicy:
  max_post_length: 1024
  require_approval_for_publication: true
  prohibited_words: ["internal", "confidential"]

PermissionPolicy:
  roles:
    ADMIN: ["*"]
    EDITOR: ["create_post", "edit_post"]
    VIEWER: ["view_posts"]

ModerationPolicy:
  rate_limit:
    messages_per_min: 5
    posts_per_hour: 10
  auto_ban_after_violations: 1

ApprovalWorkflowPolicy:
  require_approval_for_channel_posts: true
  approval_timeout_hours: 4
```

### Community (Open)

```yaml
# policies/community.yaml
ContentPolicy:
  max_post_length: 4096
  require_approval_for_publication: false

CommunityPolicy:
  auto_approve_joins: true
  allow_member_announcements: true

ModerationPolicy:
  rate_limit:
    messages_per_min: 50
    posts_per_hour: 100
  auto_ban_after_violations: 10
```

### Personal (Unlimited)

```yaml
# policies/personal.yaml
ContentPolicy:
  max_drafts_per_owner: 10000
  require_approval_for_publication: false

PermissionPolicy:
  roles:
    OWNER: ["*"]

ModerationPolicy:
  rate_limit:
    messages_per_min: 1000
    posts_per_hour: 10000
```

---

## Summary

| Policy | Purpose | Changes When |
|--------|---------|--------------|
| **Content** | Content restrictions, quotas | Business needs change |
| **Permission** | Who can do what | Role structure changes |
| **Moderation** | Spam/abuse prevention | Moderation rules evolve |
| **Approval** | When approval is needed | Approval workflows change |
| **Community** | Group engagement rules | Community guidelines update |
| **Customer Service** | Support ticket handling | SLA or support process changes |
| **Delivery** | Message sending rules | Retry strategy or rate limits change |
| **Automation** | Scheduling & automation | Automation rules change |

All policies can be updated **without touching the architecture layer** or the 13-step runtime pipeline.

