"""One module per benchmark: how to fetch it, how to pose it, how to grade it."""

from __future__ import annotations

from . import babilong, infinitebench, swebench

REGISTRY = {module.NAME: module for module in (babilong, infinitebench, swebench)}
