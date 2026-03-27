"""
BAAKI Credit Scoring — Test Suite
===================================
Unit tests covering the core layers of the application.

Test Modules:
    conftest              — Shared pytest fixtures (sample customer profiles per tier)
    test_api              — API endpoint validation, input guards, HTTP status codes
    test_data_generation  — Synthetic data quality: schema, value ranges, constraints
    test_handler          — Credit scoring logic: tier routing, score calculation, guardrails

Run all tests:
    pytest tests/ -v
"""
