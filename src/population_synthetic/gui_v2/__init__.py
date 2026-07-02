"""gui_v2 — config-driven Flow Runner GUI (parallel to the legacy ``gui/`` launcher).

Two-tier config under ``config/gui/v2/``: a ``menu.yaml`` of flows grouped by
category plus one round-trip-editable YAML per flow. On Run, the GUI TRANSLATES
the flow YAML into CLI invocations of the existing scripts — the spawned
scripts do NOT read the flow YAML.
"""
