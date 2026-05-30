"""Log-template anomaly detector (Drain3).

Mines historical failure messages into templates with the Drain3 streaming
log parser, then flags the current run if its failure message produces a
template that hasn't been seen before in the same pipeline's history.

This is the "have we seen this error pattern before?" signal — a strong
predictor of a genuinely new failure mode rather than a known one. Useful
because the LLM RCA's first-cited similar incident depends on the failure
pattern being familiar; a novel pattern means RAG retrieval will be weak
and the human probably wants a different fix process.
"""

from __future__ import annotations

from typing import Any

from dataforge.contracts.incident import (
    AnomalySignal,
    AnomalyType,
    Finding,
    Severity,
)
from dataforge.contracts.telemetry import PipelineRun
from dataforge.modules.observability.detectors import DetectorThresholds
from dataforge.modules.observability.ml.detector import MLDetectorError


def _message_for(run: PipelineRun) -> str | None:
    if run.failure is None:
        return None
    msg = run.failure.message or ""
    cls = run.failure.error_class or ""
    composed = f"{cls}: {msg}".strip(": ").strip()
    return composed or None


class LogTemplateDetector:
    """Drain3 log-template miner."""

    name = "drain3_log_template"

    def __init__(
        self,
        *,
        requires_history: int = 20,
        novel_template_size: int = 1,
    ) -> None:
        self.requires_history = requires_history
        self.novel_template_size = novel_template_size

    def detect(
        self,
        run: PipelineRun,
        history: list[PipelineRun],
        thresholds: DetectorThresholds,
    ) -> Finding | None:
        del thresholds  # detector is parameter-free at threshold layer
        current_msg = _message_for(run)
        if current_msg is None:
            return None  # no failure message -> nothing to template

        peer_msgs = [_message_for(h) for h in history if h.app_name == run.app_name]
        peers = [m for m in peer_msgs if m]
        if len(peers) < self.requires_history:
            return None

        miner = self._build_miner()
        for msg in peers:
            miner.add_log_message(msg)

        # Query whether the current message matches an existing template.
        result = miner.match(current_msg)
        if result is not None and getattr(result, "size", 0) > self.novel_template_size:
            return None  # familiar template — no anomaly

        # Either no match, or match into a singleton template ⇒ novel pattern.
        return Finding(
            anomaly_type=AnomalyType.NOVEL_FAILURE_PATTERN,
            severity=Severity.HIGH,
            title="Novel failure pattern not seen in recent history",
            description=(
                f"The failure message produced a log template not previously "
                f"seen in the last {len(peers)} runs of '{run.app_name}'. "
                "RAG retrieval over historical incidents will likely be weak "
                "for this pattern; expect lower-confidence RCA."
            ),
            signals=[
                AnomalySignal(
                    name="message_excerpt",
                    value=1.0,
                    detail=current_msg[:200],
                ),
                AnomalySignal(
                    name="peer_messages_considered",
                    value=float(len(peers)),
                ),
            ],
        )

    def _build_miner(self) -> Any:
        try:
            from drain3 import TemplateMiner
            from drain3.template_miner_config import TemplateMinerConfig
        except ImportError as exc:  # pragma: no cover - dep gated
            raise MLDetectorError(
                "drain3 not installed. Install dataforge with the [ml] extra "
                "to enable the LogTemplate detector."
            ) from exc

        config = TemplateMinerConfig()
        # Drain3's defaults are sensible; explicit zero-config keeps the
        # template miner deterministic across runs.
        return TemplateMiner(config=config)
