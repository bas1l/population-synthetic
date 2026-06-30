"""Project path resolution.

Defines the single ``PROJECT_ROOT`` constant from which all cache and
config paths derive, computed relative to this module's location.
"""
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[2]  # src/population_synth/ -> population-synth/
