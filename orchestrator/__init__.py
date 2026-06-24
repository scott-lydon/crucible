"""Orchestrator: owns the pillar interfaces, the loop, the wiring, the API.

Modules implement the Protocols in `orchestrator.interfaces`; only
`orchestrator.wiring` imports both a concrete module class and the interface
it satisfies (coding-practices.md section 2).
"""
