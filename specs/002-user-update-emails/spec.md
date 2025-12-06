# Feature Specification: User Update Emails

**Feature Branch**: `002-user-update-emails`  
**Created**: 2025-01-27  
**Status**: Draft  
**Input**: User description: "I want to somehow send updates to all current users of the alexstocks. My idea is to somehow easily being able to write some new things that were added (or even automatically generate it from the recents features implmented) and conduct a cool email with update urging the users check it and share with others. I need to be able to somehow send screenshots as well, and for test to be ablt to send it to test user only. this are going to be one time things I mean adhoc updates every time a different email on a different time with updates that were recently added."

## Clarifications

### Session 2025-01-27

- Q: How should the system determine who can create and send update emails? → A: This is a developer/admin tool (script or CLI), not a user-facing platform feature. Only developers have access to create and send update emails. Users only receive emails and do not interact with any feature.
- Q: What form should this tool take? → A: Python script with config file (YAML/JSON config)
- Q: How should screenshots be specified in the config file? → A: File paths to local image files (relative or absolute paths)
- Q: What format should developers use for the email body content in the config file? → A: Plain HTML (write HTML directly in config)
- Q: How should the preview be displayed to developers? → A: Send to test_email to preview (test mode serves as preview mechanism)

## User Scenarios & Testing *(mandatory)*

### User Story 1 - Create and Send Ad-Hoc Update Emails (Priority: P1)

As a developer, I want to create and send one-time update emails to all current users via a Python script with a config file, so that I can inform users about new features and improvements, encouraging them to check the platform and share it with others.

**Why this priority**: This is the core functionality - without the ability to create and send update emails, none of the other features matter. It enables direct communication with users about product improvements.

**Independent Test**: Can be fully tested by creating an update email with text content, specifying recipients (all users or test user), and verifying the email is sent successfully. Delivers value by enabling product communication with users.

**Acceptance Scenarios**:

1. **Given** I have a config file (YAML/JSON) with email subject, body, and recipient settings, **When** I run the Python script with the config file, **Then** the system sends the email to all active, non-deleted users with verified email addresses
2. **Given** I have prepared a config file with email content, **When** I run the script with test_mode enabled, **Then** I receive the email at the test email address to preview how it will appear to recipients
3. **Given** I have sent an update email via the script, **When** the script completes, **Then** I can see how many emails were sent successfully and if any failed
4. **Given** I want to send an update email, **When** I set "test_mode: true" in the config file, **Then** the email is sent only to the configured test user email address

---

### User Story 2 - Include Screenshots in Update Emails (Priority: P2)

As a developer, I want to include screenshots in update emails, so that I can visually demonstrate new features and improvements to users.

**Why this priority**: Screenshots significantly enhance the effectiveness of update emails by providing visual context. While not strictly required for MVP, they are essential for creating compelling update communications.

**Independent Test**: Can be fully tested by creating an update email, attaching one or more screenshot images, and verifying the images are embedded correctly in the sent email. Delivers value by making update emails more engaging and informative.

**Acceptance Scenarios**:

1. **Given** I have a config file with screenshot file paths, **When** I run the script, **Then** the images are read from the file paths and embedded in the email body, displayed correctly to recipients
2. **Given** I have specified screenshots in the config file, **When** I run the script with test_mode enabled, **Then** I receive the email at the test email address and can see how the screenshots will appear in the final email
3. **Given** I want to include screenshots, **When** I specify file paths to images in common formats (PNG, JPG, GIF) in the config, **Then** the system accepts and processes them for email inclusion
4. **Given** I have included screenshot file paths in the config, **When** the email is sent, **Then** recipients receive the email with images displayed inline or as attachments

---

### User Story 3 - Auto-Generate Update Content from Recent Features (Priority: P3)

As a developer, I want the system to automatically generate update content from recently implemented features, so that I can quickly create update emails without manually writing all content.

**Why this priority**: This is a convenience feature that reduces manual work. While valuable, it's not essential for the core functionality - manual content creation can always be used as a fallback.

**Independent Test**: Can be fully tested by triggering the auto-generation feature and verifying it produces draft content based on recent feature implementations. Delivers value by reducing time needed to create update emails.

**Acceptance Scenarios**:

1. **Given** I want to create an update email, **When** I select "auto-generate from recent features", **Then** the system creates draft email content summarizing recently implemented features
2. **Given** the system has auto-generated update content, **When** I review the generated content, **Then** I can edit, modify, or replace it before sending
3. **Given** I want to auto-generate content, **When** I specify a time range (e.g., "last 30 days"), **Then** the system includes features implemented within that timeframe

---

### Edge Cases

- What happens when there are no active users to send to?
- How does the system handle users with unverified or bounced email addresses?
- What happens if an email send fails for some users but succeeds for others?
- How does the system handle very large numbers of recipients (e.g., 10,000+ users)?
- What happens if a screenshot file path is invalid, file doesn't exist, file is too large, or in an unsupported format?
- How does the system handle special characters, malformed HTML, or XSS risks in HTML email content?
- What happens if the test user email address is not configured?
- How does the system prevent accidentally sending to all users when test mode was intended?

## Requirements *(mandatory)*

### Functional Requirements

- **FR-001**: System MUST provide a Python script that accepts a config file (YAML/JSON) with email subject, body content, and settings
- **FR-002**: System MUST support sending update emails to all active, non-deleted users with verified email addresses
- **FR-003**: System MUST support a test mode that sends emails only to a configured test user email address
- **FR-004**: System MUST allow including one or more screenshot images in update emails via file paths (relative or absolute) specified in the config file
- **FR-005**: System MUST support test mode that sends email to test user only, which serves as the preview mechanism (no separate preview mode needed)
- **FR-006**: System MUST track and report email send status (successful sends, failures, total recipients)
- **FR-007**: System MUST exclude users with bounced email addresses from recipient lists
- **FR-008**: System MUST exclude soft-deleted users from recipient lists
- **FR-009**: System MUST support HTML email formatting - email body content in config file is written as HTML and sent as-is
- **FR-010**: System MUST log all update email sends with metadata (timestamp, recipient count, sender, content summary)
- **FR-011**: System MUST allow editing email content before final send confirmation
- **FR-012**: System MUST validate email content (subject and body) before allowing send
- **FR-013**: System MUST support auto-generating draft email content from recently implemented features (optional enhancement)
- **FR-014**: System MUST handle email send failures gracefully, continuing to send to remaining recipients if some fail
- **FR-015**: System MUST respect email rate limits and provider constraints when sending to large recipient lists

### Key Entities *(include if feature involves data)*

- **UpdateEmail**: Represents a one-time update email campaign with subject, body content, screenshots, send status, recipient list, and metadata (created timestamp, sent timestamp, sender)
- **EmailRecipient**: Represents a user who should receive an update email, with status tracking (pending, sent, failed)

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: Developers can create a config file and send an update email to all users in under 5 minutes using the Python script
- **SC-002**: System successfully delivers update emails to 95% of intended recipients
- **SC-003**: Update emails with screenshots render correctly across major email clients (Gmail, Outlook, Apple Mail)
- **SC-004**: Test mode allows sending to test user only for preview purposes, preventing accidental sends to all users
- **SC-005**: System can handle sending update emails to up to 10,000 users without system degradation
- **SC-006**: Test mode email accurately represents final email appearance (test email serves as preview)
- **SC-007**: Auto-generation feature (if implemented) produces usable draft content in under 30 seconds

## Assumptions

- Email service infrastructure (AWS SES) is already configured and operational
- Test user email address is configured in system settings
- Users have verified email addresses before being eligible to receive update emails
- This is a developer/admin tool (Python script with config file), not a user-facing platform feature. Only developers have access to create and send update emails
- The tool is a Python script that reads email content and settings from a YAML or JSON config file
- Screenshot images are provided as file paths in the config file and will be read and embedded directly in emails (not requiring permanent storage beyond the source files)
- Update emails are one-time sends (not scheduled or recurring)
- Email body content is written as HTML directly in the config file and sent as HTML email
- System will use existing email service infrastructure for actual email delivery

## Dependencies

- Existing email service infrastructure (EmailService, SESEmailService)
- User repository for retrieving active users
- Email template service for HTML email formatting
- Configuration system for test user email address

## Out of Scope

- Scheduled or recurring update emails
- Email analytics beyond basic send status (open rates, click rates)
- User preferences for receiving update emails (all users receive all updates)
- Email templates or saved drafts for reuse
- A/B testing of email content
- Personalization of update emails per user
- Unsubscribe functionality for update emails (users can unsubscribe from all emails via existing mechanisms)
