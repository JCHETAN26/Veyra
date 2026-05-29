"""Domain modules.

Each of the seven platform domains lives here as a self-contained package
exposing a `module: DomainModule` instance. The app factory mounts them all.
This is the seam along which a module can later become its own service: its
router, lifecycle, and health check are already isolated.
"""
