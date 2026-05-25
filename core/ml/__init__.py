"""Predictive models package for Apiary (per-colony forecasting).

Layered hybrid approach (see project_predictive_models memory):
  * ``dataset``  – single source of truth that gathers a colony's raw time series.
  * ``features`` – turns that raw series into a tidy week-colony feature grid.
  * ``models``   – one module per prediction target (swarm, wintering, production),
                   each exposing a mechanistic ``baseline`` plus, later, a fitted
                   statistical layer.

Naming convention for this sub-module is English even though the rest of the
backend is in Italian (explicit user decision, 2026-05-24).
"""
