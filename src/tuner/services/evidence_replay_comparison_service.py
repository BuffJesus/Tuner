from __future__ import annotations

from dataclasses import dataclass

from tuner.services.evidence_replay_service import EvidenceReplaySnapshot


@dataclass(slots=True, frozen=True)
class EvidenceReplayChannelDelta:
    name: str
    previous_value: float
    current_value: float
    delta_value: float
    units: str | None = None


@dataclass(slots=True, frozen=True)
class EvidenceReplayComparisonSnapshot:
    summary_text: str
    detail_text: str
    changed_channels: tuple[EvidenceReplayChannelDelta, ...]


class EvidenceReplayComparisonService:
    def build(
        self,
        *,
        baseline_snapshot: EvidenceReplaySnapshot | None,
        current_snapshot: EvidenceReplaySnapshot | None,
        relevant_channel_names: tuple[str, ...] = (),
    ) -> EvidenceReplayComparisonSnapshot | None:
        if baseline_snapshot is None or current_snapshot is None:
            return None
        if baseline_snapshot == current_snapshot:
            return None
        baseline_channels = {item.name.lower(): item for item in baseline_snapshot.runtime_channels}
        current_channels = {item.name.lower(): item for item in current_snapshot.runtime_channels}
        requested = tuple(dict.fromkeys(name.lower() for name in relevant_channel_names if name))
        if not requested:
            requested = tuple(current_channels.keys())
        deltas: list[EvidenceReplayChannelDelta] = []
        for key in requested:
            baseline = baseline_channels.get(key)
            current = current_channels.get(key)
            if baseline is None or current is None:
                continue
            delta = current.value - baseline.value
            if abs(delta) < 1e-9:
                continue
            deltas.append(
                EvidenceReplayChannelDelta(
                    name=current.name,
                    previous_value=baseline.value,
                    current_value=current.value,
                    delta_value=delta,
                    units=current.units or baseline.units,
                )
            )
        if not deltas:
            return None
        top_deltas = tuple(sorted(deltas, key=lambda item: abs(item.delta_value), reverse=True)[:4])
        delta_text = " | ".join(
            f"{item.name} {item.delta_value:+.1f}{f' {item.units}' if item.units else ''}"
            for item in top_deltas
        )
        summary = "Comparison vs latest capture highlights runtime drift on this page."
        detail = (
            f"{summary}\n"
            f"Channel deltas: {delta_text}"
        )
        return EvidenceReplayComparisonSnapshot(
            summary_text=summary,
            detail_text=detail,
            changed_channels=top_deltas,
        )
