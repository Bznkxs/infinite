"""A local web viewer for run trajectories.

`reader.py` turns `trajectory-<id>.jsonl` into the shape the page renders;
`server.py` serves it. Both are stdlib-only, so the viewer adds no dependency
to the scaffold.
"""

from .reader import list_workspaces, load_trajectory

__all__ = ["list_workspaces", "load_trajectory"]
