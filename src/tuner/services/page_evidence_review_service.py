from __future__ import annotations

from dataclasses import dataclass

from tuner.services.evidence_replay_service import EvidenceReplayChannel, EvidenceReplaySnapshot


@dataclass(slots=True, frozen=True)
class PageEvidenceReviewSnapshot:
    summary_text: str
    detail_text: str
    relevant_channels: tuple[EvidenceReplayChannel, ...]


class PageEvidenceReviewService:
    _BASE_CHANNEL_KEYS = ("rpm", "map", "tps", "batt")
    _FAMILY_CHANNEL_KEYS = {
        "fuel-trims": ("afr", "lambda", "ego", "pw"),
        "fuel-tables": ("afr", "lambda", "ego", "pw"),
        "spark-tables": ("advance", "dwell", "knock", "sync", "rsa_fullsync"),
        "target-tables": ("afr", "lambda", "ego"),
        "vvt": ("advance", "sync", "rpm", "map"),
    }
    _GROUP_CHANNEL_KEYS = {
        "fuel": ("afr", "lambda", "ego", "pw"),
        "ignition": ("advance", "dwell", "knock", "sync", "rsa_fullsync"),
        "idle": ("clt", "iat", "idle"),
        "hardware_setup": ("clt", "iat", "afr", "lambda", "baro", "oil"),
    }
    _PARAMETER_CHANNEL_KEYS = {
        "reqfuel": ("rpm", "map", "pw"),
        "ve": ("rpm", "map", "afr", "lambda", "ego"),
        "fuel": ("rpm", "map", "afr", "lambda", "ego", "pw"),
        "afr": ("rpm", "map", "afr", "lambda", "ego"),
        "lambda": ("rpm", "map", "afr", "lambda", "ego"),
        "ego": ("rpm", "map", "afr", "lambda", "ego"),
        "injector": ("rpm", "map", "pw", "afr", "lambda"),
        "inj": ("rpm", "map", "pw", "afr", "lambda"),
        "spark": ("rpm", "map", "advance", "dwell", "knock", "sync", "rsa_fullsync"),
        "ign": ("rpm", "map", "advance", "dwell", "knock", "sync", "rsa_fullsync"),
        "dwell": ("rpm", "batt", "dwell"),
        "knock": ("rpm", "map", "advance", "knock", "sync", "rsa_fullsync"),
        "trigger": ("rpm", "sync", "rsa_fullsync", "advance"),
        "idle": ("rpm", "map", "tps", "clt", "iat", "idle"),
        "clt": ("clt", "rpm", "batt"),
        "iat": ("iat", "rpm", "batt"),
        "map": ("map", "rpm", "baro"),
        "baro": ("baro", "map", "rpm"),
        "oil": ("oil", "rpm", "batt"),
    }

    def build(
        self,
        *,
        page_title: str,
        parameter_names: tuple[str, ...] = (),
        page_id: str | None = None,
        group_id: str | None = None,
        page_family_id: str | None = None,
        evidence_hints: tuple[str, ...] = (),
        evidence_snapshot: EvidenceReplaySnapshot | None,
    ) -> PageEvidenceReviewSnapshot | None:
        if evidence_snapshot is None:
            return None
        relevant_channels = self._select_channels(
            page_title=page_title,
            parameter_names=parameter_names,
            page_id=page_id,
            group_id=group_id,
            page_family_id=page_family_id,
            evidence_hints=evidence_hints,
            runtime_channels=evidence_snapshot.runtime_channels,
        )
        if not relevant_channels:
            return PageEvidenceReviewSnapshot(
                summary_text="Evidence review: latest captured bundle has no page-relevant runtime channels.",
                detail_text=evidence_snapshot.evidence_summary_text,
                relevant_channels=(),
            )
        channel_text = " | ".join(
            f"{item.name}={item.value}{f' {item.units}' if item.units else ''}"
            for item in relevant_channels
        )
        age_text = (
            self._format_age(evidence_snapshot.runtime_age_seconds)
            if evidence_snapshot.runtime_age_seconds is not None
            else "age unknown"
        )
        summary = (
            f"Evidence review: latest capture for '{page_title}' exposes {len(relevant_channels)} relevant channel(s)"
            f" from {age_text} ago."
        )
        detail_lines = [
            summary,
            f"Relevant channels: {channel_text}",
        ]
        if evidence_snapshot.latest_write_text:
            detail_lines.append(f"Latest write: {evidence_snapshot.latest_write_text}")
        if evidence_snapshot.latest_burn_text:
            detail_lines.append(f"Latest burn: {evidence_snapshot.latest_burn_text}")
        if evidence_snapshot.sync_mismatch_details:
            detail_lines.extend(f"Sync mismatch: {detail}" for detail in evidence_snapshot.sync_mismatch_details)
        return PageEvidenceReviewSnapshot(
            summary_text=summary,
            detail_text="\n".join(detail_lines),
            relevant_channels=relevant_channels,
        )

    def _select_channels(
        self,
        *,
        page_title: str,
        parameter_names: tuple[str, ...],
        page_id: str | None,
        group_id: str | None,
        page_family_id: str | None,
        evidence_hints: tuple[str, ...],
        runtime_channels: tuple[EvidenceReplayChannel, ...],
    ) -> tuple[EvidenceReplayChannel, ...]:
        keys = self._channel_keys(
            page_title=page_title,
            parameter_names=parameter_names,
            page_id=page_id,
            group_id=group_id,
            page_family_id=page_family_id,
            evidence_hints=evidence_hints,
        )
        selected: list[EvidenceReplayChannel] = []
        seen: set[str] = set()
        for channel in runtime_channels:
            normalized = channel.name.lower()
            if normalized in seen:
                continue
            if any(key in normalized for key in keys):
                selected.append(channel)
                seen.add(normalized)
        return tuple(selected[:6])

    def _channel_keys(
        self,
        *,
        page_title: str,
        parameter_names: tuple[str, ...],
        page_id: str | None,
        group_id: str | None,
        page_family_id: str | None,
        evidence_hints: tuple[str, ...],
    ) -> tuple[str, ...]:
        ordered: list[str] = list(self._BASE_CHANNEL_KEYS)
        if page_family_id and page_family_id in self._FAMILY_CHANNEL_KEYS:
            for key in self._FAMILY_CHANNEL_KEYS[page_family_id]:
                if key not in ordered:
                    ordered.append(key)
        if group_id and group_id in self._GROUP_CHANNEL_KEYS:
            for key in self._GROUP_CHANNEL_KEYS[group_id]:
                if key not in ordered:
                    ordered.append(key)
        normalized_tokens = self._normalized_tokens(page_title, page_id, parameter_names, evidence_hints)
        for token in normalized_tokens:
            for hint_key, channels in self._PARAMETER_CHANNEL_KEYS.items():
                if hint_key in token:
                    for channel in channels:
                        if channel not in ordered:
                            ordered.append(channel)
        return tuple(ordered)

    @staticmethod
    def _normalized_tokens(
        page_title: str,
        page_id: str | None,
        parameter_names: tuple[str, ...],
        evidence_hints: tuple[str, ...],
    ) -> tuple[str, ...]:
        raw = " ".join(
            item for item in (page_title, page_id or "", *parameter_names, *evidence_hints) if item
        ).lower()
        token = []
        tokens: list[str] = []
        for ch in raw:
            if ch.isalnum():
                token.append(ch)
            else:
                if token:
                    tokens.append("".join(token))
                    token.clear()
        if token:
            tokens.append("".join(token))
        return tuple(tokens)

    @staticmethod
    def _format_age(age_seconds: float) -> str:
        rounded = int(round(age_seconds))
        if rounded < 60:
            return f"{rounded}s"
        minutes, seconds = divmod(rounded, 60)
        return f"{minutes}m {seconds}s"
