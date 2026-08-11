"""Termux:API capability adapter for CCOS.

This module exposes Termux:API commands as safe, structured Python tools.
The LLM should select capabilities; this adapter performs execution.
"""

from .termux_api import TOOL_DEFINITIONS, TermuxAPI, get_termux_api

__all__ = ["TOOL_DEFINITIONS", "TermuxAPI", "get_termux_api"]
