# Proton Mail Workflow with Draft/Approval Gating

## Overview

Automatically fetches Proton Mail emails, categorizes them, creates draft responses for approval, then routes approved drafts through Claude/Codex/Anvil. Unhandled emails log to GitHub issues.

## Components

1. **process_proton_mail.py** - Main email fetcher and categorizer
2. **approve_draft.py** - CLI for reviewing and approving drafts
3. **com.protonmail.processor.plist** - launchd job configuration
4. **install_proton_mail_processor.sh** - Installation script

## Setup

### 1. Configure Environment Variables

Create/edit `.env` file:

```bash
PROTON_USERNAME=your_email@protonmail.com
PROTON_PASSWORD=your_app_password_here
GITHUB_TOKEN=your_github_token_here
GITHUB_REPO=metazen11/autonomous-agents
```

**Important:** Use a Proton Mail app password, not your main password. Generate it from protonmail.com/settings/security.

### 2. Install launchd Job

```bash
chmod +x scripts/install_proton_mail_processor.sh
./scripts/install_proton_mail_processor.sh
```

This will:
- Create/update `.env` file
- Install the launchd plist to `~/Library/LaunchAgents/`
- Load the job (checks every 1 hour)

### 3. Verify Installation

```bash
# List running jobs
launchctl list | grep protonmail

# View logs
tail -f .proton-drafts/processor.log
```

## Workflow

### Email Fetching (Automatic)

Every hour, launchd runs `process_proton_mail.py` which:
1. Connects to Proton Mail IMAP
2. Fetches unread emails from last 7 days
3. Categorizes by content (urgent/support/feature/general)
4. Creates draft files in `.proton-drafts/`
5. Logs unhandled emails to GitHub issues

### Draft Review (Manual Approval)

```bash
# List all pending drafts
python3 scripts/approve_draft.py list

# Approve a specific draft
python3 scripts/approve_draft.py approve <draft_id>
```

### Approved Processing

Once approved:
1. Draft moves to `.proton-drafts/approved/`
2. System logs the draft to GitHub issue if no response template
3. Spawns Claude/Codex/Anvil to generate response
4. You review and send the response manually

## Email Filtering

Emails are automatically categorized:

- **urgent**: Keywords like "urgent", "asap", "emergency"
- **support**: Keywords like "help", "bug", "error", "issue"
- **feature**: Keywords like "suggestion", "enhancement", "idea"
- **general**: Everything else

## Draft Structure

Each draft is a JSON file in `.proton-drafts/`:

```json
{
  "id": "a1b2c3d4",
  "original": {
    "id": "12345",
    "subject": "Bug Report",
    "sender": "user@example.com",
    "body": "..."
  },
  "category": "support",
  "response_template": "",
  "created_at": "2024-01-01T00:00:00",
  "status": "pending_approval"
}
```

## Management Commands

```bash
# Check launchd status
launchctl list | grep protonmail

# Unload the job
launchctl unload ~/Library/LaunchAgents/com.protonmail.processor.plist

# Reload the job
launchctl load ~/Library/LaunchAgents/com.protonmail.processor.plist

# View all drafts (pending + approved)
ls -la .proton-drafts/
ls -la .proton-drafts/approved/
```

## Security Notes

- Store credentials in `.env`, never commit to git
- Use app passwords for Proton Mail
- GitHub token should have repo scope only
- Draft files contain email content - protect `.proton-drafts/` directory

## Troubleshooting

```bash
# Test IMAP connection
python3 -c "
import imaplib
imap = imaplib.IMAP4_SSL('imap.protonmail.ch', 993)
imap.login('your@email.com', 'your_password')
imap.select('INBOX')
print('Connected successfully')
"

# Check draft files
cat .proton-drafts/*.json

# View processor logs
cat .proton-drafts/processor.log
```

## Next Steps

1. Generate Proton Mail app password
2. Create `.env` with your credentials
3. Run installation script
4. Review first drafts that appear
5. Customize filtering rules in `process_proton_mail.py` if needed
