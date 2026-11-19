#!/usr/bin/env python3
"""Draft approval CLI for Proton Mail processor"""

import json
import sys
from pathlib import Path

DRAFTS_DIR = Path('.proton-drafts')
APPROVED_DIR = DRAFTS_DIR / 'approved'


def list_drafts():
    """List all pending drafts"""
    drafts = list(DRAFTS_DIR.glob('*.json'))
    if not drafts:
        print("No pending drafts")
        return
    
    for draft_file in drafts:
        with open(draft_file, 'r') as f:
            draft = json.load(f)
        print(f"\n[{draft['id']}] {draft['original']['subject']}")
        print(f"Category: {draft['category']}")
        print(f"From: {draft['original']['sender']}")
        print(f"---")
        print(draft['original']['body'][:500])
        print(f"---")


def approve(draft_id):
    """Approve a draft for processing"""
    draft_file = DRAFTS_DIR / f"{draft_id}.json"
    if not draft_file.exists():
        print(f"Draft {draft_id} not found")
        return
    
    from process_proton_mail import ProtonMailProcessor
    processor = ProtonMailProcessor()
    if processor.approve_draft(draft_id):
        print(f"Draft {draft_id} approved")
        processor.spawn_agent(draft_id)
    else:
        print(f"Failed to approve {draft_id}")


def main():
    if len(sys.argv) < 2:
        print("Usage: approve_draft.py [list|approve <draft_id>]")
        return
    
    cmd = sys.argv[1]
    if cmd == 'list':
        list_drafts()
    elif cmd == 'approve' and len(sys.argv) > 2:
        approve(sys.argv[2])
    else:
        print("Usage: approve_draft.py [list|approve <draft_id>]")


if __name__ == '__main__':
    main()
