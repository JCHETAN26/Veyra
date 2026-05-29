"""Remediation module.

Spark failure analysis, fix/patch proposal generation and safe rerun
orchestration. Acts only behind an approval gate owned by orchestration.
"""

from dataforge.modules.remediation.module import module

__all__ = ["module"]
