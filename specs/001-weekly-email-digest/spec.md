# Feature Specification: Weekly Email Digest

**Feature Branch**: `001-weekly-email-digest`  
**Created**: 2025-12-05  
**Status**: Draft  
**Input**: User description: "Objective: Provide a weekly email that synthesizes the past week's daily summaries—surfacing trends, top weekly comments, and overall sentiment changes—for users who opt into a weekly cadence. Ensure exactly one weekly send per week per opted-in user."

## User Scenarios & Testing *(mandatory)*

### User Story 1 - Subscribe to Weekly Digest (Priority: P1)

A user wants to receive a consolidated weekly email instead of (or in addition to) daily emails. They navigate to their notification preferences and select their preferred email cadence: daily only, weekly only, or both.

**Why this priority**: Without the ability to opt into weekly emails, the entire feature has no subscribers. This is the foundational capability that enables all other weekly digest functionality.

**Independent Test**: Can be fully tested by allowing a user to change their email preference setting and verifying the preference persists. Delivers value by giving users control over their communication frequency.

**Acceptance Scenarios**:

1. **Given** a user is on the notification preferences page, **When** they select "Weekly only" and save, **Then** their preference is stored and they stop receiving daily emails.
2. **Given** a user has "Daily only" selected, **When** they change to "Both daily and weekly" and save, **Then** they receive both daily emails and one weekly digest per week.
3. **Given** a user has "Weekly only" selected, **When** they change to "Daily only", **Then** they stop receiving weekly digests and resume daily emails only.
4. **Given** a new user signs up, **When** they view notification preferences, **Then** the default cadence matches the existing platform default (unchanged behavior).

---

### User Story 2 - Receive Weekly Digest Email (Priority: P1)

A user who has opted into weekly emails receives a single consolidated email summarizing the past week's market pulse activity. The email synthesizes daily summaries into a coherent narrative highlighting trends, sentiment changes, top comments, and actionable insights.

**Why this priority**: This is the core value proposition—delivering the weekly digest. Equal priority with subscription because both are required for an MVP.

**Independent Test**: Can be fully tested by triggering the weekly job for a user with existing daily summaries and verifying they receive exactly one email with the expected content structure.

**Acceptance Scenarios**:

1. **Given** a user is opted into weekly emails and has 7 days of daily summaries, **When** the weekly job runs, **Then** they receive exactly one email containing a synthesized summary.
2. **Given** a user is opted into weekly emails and has 4 days of daily summaries (partial week), **When** the weekly job runs, **Then** they receive an email summarizing the available days with transparent acknowledgment of limited data.
3. **Given** a user is opted into "Both" cadence, **When** the weekly job runs, **Then** they receive the weekly digest in addition to their daily emails (not instead of).
4. **Given** a user is opted into "Daily only", **When** the weekly job runs, **Then** they do not receive a weekly digest.

---

### User Story 3 - Weekly Digest Content Quality (Priority: P2)

A user reads their weekly digest and finds a well-structured, scannable email that synthesizes the week's information rather than repeating daily content verbatim. The email follows a consistent structure with headline, key highlights, sentiment analysis, and recommended actions.

**Why this priority**: Content quality determines whether users find value and remain subscribed. Important but dependent on the delivery mechanism working first.

**Independent Test**: Can be tested by reviewing generated weekly digest content against quality criteria: narrative synthesis (not day-by-day repetition), presence of all required sections, appropriate length, and factual accuracy.

**Acceptance Scenarios**:

1. **Given** daily summaries contain overlapping themes, **When** the weekly digest is generated, **Then** the content synthesizes themes into a cohesive narrative rather than repeating each day's mention.
2. **Given** sentiment varied throughout the week, **When** the weekly digest is generated, **Then** it describes the sentiment direction (improving, stable, or declining) with key drivers.
3. **Given** the weekly digest is generated, **When** a user views it, **Then** all required sections are present: headline, 3-5 highlight bullets, top comments/signals, trend & sentiment, risks/opportunities, and recommended next actions.
4. **Given** insufficient data exists for a section, **When** the digest is generated, **Then** the section transparently acknowledges limited data rather than fabricating content.

---

### User Story 4 - Idempotent Weekly Delivery (Priority: P2)

The system ensures each opted-in user receives exactly one weekly email per week, even if the job is retried, runs multiple times, or encounters partial failures.

**Why this priority**: Critical for user trust and preventing spam complaints. Ranked P2 because it's a system reliability concern that can be addressed after basic functionality works.

**Independent Test**: Can be tested by triggering the weekly job multiple times for the same user in the same week and verifying only one email is sent.

**Acceptance Scenarios**:

1. **Given** a user has already received their weekly digest for the current week, **When** the weekly job runs again, **Then** no duplicate email is sent.
2. **Given** the weekly job partially fails mid-execution, **When** it is retried, **Then** users who already received emails are skipped and remaining users are processed.
3. **Given** a user's weekly digest failed to send, **When** the job retries, **Then** that specific user receives their email without affecting others.

---

### User Story 5 - Weekly Job Scheduling (Priority: P3)

The weekly digest job runs automatically at a consistent time each week, respecting user time zones when available and handling daylight saving time transitions gracefully.

**Why this priority**: Automation is important for production but can be manually triggered during initial rollout. Lower priority than core functionality.

**Independent Test**: Can be tested by configuring the job schedule, observing it triggers at the expected time, and verifying DST transitions don't cause missed or duplicate runs.

**Acceptance Scenarios**:

1. **Given** the weekly job is configured for Sunday 9:00 AM, **When** that time arrives, **Then** the job executes automatically.
2. **Given** a user has a time zone configured, **When** the weekly job runs, **Then** the email is sent at an appropriate time for their local time zone.
3. **Given** a DST transition occurs during the week, **When** the weekly job runs, **Then** it executes at the correct adjusted time without skipping or duplicating.
4. **Given** no user time zone is available, **When** the weekly job runs, **Then** the platform default time zone is used.

---

### Edge Cases

- **No daily summaries exist**: If zero daily summaries exist for the 7-day window, skip sending the weekly digest (or send a minimal "no updates this week" message per configuration).
- **Partial week data**: If only some days have summaries (e.g., 3 of 7), generate the digest from available data and acknowledge the limited scope.
- **Late-arriving data**: Data arriving after the job starts is excluded from the current week's digest and rolls into the next week.
- **User opts out mid-week**: If a user changes from weekly to daily-only after the weekly window starts but before the job runs, they should not receive the weekly digest.
- **First-time weekly subscriber**: On first weekly digest, include data from the last 7 days even if the user subscribed mid-week.
- **Failed daily summary generation**: Missing or failed daily summaries for specific days should not block the weekly digest; use available days.
- **Very long daily summaries**: The weekly digest should remain scannable regardless of input volume.

## Requirements *(mandatory)*

### Functional Requirements

- **FR-001**: System MUST allow users to select their email cadence preference: "Daily only", "Weekly only", or "Both daily and weekly".
- **FR-002**: System MUST persist user email cadence preferences and apply them to email delivery logic.
- **FR-003**: System MUST default existing users to "Daily only" (backward compatible) and new users to "Both daily and weekly".
- **FR-004**: System MUST send exactly one weekly digest per opted-in user per week (idempotent delivery).
- **FR-005**: System MUST include daily summaries from the 7-day window ending at job start time in the weekly digest.
- **FR-006**: System MUST skip weekly digest delivery if no daily summaries exist for the time window.
- **FR-007**: System MUST generate weekly digest content that synthesizes daily summaries into a narrative (not day-by-day repetition).
- **FR-008**: System MUST include in the weekly digest: headline, 3-5 highlight bullets, top comments/signals section, trend & sentiment analysis, risks/opportunities, and recommended next actions.
- **FR-009**: System MUST describe sentiment direction (improving, stable, declining) with identified key drivers.
- **FR-010**: System MUST use only supplied daily summaries and comments as source data (no hallucinated content).
- **FR-011**: System MUST transparently acknowledge when data is limited or incomplete.
- **FR-012**: System MUST track weekly send status per user to prevent duplicate sends within the same week.
- **FR-013**: System MUST support retry of failed sends without re-sending to successful recipients.
- **FR-014**: System MUST log each job run with: users processed count, emails sent count, skips with reasons.
- **FR-015**: System MUST define a cutoff time at job start; data arriving after cutoff rolls to next week.
- **FR-016**: System MUST continue processing other users if one user's digest fails.
- **FR-017**: Weekly digest emails MUST be visually distinct from daily emails (different template/layout).
- **FR-018**: System MUST respect user time zones for delivery timing when available; otherwise use platform default.
- **FR-019**: System MUST handle DST transitions without missing or duplicating weekly sends.
- **FR-020**: Weekly digest job MUST be integrated into CI/CD deployment pipeline (deploy-ecs-jobs workflow) for automated deployment alongside other ECS batch jobs.

### Key Entities

- **User Email Preference**: Stores user's selected cadence (daily_only, weekly_only, both). Links to user. Includes opt-in/opt-out timestamps.
- **Weekly Digest Record**: Tracks weekly digest status per user per week. Contains: user reference, week identifier, send status (pending, sent, failed, skipped), sent timestamp, skip reason if applicable.
- **Daily Summary**: Existing entity containing daily summary content, timestamp, user linkage. Used as input to weekly aggregation.
- **Weekly Digest Content**: The generated digest content including all sections (headline, highlights, sentiment analysis, etc.). Linked to weekly digest record.

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: 100% of users who opt into weekly emails receive exactly one weekly digest per week (no duplicates, no misses).
- **SC-002**: Weekly digest emails are delivered within 2 hours of the scheduled job time for all opted-in users.
- **SC-003**: Weekly digest open rate meets or exceeds daily email open rate within 4 weeks of launch.
- **SC-004**: Spam complaint rate for weekly digests remains below 0.1% of sends.
- **SC-005**: Weekly job success rate is 99.5% or higher (measured over rolling 4-week period).
- **SC-006**: Users can update their email cadence preference and see the change reflected within 1 minute.
- **SC-007**: Weekly digest email is scannable and readable in under 3 minutes for typical content volume.
- **SC-008**: Opt-out rate from weekly digest is below 5% in first month post-launch.
- **SC-009**: System correctly handles 100% of edge cases (partial data, late data, retries) without manual intervention.
- **SC-010**: All job runs are logged with complete metrics (users processed, sent, skipped) for monitoring and debugging.

## Clarifications

### Session 2025-12-05

- Q: Should the weekly digest job be integrated into CI/CD deployment pipelines? → A: Yes, weekly digest job MUST be included in CI/CD workflow (same as other ECS jobs).
- Q: What should be the default email cadence for new users? → A: New users default to "Both daily and weekly".

## Assumptions

- Daily summaries are already being generated and stored with timestamps and user linkage.
- User time zone information is available in existing user profile data or can be inferred.
- Top comments/feedback data is available or can be derived from existing data stores.
- Sentiment data per day is available from existing daily summary generation.
- Email infrastructure supports templating for a distinct weekly email layout.
- The LLM/summarization service used for daily summaries can also generate weekly synthesis.
- Platform has existing job scheduling infrastructure that can run weekly tasks.
- Existing email preference system can be extended to support cadence options.
