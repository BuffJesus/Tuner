from __future__ import annotations

import json
from dataclasses import asdict

from tuner.services.evidence_replay_service import EvidenceReplaySnapshot


class EvidenceReplayFormatterService:
    def to_text(self, snapshot: EvidenceReplaySnapshot) -> str:
        lines = [
            f"Captured: {snapshot.captured_at.isoformat()}",
            f"Session: {snapshot.session_state}",
            snapshot.connection_text,
            snapshot.source_text,
            snapshot.sync_summary_text,
            snapshot.staged_summary_text,
            f"Operations: {snapshot.operation_session_count} session(s)",
        ]
        if snapshot.latest_write_text:
            lines.append(f"Latest write: {snapshot.latest_write_text}")
        if snapshot.latest_burn_text:
            lines.append(f"Latest burn: {snapshot.latest_burn_text}")
        if snapshot.sync_mismatch_details:
            lines.extend(f"Sync mismatch: {detail}" for detail in snapshot.sync_mismatch_details)
        lines.append(snapshot.runtime_summary_text)
        lines.append(f"Runtime channels captured: {snapshot.runtime_channel_count}")
        if snapshot.runtime_channels:
            lines.append("Runtime values:")
            lines.extend(
                f"  {item.name} = {item.value}{f' {item.units}' if item.units else ''}"
                for item in snapshot.runtime_channels
            )
        lines.append("")
        lines.append("Evidence Summary:")
        lines.append(snapshot.evidence_summary_text)
        lines.append("")
        lines.append("Operation Evidence:")
        lines.append(snapshot.operation_summary_text)
        return "\n".join(lines)

    def to_json(self, snapshot: EvidenceReplaySnapshot) -> str:
        payload = asdict(snapshot)
        payload["captured_at"] = snapshot.captured_at.isoformat()
        return json.dumps(payload, indent=2, sort_keys=True)
