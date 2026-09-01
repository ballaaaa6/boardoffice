from __future__ import annotations

"""Bind the runtime presentation loop to an application's frame callbacks.

The repository intentionally does not own a windowing toolkit or a game UI.
``RuntimePresentationLoop`` therefore remains the stateful simulation/render
seam, while :class:`RuntimePresentationHostAdapter` is the small, explicit
boundary an external app can call from its own participant loop.  A host
performs one ``tick`` per frame, receives the complete frame result through a
single callback, and may separately consume the ordered runtime events.

This adapter does not advance Central a second time, does not mutate the
returned snapshot, and rejects re-entrant frame calls.  Callback failures are
reported as host-boundary errors; the loop's already-rendered frame remains
the current frame so the host can decide whether to retry or show its own
fallback UI.
"""

import copy
from typing import Any, Callable

from .runtime_presentation_renderer import (
    RuntimePresentationLoop,
    RuntimePresentationRenderError,
)


class RuntimePresentationHostError(RuntimeError):
    """Raised when the application-facing presentation boundary fails."""


FrameSink = Callable[[dict[str, Any]], None]
EventSink = Callable[[dict[str, Any]], None]


class RuntimePresentationHostAdapter:
    """Call :class:`RuntimePresentationLoop` once for each host frame.

    ``frame_sink`` receives a defensive copy of the complete frame result.
    That result contains the rendered RGBA ``image``, the read-only
    ``presentation`` snapshot, the composed ``runtime_snapshot`` and the
    actor/speech event lists.  ``event_sink`` receives defensive copies of
    ordered events one at a time after the frame has been produced.

    The sinks are optional so a host can simply call :meth:`tick` and consume
    the returned result itself.  ``render_current`` is for an initial draw or
    a redraw that must not advance simulation time.
    """

    def __init__(
        self,
        loop: RuntimePresentationLoop,
        *,
        frame_sink: FrameSink | None = None,
        event_sink: EventSink | None = None,
    ) -> None:
        if not isinstance(loop, RuntimePresentationLoop):
            raise RuntimePresentationHostError(
                "host adapter requires a RuntimePresentationLoop"
            )
        if frame_sink is not None and not callable(frame_sink):
            raise RuntimePresentationHostError("frame_sink must be callable")
        if event_sink is not None and not callable(event_sink):
            raise RuntimePresentationHostError("event_sink must be callable")
        self.loop = loop
        self.frame_sink = frame_sink
        self.event_sink = event_sink
        self._frame_count = 0
        self._last_frame: dict[str, Any] | None = None
        self._in_host_call = False

    @property
    def frame_count(self) -> int:
        """Number of successful simulation ticks presented by this adapter."""
        return self._frame_count

    @property
    def last_frame(self) -> dict[str, Any] | None:
        """Return a defensive copy of the last produced frame, if any."""
        return copy.deepcopy(self._last_frame) if self._last_frame is not None else None

    @staticmethod
    def _copy_frame(frame: dict[str, Any]) -> dict[str, Any]:
        """Copy a frame before exposing it to an application callback."""
        return copy.deepcopy(frame)

    def _present(self, frame: dict[str, Any], *, dispatch_events: bool = True) -> None:
        """Send one frame and its ordered events to the configured sinks."""
        if self.frame_sink is not None:
            try:
                self.frame_sink(self._copy_frame(frame))
            except Exception as exc:
                if isinstance(exc, RuntimePresentationHostError):
                    raise
                raise RuntimePresentationHostError(
                    "frame_sink failed while presenting a runtime frame"
                ) from exc
        if dispatch_events and self.event_sink is not None:
            for event in frame.get("events", []):
                try:
                    self.event_sink(copy.deepcopy(event))
                except Exception as exc:
                    if isinstance(exc, RuntimePresentationHostError):
                        raise
                    raise RuntimePresentationHostError(
                        "event_sink failed while dispatching a runtime event"
                    ) from exc

    def render_current(self, *, at_ms: int | None = None) -> dict[str, Any]:
        """Present the current frame without advancing either runtime clock."""
        if self._in_host_call:
            raise RuntimePresentationHostError("host presentation calls are not re-entrant")
        self._in_host_call = True
        try:
            try:
                frame = self.loop.render_current(at_ms=at_ms)
            except Exception as exc:
                raise RuntimePresentationHostError(
                    "host could not render the current runtime frame"
                ) from exc
            self._last_frame = self._copy_frame(frame)
            self._present(frame, dispatch_events=False)
            return frame
        finally:
            self._in_host_call = False

    def tick(
        self,
        elapsed_ms: int,
        *,
        actor_commands=None,
        speech_commands=None,
        at_ms: int | None = None,
    ) -> dict[str, Any]:
        """Advance Central exactly once, present one frame, and return it."""
        if self._in_host_call:
            raise RuntimePresentationHostError("host presentation calls are not re-entrant")
        self._in_host_call = True
        try:
            try:
                frame = self.loop.tick(
                    elapsed_ms,
                    actor_commands=actor_commands,
                    speech_commands=speech_commands,
                    at_ms=at_ms,
                )
            except Exception as exc:
                # Preserve the loop's stable error boundary while adding the
                # application-facing context.  The loop itself is
                # transactional, so no new frame is committed on failure.
                if isinstance(exc, RuntimePresentationRenderError):
                    raise RuntimePresentationHostError(
                        "host could not advance and render the runtime frame"
                    ) from exc
                raise RuntimePresentationHostError(
                    "host loop tick failed"
                ) from exc
            self._last_frame = self._copy_frame(frame)
            self._frame_count += 1
            self._present(frame)
            return frame
        finally:
            self._in_host_call = False
