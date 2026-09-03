"""Public runtime exports with lazy loading for low-level module imports.

The package exposes the historical facade names, but importing a leaf module
such as ``RUNTIME.asset_utils`` must not eagerly import ``CentralGameCore``.
That eager import creates a cycle when a direct CLI starts from a world module.
"""

from importlib import import_module


_EXPORTS = {
    'CentralGameCore': ('.central_core', 'CentralGameCore'),
    'CentralGameCoreError': ('.central_core', 'CentralGameCoreError'),
    'ActorSimulationCore': ('.actor_simulation_core', 'ActorSimulationCore'),
    'ActorSimulationError': ('.actor_simulation_core', 'ActorSimulationError'),
    'EmployeeMetadataError': ('.employee_registry', 'EmployeeMetadataError'),
    'EmployeeMetadataRegistry': ('.employee_registry', 'EmployeeMetadataRegistry'),
    'PortalActorLifecycle': ('.portal_actor_lifecycle', 'PortalActorLifecycle'),
    'PortalActorLifecycleError': ('.portal_actor_lifecycle', 'PortalActorLifecycleError'),
    'WorkSeatLifecycle': ('.work_seat_lifecycle', 'WorkSeatLifecycle'),
    'WorkSeatLifecycleError': ('.work_seat_lifecycle', 'WorkSeatLifecycleError'),
    'SpeechSchedulerCore': ('.speech_scheduler_core', 'SpeechSchedulerCore'),
    'SpeechSchedulerError': ('.speech_scheduler_core', 'SpeechSchedulerError'),
    'RuntimePresentationRenderer': (
        '.runtime_presentation_renderer',
        'RuntimePresentationRenderer',
    ),
    'RuntimePresentationRenderError': (
        '.runtime_presentation_renderer',
        'RuntimePresentationRenderError',
    ),
    'RuntimePresentationLoop': ('.runtime_presentation_renderer', 'RuntimePresentationLoop'),
    'RuntimePresentationHostAdapter': (
        '.runtime_presentation_host',
        'RuntimePresentationHostAdapter',
    ),
    'RuntimePresentationHostError': (
        '.runtime_presentation_host',
        'RuntimePresentationHostError',
    ),
    'RuntimeRenderStateError': ('.runtime_render_state', 'RuntimeRenderStateError'),
    'RuntimeRenderStateProjector': (
        '.runtime_render_state',
        'RuntimeRenderStateProjector',
    ),
    'RuntimePersistence': ('.runtime_persistence', 'RuntimePersistence'),
    'RuntimePersistenceError': ('.runtime_persistence', 'RuntimePersistenceError'),
}

__all__ = [
    'CentralGameCore',
    'CentralGameCoreError',
    'ActorSimulationCore',
    'ActorSimulationError',
    'EmployeeMetadataError',
    'EmployeeMetadataRegistry',
    'PortalActorLifecycle',
    'PortalActorLifecycleError',
    'WorkSeatLifecycle',
    'WorkSeatLifecycleError',
    'SpeechSchedulerCore',
    'SpeechSchedulerError',
    'RuntimePresentationRenderer',
    'RuntimePresentationRenderError',
    'RuntimePresentationLoop',
    'RuntimePresentationHostAdapter',
    'RuntimePresentationHostError',
    'RuntimeRenderStateError',
    'RuntimeRenderStateProjector',
    'RuntimePersistence',
    'RuntimePersistenceError',
]


def __getattr__(name: str):
    try:
        module_name, attribute_name = _EXPORTS[name]
    except KeyError as exc:
        raise AttributeError(f"module {__name__!r} has no attribute {name!r}") from exc
    module = import_module(module_name, __name__)
    value = getattr(module, attribute_name)
    globals()[name] = value
    return value
