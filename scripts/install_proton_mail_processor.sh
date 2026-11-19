#!/bin/bash
# Install Proton Mail Processor with launchd

set -e

REPO_ROOT="$PWD"
HOME_DIR="$HOME"

# Create .env file if not exists
if [ ! -f .env ]; then
    echo "Creating .env file..."
    cat > .env << 'EOF'
# Proton Mail Configuration
PROTON_IMAP_HOST=imap.protonmail.ch
PROTON_IMAP_PORT=993
PROTON_USERNAME=your_email@protonmail.com
PROTON_PASSWORD=your_app_password_here

# GitHub Configuration
GITHUB_TOKEN=your_github_token_here
GITHUB_REPO=metazen11/autonomous-agents
EOF
    echo "Please edit .env with your credentials"
fi

# Install launchd plist
PLIST_FILE="$REPO_ROOT/com.protonmail.processor.plist"
USER_PLIST="$HOME/Library/LaunchAgents/com.protonmail.processor.plist"

# Update plist with actual paths
sed -i '' "s|/Users/mz/_CODING/autonomous_agents_mds|$REPO_ROOT|g" "$PLIST_FILE" 2>/dev/null || \
    sed -i "s|/Users/mz/_CODING/autonomous_agents_mds|$REPO_ROOT|g" "$PLIST_FILE"

sed -i '' "s|YOUR_PROTON_EMAIL|$PROTON_USERNAME|g" "$PLIST_FILE" 2>/dev/null || \
    sed -i "s|YOUR_PROTON_EMAIL|$PROTON_USERNAME|g" "$PLIST_FILE"

cp "$PLIST_FILE" "$USER_PLIST"

# Load launchd job
launchctl load "$USER_PLIST"

echo "✓ Proton Mail processor installed"
echo "✓ Launchd job loaded (checks every 1 hour)"
echo ""
echo "To manage:"
echo "  launchctl list | grep protonmail"
echo "  launchctl unload ~/Library/LaunchAgents/com.protonmail.processor.plist"
echo ""
echo "To view drafts:"
echo "  python3 scripts/approve_draft.py list"
echo ""
echo "To approve a draft:"
echo "  python3 scripts/approve_draft.py approve <draft_id>"
