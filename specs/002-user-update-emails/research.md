# Research: User Update Emails

**Feature**: 002-user-update-emails  
**Date**: 2025-01-27  
**Purpose**: Resolve technical unknowns and establish implementation patterns

## Research Questions

### 1. Config File Format: YAML vs JSON

**Question**: Should we use YAML or JSON for the config file?

**Research**:
- YAML: More human-readable, supports multi-line strings naturally (good for HTML email body), comments supported, common in Python projects
- JSON: Simpler parsing, no dependencies (stdlib), stricter validation, but harder to write multi-line HTML

**Decision**: **YAML**  
**Rationale**: 
- HTML email bodies are multi-line and YAML handles this naturally with `|` or `>` block scalars
- YAML supports comments which is useful for config files
- Python has excellent YAML support via `pyyaml` (already likely in dependencies)
- More readable for developers writing email content

**Alternatives Considered**:
- JSON: Rejected due to poor multi-line string support (would require escaping or base64)
- TOML: Considered but less common in Python ecosystem

**Implementation Notes**:
- Use `pyyaml` for parsing
- Validate config structure with Pydantic models
- Support both YAML and JSON if needed (YAML parser can handle JSON)

---

### 2. Screenshot Embedding: Inline vs Attachment

**Question**: How should screenshots be embedded in emails - inline (CID) or as attachments?

**Research**:
- **Inline (CID)**: Images embedded in HTML body using `cid:` references. Better UX (images visible immediately), but larger email size, some email clients block by default
- **Attachments**: Images attached to email. Smaller email size, user must click to view, more reliable delivery
- **Hybrid**: Inline with fallback attachments (best practice)

**Decision**: **Inline (CID) with HTML `<img>` tags**  
**Rationale**:
- Better user experience - screenshots visible immediately in email body
- Standard practice for marketing/update emails
- Email service (AWS SES) supports multipart emails with inline images
- Can add `alt` text for accessibility

**Alternatives Considered**:
- Attachments only: Rejected - poor UX, users may not open attachments
- External URLs: Rejected - requires hosting, may be blocked, breaks offline viewing

**Implementation Notes**:
- Use `email.mime.multipart.MIMEMultipart` with `related` subtype
- Attach images with `Content-ID` headers
- Reference in HTML: `<img src="cid:image1">`
- Validate image file paths and sizes before sending

---

### 3. Email Rate Limiting & Batching Strategy

**Question**: How should we handle sending to large recipient lists while respecting AWS SES rate limits?

**Research**:
- AWS SES Sandbox: 1 email/second, 200 emails/day
- AWS SES Production: 14 emails/second, 50,000 emails/day (can request increase)
- Best practice: Batch sends with delays, exponential backoff on errors

**Decision**: **Batch processing with configurable delay**  
**Rationale**:
- Process users in batches (e.g., 14 users per batch)
- Add delay between batches (1 second) to stay within rate limit
- Log progress after each batch
- Continue on individual failures, report summary at end

**Alternatives Considered**:
- Send all at once: Rejected - will hit rate limits, may cause failures
- Queue-based (SQS): Overkill for ad-hoc script, adds complexity

**Implementation Notes**:
- Configurable batch size: `EMAIL_BATCH_SIZE=14` (default)
- Configurable delay: `EMAIL_BATCH_DELAY_SECONDS=1` (default)
- Track success/failure per user
- Report summary: total sent, failed, skipped

---

### 4. HTML Email Best Practices

**Question**: What HTML email practices ensure compatibility across email clients?

**Research**:
- Email clients have inconsistent CSS support (especially Gmail, Outlook)
- Best practice: Inline CSS, table-based layouts, avoid modern CSS features
- Test across: Gmail, Outlook, Apple Mail

**Decision**: **Inline CSS with table-based layout**  
**Rationale**:
- Maximum compatibility across email clients
- Script can wrap user HTML in standard email template
- Can provide template with inline styles

**Alternatives Considered**:
- External CSS: Rejected - many email clients block external stylesheets
- Modern CSS (flexbox, grid): Rejected - poor support in email clients

**Implementation Notes**:
- Provide optional email template wrapper with inline styles
- Validate HTML (basic checks for XSS, malformed tags)
- Support both raw HTML and template-wrapped HTML

---

### 5. Config File Validation Approach

**Question**: How should we validate the config file structure and content?

**Research**:
- Pydantic models: Type-safe, automatic validation, clear error messages
- Manual validation: More flexible but error-prone
- JSON Schema: Standard but requires separate schema file

**Decision**: **Pydantic models**  
**Rationale**:
- Matches existing codebase patterns (already uses Pydantic)
- Type-safe config parsing
- Clear validation errors for developers
- Can generate example config from model

**Alternatives Considered**:
- Manual validation: Rejected - error-prone, harder to maintain
- JSON Schema: Rejected - adds complexity, Pydantic is sufficient

**Implementation Notes**:
- Create `UpdateEmailConfig` Pydantic model
- Fields: `subject`, `body_html`, `screenshots` (list of paths), `test_mode` (bool)
- Validate file paths exist and are readable
- Validate HTML is not empty, subject is not empty

---

## Technical Decisions Summary

| Decision | Choice | Rationale |
|----------|--------|------------|
| Config Format | YAML | Better multi-line support for HTML |
| Screenshot Embedding | Inline (CID) | Better UX, standard practice |
| Rate Limiting | Batch with delay | Respects AWS SES limits |
| HTML Email | Inline CSS, table layout | Maximum compatibility |
| Validation | Pydantic models | Type-safe, matches codebase |

## Dependencies to Add

- `pyyaml`: For YAML config file parsing (if not already present)
- `Pillow`: For image validation/sizing (optional, but recommended)

## Open Questions (Resolved)

All technical unknowns have been resolved. Ready to proceed to Phase 1 design.

