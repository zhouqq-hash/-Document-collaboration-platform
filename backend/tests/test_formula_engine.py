import pytest

from app.formula_engine import (
    FormulaEvaluator,
    UnsupportedFormulaError,
    format_formula_result,
)
from app.table_sheets import calculate_grid, remap_formula_references


class StubResolver:
    def __init__(self, cells):
        self.cells = cells

    def cell(self, address):
        return self.cells.get(address, "")

    def range(self, start, end):
        return [self.cells.get("A2", ""), self.cells.get("A3", "")]


def test_formula_engine_calculates_ranges_and_arithmetic():
    evaluator = FormulaEvaluator(StubResolver({"A2": "2", "A3": "3", "B2": "4"}))

    assert evaluator.evaluate("=SUM(A2:A3)*B2") == 20
    assert evaluator.evaluate("=IF(A2>1, \"够\", \"不够\")") == "够"
    assert format_formula_result(evaluator.evaluate("=ROUND(2.345, 2)")) == "2.35"


def test_formula_engine_does_not_evaluate_unused_if_branch():
    evaluator = FormulaEvaluator(StubResolver({}))

    assert evaluator.evaluate("=IF(TRUE, 1, 1/0)") == 1


def test_formula_engine_rejects_unsupported_function():
    evaluator = FormulaEvaluator(StubResolver({}))

    with pytest.raises(UnsupportedFormulaError):
        evaluator.evaluate("=VLOOKUP(A2, A2:B3, 2, FALSE)")


def test_calculate_grid_recalculates_dependent_formulas():
    columns = [
        {"key": "col1", "name": "人数", "type": "text"},
        {"key": "col2", "name": "总分", "type": "text"},
        {"key": "col3", "name": "平均分", "type": "text"},
    ]
    rows = [
        {
            "row_key": "r1",
            "cells": {"col1": "2", "col2": "80", "col3": "0"},
        }
    ]
    meta = {
        "r1:col3": {
            "formula": "=B2/A2",
            "locked": False,
        }
    }

    _cols, result_rows, result_meta, report = calculate_grid(columns, rows, meta)

    assert result_rows[0]["cells"]["col3"] == "40"
    assert result_meta["r1:col3"]["formula"] == "=B2/A2"
    assert report["recalculated_formula_count"] == 1


def test_formula_references_follow_deleted_rows_and_columns():
    assert remap_formula_references(
        "=SUM(A2:B4)", deleted_rows={2}
    ) == "=SUM(#REF!)"
    assert remap_formula_references(
        "=SUM(B2:C3)+D2", deleted_columns={1}
    ) == "=SUM(A2:B3)+C2"
