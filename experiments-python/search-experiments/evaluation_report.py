"""Compatibility wrapper for the live evaluation report.

Historically this file contained hardcoded metrics and winners, which can drift
from current benchmark artifacts and lead to misleading conclusions.
Use eval_analyze.py's computed report instead.
"""

from eval_analyze import main


if __name__ == "__main__":
    main()
