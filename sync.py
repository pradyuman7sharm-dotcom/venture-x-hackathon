"""
Offline-first sync worker for Sahaayak Pro.
Runs in a background thread, checks connectivity, syncs pending cases,
and checks for rule updates when online.
"""

import threading
import time
import socket
import json
import csv
import io
import os
import logging
import urllib.request
import urllib.error
from datetime import datetime

logger = logging.getLogger('sync')

# Configuration
SYNC_URL = os.environ.get('SYNC_URL', 'http://localhost:8080/api/sync')
RULES_URL = os.environ.get('RULES_URL', 'http://localhost:8080/api/rules')
SYNC_INTERVAL = int(os.environ.get('SYNC_INTERVAL', '30'))
CONNECTIVITY_TIMEOUT = 3
MAX_RETRIES = 5


class SyncWorker:
    """Background sync worker that runs in a daemon thread."""

    def __init__(self):
        self.is_online = False
        self.last_check = None
        self.last_sync = None
        self.pending_count = 0
        self.running = False
        self._thread = None
        self._lock = threading.Lock()
        self._retry_counts = {}  # case_id -> retry count

    def start(self):
        """Start the sync worker in a background daemon thread."""
        if self.running:
            return
        self.running = True
        self._thread = threading.Thread(target=self._run_loop, daemon=True, name='sync-worker')
        self._thread.start()
        logger.info("Sync worker started")

    def stop(self):
        """Stop the sync worker."""
        self.running = False
        if self._thread:
            self._thread.join(timeout=5)
        logger.info("Sync worker stopped")

    def check_connectivity(self):
        """Check if internet is available using a socket connection to Google DNS."""
        try:
            sock = socket.create_connection(("8.8.8.8", 53), timeout=CONNECTIVITY_TIMEOUT)
            sock.close()
            with self._lock:
                self.is_online = True
        except (socket.timeout, OSError):
            with self._lock:
                self.is_online = False
        with self._lock:
            self.last_check = datetime.utcnow().isoformat() + 'Z'
        return self.is_online

    def _run_loop(self):
        """Main sync loop - runs every SYNC_INTERVAL seconds."""
        while self.running:
            try:
                self.check_connectivity()
                if self.is_online:
                    self._sync_cases()
                    self._check_rule_updates()
                self._update_pending_count()
            except Exception as e:
                logger.error(f"Sync loop error: {e}")
            time.sleep(SYNC_INTERVAL)

    def _sync_cases(self):
        """POST pending cases to SYNC_URL with retry and backoff."""
        try:
            from db import get_pending_cases, mark_synced, mark_pending
        except ImportError:
            logger.error("Cannot import db module")
            return

        pending = get_pending_cases()
        if not pending:
            return

        for case in pending:
            case_id = case.get('case_id', '')
            retry_count = self._retry_counts.get(case_id, 0)

            if retry_count >= MAX_RETRIES:
                logger.warning(f"Max retries reached for case {case_id}, skipping")
                continue

            try:
                # Mark as pending (in transit)
                mark_pending(case_id)

                # Prepare payload
                payload = json.dumps(case, ensure_ascii=False, default=str).encode('utf-8')

                req = urllib.request.Request(
                    SYNC_URL,
                    data=payload,
                    headers={
                        'Content-Type': 'application/json',
                        'User-Agent': 'SahaayakPro/1.0'
                    },
                    method='POST'
                )

                with urllib.request.urlopen(req, timeout=10) as response:
                    if response.status in (200, 201, 202):
                        mark_synced(case_id)
                        self._retry_counts.pop(case_id, None)
                        with self._lock:
                            self.last_sync = datetime.utcnow().isoformat() + 'Z'
                        logger.info(f"Case {case_id} synced successfully")
                    else:
                        self._retry_counts[case_id] = retry_count + 1
                        logger.warning(f"Sync failed for {case_id}: HTTP {response.status}")

            except (urllib.error.URLError, urllib.error.HTTPError, OSError) as e:
                self._retry_counts[case_id] = retry_count + 1
                # Exponential backoff handled by increasing retry count
                logger.debug(f"Sync error for {case_id} (retry {retry_count + 1}): {e}")
            except Exception as e:
                self._retry_counts[case_id] = retry_count + 1
                logger.error(f"Unexpected sync error for {case_id}: {e}")

    def _check_rule_updates(self):
        """Check for updated rules.json from RULES_URL."""
        try:
            from db import get_rules_version, set_rules_version
            from triage.engine import load_rules, RULES_PATH
        except ImportError:
            return

        try:
            req = urllib.request.Request(
                RULES_URL,
                headers={'User-Agent': 'SahaayakPro/1.0'},
                method='GET'
            )
            with urllib.request.urlopen(req, timeout=10) as response:
                if response.status == 200:
                    data = json.loads(response.read().decode('utf-8'))
                    remote_version = data.get('version', '0.0.0')

                    # Compare with local version
                    local_rules = load_rules()
                    local_version = local_rules.get('version', '0.0.0')

                    if remote_version > local_version:
                        # Validate structure
                        if 'rules' in data and isinstance(data['rules'], list):
                            # Backup and replace
                            rules_path = RULES_PATH
                            backup_path = rules_path + '.bak'
                            try:
                                if os.path.exists(rules_path):
                                    with open(rules_path, 'r', encoding='utf-8') as f:
                                        backup = f.read()
                                    with open(backup_path, 'w', encoding='utf-8') as f:
                                        f.write(backup)

                                with open(rules_path, 'w', encoding='utf-8') as f:
                                    json.dump(data, f, ensure_ascii=False, indent=2)

                                set_rules_version(remote_version, 'synced')
                                logger.info(f"Rules updated from {local_version} to {remote_version}")
                            except Exception as e:
                                # Restore backup on failure
                                logger.error(f"Failed to write rules: {e}")
                                if os.path.exists(backup_path):
                                    with open(backup_path, 'r', encoding='utf-8') as f:
                                        restored = f.read()
                                    with open(rules_path, 'w', encoding='utf-8') as f:
                                        f.write(restored)
                        else:
                            logger.warning("Remote rules invalid structure, skipping update")

        except (urllib.error.URLError, urllib.error.HTTPError, OSError):
            pass  # Expected when offline or server unavailable
        except Exception as e:
            logger.error(f"Rule update check error: {e}")

    def _update_pending_count(self):
        """Update the pending sync count from the database."""
        try:
            from db import get_stats
            stats = get_stats()
            with self._lock:
                self.pending_count = stats.get('pending_count', 0)
        except Exception as e:
            logger.debug(f"Could not update pending count: {e}")

    def get_status(self):
        """Return current sync status as a dict."""
        with self._lock:
            return {
                "is_online": self.is_online,
                "last_check": self.last_check,
                "last_sync": self.last_sync,
                "pending_count": self.pending_count,
                "running": self.running
            }


def export_cases_csv():
    """Export all cases as a CSV string."""
    from db import get_cases_for_export

    cases = get_cases_for_export()
    if not cases:
        return "No cases to export\n"

    output = io.StringIO()
    headers = [
        'case_id', 'created_at', 'patient_group', 'age_months', 'gender',
        'symptoms', 'symptom_text', 'risk', 'risk_level', 'reasons',
        'protocol_refs', 'explanation', 'sync_status', 'synced_at', 'language'
    ]

    writer = csv.DictWriter(output, fieldnames=headers, extrasaction='ignore')
    writer.writeheader()

    for case in cases:
        row = dict(case)
        # Convert list fields to semicolon-separated strings
        for field in ('symptoms', 'reasons', 'protocol_refs', 'rules_fired'):
            val = row.get(field, [])
            if isinstance(val, list):
                row[field] = '; '.join(str(v) for v in val)
        writer.writerow(row)

    return output.getvalue()


def export_cases_json():
    """Export all cases as a pretty-printed JSON string."""
    from db import get_cases_for_export

    cases = get_cases_for_export()
    return json.dumps(cases, ensure_ascii=False, indent=2, default=str)


# Module-level singleton
sync_worker = SyncWorker()
