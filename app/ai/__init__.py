"""Local-only AI pipeline for the Relatorio TikTok application.

The package intentionally keeps heavyweight imports inside the modules that
actually execute inference. Importing Flask, the database, or the old
analytics still works when the optional GPU dependencies are not installed.
"""

CLASSIFIER_PROMPT_VERSION = "1"
STRATEGIST_PROMPT_VERSION = "1"

__all__ = ["CLASSIFIER_PROMPT_VERSION", "STRATEGIST_PROMPT_VERSION"]
