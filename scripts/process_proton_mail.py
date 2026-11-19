#!/usr/bin/env python3
"""Proton Mail Processor with Draft/Approval Gating"""

import json
import os
import hashlib
import imaplib
import email
from email import policy
from email.parser import BytesParser
from datetime import datetime, timedelta
from pathlib import Path
import requests

PROTON_HOST = os.getenv('PROTON_IMAP_HOST', 'imap.protonmail.ch')
PROTON_PORT = int(os.getenv('PROTON_IMAP_PORT', '993'))
PROTON_USERNAME = os.getenv('PROTON_USERNAME', '')
PROTON_PASSWORD = os.getenv('PROTON_PASSWORD', '')

GITHUB_TOKEN = os.getenv('GITHUB_TOKEN', '')
GITHUB_REPO = os.getenv('GITHUB_REPO', 'metazen11/autonomous-agents')
GITHUB_OWNER = GITHUB_REPO.split('/')[0]
GITHUB_NAME = GITHUB_REPO.split('/')[1]

DRAFTS_DIR = Path('.proton-drafts')
DRAFTS_DIR.mkdir(exist_ok=True)
APPROVED_DIR = DRAFTS_DIR / 'approved'
APPROVED_DIR.mkdir(exist_ok=True)

FILTER_RULES = {
    'urgent': ['urgent', 'asap', 'immediate', 'emergency', 'critical'],
    'support': ['support', 'help', 'issue', 'bug', 'error', 'problem'],
    'feature': ['feature', 'enhancement', 'suggestion', 'idea', 'proposal'],
    'general': []
}


class ProtonMailProcessor:
    def __init__(self):
        self.imap = None
        self.drafts_dir = DRAFTS_DIR
        
    def connect(self):
        try:
            self.imap = imaplib.IMAP4_SSL(PROTON_HOST, PROTON_PORT)
            self.imap.login(PROTON_USERNAME, PROTON_PASSWORD)
            return True
        except Exception as e:
            print(f"Failed to connect: {e}")
            return False
    
    def fetch_emails(self, days_back=7):
        if not self.imap:
            return []
        cutoff = (datetime.now() - timedelta(days=days_back)).strftime('%d-%b-%Y')
        self.imap.search(None, f'(SINCE {cutoff} UNSEEN)')
        messages = self.imap.message(self.imap.uid('EXISTS'))
        return [self._parse(msg, msg_id) for msg_id, msg in messages]
    
    def _parse(self, msg, msg_id):
        subject = msg.get('Subject', 'No Subject')
        sender = msg.get('From', 'Unknown')
        body = ''
        if msg.is_multipart():
            for part in msg.walk():
                if part.get_content_type() == 'text/plain':
                    body = part.get_payload(decode=True).decode('utf-8', errors='ignore')
                    break
        else:
            body = msg.get_payload(decode=True).decode('utf-8', errors='ignore')
        return {'id': msg_id, 'subject': subject, 'sender': sender, 'body': body}
    
    def categorize(self, email_data):
        text = f"{email_data['subject']} {email_data['body']}".lower()
        for cat, keywords in FILTER_RULES.items():
            if any(kw in text for kw in keywords):
                return cat
        return 'general'
    
    def create_draft(self, email_data, response_template=''):
        draft_id = hashlib.md5(str(email_data['id']).encode()).hexdigest()[:8]
        draft_file = self.drafts_dir / f"{draft_id}.json"
        draft = {
            'id': draft_id,
            'original': email_data,
            'category': self.categorize(email_data),
            'response_template': response_template,
            'created_at': datetime.now().isoformat(),
            'status': 'pending_approval'
        }
        with open(draft_file, 'w') as f:
            json.dump(draft, f, indent=2)
        return draft_id
    
    def approve_draft(self, draft_id):
        draft_file = self.drafts_dir / f"{draft_id}.json"
        if not draft_file.exists():
            return False
        with open(draft_file, 'r') as f:
            draft = json.load(f)
        draft['status'] = 'approved'
        draft['approved_at'] = datetime.now().isoformat()
        with open(APPROVED_DIR / f"{draft_id}.json", 'w') as f:
            json.dump(draft, f, indent=2)
        draft_file.unlink()
        return True
    
    def log_to_github(self, email_data):
        if not GITHUB_TOKEN:
            return
        url = f"https://api.github.com/repos/{GITHUB_OWNER}/{GITHUB_NAME}/issues"
        headers = {'Authorization': f'token {GITHUB_TOKEN}', 'Content-Type': 'application/json'}
        issue = {
            'title': f"Email: {email_data['subject'][:50]}",
            'body': f"**From:** {email_data['sender']}\n\n{email_data['body'][:2000]}"
        }
        try:
            resp = requests.post(url, json=issue, headers=headers)
            if resp.status_code == 201:
                print(f"Created GitHub issue: {resp.json()['html_url']}")
        except Exception as e:
            print(f"GitHub error: {e}")
    
    def spawn_agent(self, draft_id):
        approved_file = APPROVED_DIR / f"{draft_id}.json"
        if not approved_file.exists():
            return False
        with open(approved_file, 'r') as f:
            draft = json.load(f)
        print(f"Processing draft {draft_id} via {draft['category']} category")
        return True
    
    def process_all(self):
        if not self.connect():
            return
        self.imap.select('INBOX')
        emails = self.fetch_emails()
        for email_data in emails:
            if email_data:
                draft_id = self.create_draft(email_data)
                print(f"Created draft {draft_id} for {email_data['subject']}")
        self.imap.close()
        self.imap.logout()


def main():
    processor = ProtonMailProcessor()
    processor.process_all()


if __name__ == '__main__':
    main()
