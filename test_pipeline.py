#!/usr/bin/env python3
"""Compatibility shim for legacy test command; delegates to qmsep_preflight."""

from qmsep_preflight import main


if __name__ == "__main__":
    main()