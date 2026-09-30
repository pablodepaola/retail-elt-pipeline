"""Retail ELT pipeline package.

A free-tier, production-grade batch ELT that lands immutable raw data, loads it
into DuckDB, transforms with dbt, gates on data quality, and publishes marts to
Oracle Autonomous DB for an Oracle APEX exec dashboard.
"""

__version__ = "1.0.0"
