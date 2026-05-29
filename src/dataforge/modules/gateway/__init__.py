"""Gateway module.

API aggregation surface: auth, routing and rate limiting. In the monolith it
exposes cross-cutting endpoints; when modules split out it becomes the edge.
"""

from dataforge.modules.gateway.module import module

__all__ = ["module"]
