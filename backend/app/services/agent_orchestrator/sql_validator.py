from __future__ import annotations

import re
from typing import Any

from app.services.agent_orchestrator.table_policy import FORBIDDEN_TABLES, get_policy
from app.services.agent_orchestrator.types import AgentOperationType, SqlValidationResult

_DANGEROUS = re.compile(
    r"\b(drop|delete|alter|truncate|create|replace|attach|detach|pragma|vacuum)\b",
    re.IGNORECASE,
)
_COMMENT = re.compile(r"(--|/\*|\*/|#)")
_SELECT_RE = re.compile(
    r"^\s*select\s+(?P<cols>.+?)\s+from\s+(?P<table>[a-zA-Z_][\w]*)\b(?P<rest>.*)$",
    re.IGNORECASE | re.DOTALL,
)
_INSERT_RE = re.compile(
    r"^\s*insert\s+into\s+(?P<table>[a-zA-Z_][\w]*)\s*\((?P<cols>[^)]+)\)\s*values\s*\((?P<values>[^)]+)\)\s*$",
    re.IGNORECASE | re.DOTALL,
)
_UPDATE_RE = re.compile(
    r"^\s*update\s+(?P<table>[a-zA-Z_][\w]*)\s+set\s+(?P<sets>.+?)\s+where\s+(?P<where>.+)\s*$",
    re.IGNORECASE | re.DOTALL,
)
_PARAM_RE = re.compile(r":[a-zA-Z_][\w]*")
_LIMIT_RE = re.compile(r"\blimit\s+(\d+)\b", re.IGNORECASE)
_TABLE_REF_RE = re.compile(r"\b(?:from|join)\s+([a-zA-Z_][\w]*)\b", re.IGNORECASE)
_ALLOWED_FUNCTIONS = {"sum", "count", "coalesce", "date", "strftime", "max", "min", "avg"}


class SqlValidator:
    def validate(
        self,
        operation_type: AgentOperationType,
        table_name: str | None,
        sql: str | None,
        params: dict[str, Any] | None = None,
    ) -> SqlValidationResult:
        params = params or {}
        if operation_type not in {AgentOperationType.select, AgentOperationType.insert, AgentOperationType.update}:
            return self._reject("unknown or non-SQL operation type")
        if not sql or not isinstance(sql, str):
            return self._reject("missing SQL")
        if ";" in sql.strip().rstrip(";") or sql.count(";") > 0:
            return self._reject("multiple statements or semicolons are not allowed")
        if _COMMENT.search(sql):
            return self._reject("SQL comments are not allowed")
        if _DANGEROUS.search(sql):
            return self._reject("destructive or administrative SQL is not allowed")
        if not isinstance(params, dict):
            return self._reject("params must be an object")
        if "user_id" in {k.lower() for k in params.keys()}:
            return self._reject("LLM-provided user_id is not allowed")

        if operation_type == AgentOperationType.select:
            try:
                return self._validate_select(table_name, sql, params)
            except ValueError as exc:
                return self._reject(str(exc))
        if operation_type == AgentOperationType.update:
            try:
                return self._validate_update(table_name, sql, params)
            except ValueError as exc:
                return self._reject(str(exc))
        try:
            return self._validate_insert(table_name, sql, params)
        except ValueError as exc:
            return self._reject(str(exc))

    def _validate_select(self, requested_table: str | None, sql: str, params: dict[str, Any]) -> SqlValidationResult:
        match = _SELECT_RE.match(sql)
        if not match:
            return self._reject("only simple SELECT statements are allowed")
        table = match.group("table").lower()
        referenced_tables = [name.lower() for name in _TABLE_REF_RE.findall(sql)]
        if table not in referenced_tables:
            referenced_tables.insert(0, table)
        if requested_table and requested_table.lower() not in referenced_tables:
            return self._reject("step table_name is not referenced by SQL")
        policies = {}
        for ref_table in referenced_tables:
            policy = get_policy(ref_table)
            if not policy or ref_table in FORBIDDEN_TABLES or not policy.allowed_select or policy.system_only:
                return self._reject("SELECT from this table is forbidden", ref_table)
            policies[ref_table] = policy
        policy = policies[requested_table.lower() if requested_table and requested_table.lower() in policies else table]

        columns = self._extract_select_columns(match.group("cols"))
        if not columns:
            return self._reject("no selectable columns found", table)
        for col in columns:
            if col == "*":
                return self._reject("SELECT * is not allowed", table)
            if col in _ALLOWED_FUNCTIONS or col in {"literal"}:
                continue
            base = col.split(".", 1)[-1]
            if not any(base in item.selectable_columns for item in policies.values()):
                return self._reject(f"column {base} is not selectable", table)

        for ref_table, ref_policy in policies.items():
            for forbidden in ref_policy.forbidden_columns:
                if re.search(rf"\b{re.escape(ref_table)}\.{re.escape(forbidden)}\b|\b{re.escape(forbidden)}\b", sql, re.IGNORECASE):
                    return self._reject(f"column {forbidden} is forbidden", ref_table)

        self._validate_params_are_used(sql, params)
        limit_match = _LIMIT_RE.search(sql)
        limit = int(limit_match.group(1)) if limit_match else policy.max_select_rows
        limit = min(limit, policy.max_select_rows)
        return SqlValidationResult(
            allowed=True,
            operation_type=AgentOperationType.select,
            table_name=table,
            sql=sql.strip(),
            params=params,
            columns=columns,
            limit=limit,
        )

    def _validate_insert(self, requested_table: str | None, sql: str, params: dict[str, Any]) -> SqlValidationResult:
        match = _INSERT_RE.match(sql)
        if not match:
            return self._reject("only simple parameterized INSERT statements are allowed")
        table = match.group("table").lower()
        if requested_table and table != requested_table.lower():
            return self._reject("step table_name does not match SQL table", table)
        policy = get_policy(table)
        if not policy or table in FORBIDDEN_TABLES or not policy.allowed_insert or policy.system_only:
            return self._reject("INSERT into this table is forbidden", table)

        columns = [c.strip().lower() for c in match.group("cols").split(",")]
        values = [v.strip() for v in match.group("values").split(",")]
        if len(columns) != len(values):
            return self._reject("INSERT columns and values do not match", table)
        if "user_id" in columns:
            return self._reject("LLM cannot set user_id", table)
        for col in columns:
            if col not in policy.insertable_columns or col in policy.forbidden_columns:
                return self._reject(f"column {col} is not insertable", table)
        for value in values:
            if not _PARAM_RE.fullmatch(value):
                return self._reject("INSERT values must be named parameters only", table)
        self._validate_params_are_used(sql, params)
        return SqlValidationResult(
            allowed=True,
            operation_type=AgentOperationType.insert,
            table_name=table,
            sql=sql.strip(),
            params=params,
            columns=columns,
        )

    def _validate_update(self, requested_table: str | None, sql: str, params: dict[str, Any]) -> SqlValidationResult:
        match = _UPDATE_RE.match(sql)
        if not match:
            return self._reject("only simple parameterized UPDATE statements are allowed")
        table = match.group("table").lower()
        if requested_table and table != requested_table.lower():
            return self._reject("step table_name does not match SQL table", table)
        policy = get_policy(table)
        if not policy or table in FORBIDDEN_TABLES or not policy.allowed_update or policy.system_only:
            return self._reject("UPDATE on this table is forbidden", table)

        assignments = [item.strip() for item in match.group("sets").split(",") if item.strip()]
        if not assignments:
            return self._reject("UPDATE requires at least one assignment", table)
        columns: list[str] = []
        for assignment in assignments:
            assignment_match = re.match(r"^([a-zA-Z_][\w]*)\s*=\s*(:[a-zA-Z_][\w]*)$", assignment)
            if not assignment_match:
                return self._reject("UPDATE assignments must be named parameters only", table)
            col = assignment_match.group(1).lower()
            if col == "user_id":
                return self._reject("LLM cannot set user_id", table)
            if col not in policy.updateable_columns or col in policy.forbidden_columns:
                return self._reject(f"column {col} is not updateable", table)
            columns.append(col)

        where = match.group("where").strip().lower()
        if not re.fullmatch(r"id\s*=\s*:[a-zA-Z_][\w]*", where):
            return self._reject("UPDATE must target one row by id parameter", table)
        self._validate_params_are_used(sql, params)
        return SqlValidationResult(
            allowed=True,
            operation_type=AgentOperationType.update,
            table_name=table,
            sql=sql.strip(),
            params=params,
            columns=columns,
        )

    def _extract_select_columns(self, raw: str) -> list[str]:
        cols: list[str] = []
        for part in self._split_select_items(raw):
            token = part.strip()
            lower = token.lower()
            if re.match(r"^\d+(\.\d+)?(\s+as\s+[a-zA-Z_][\w]*)?$", lower):
                cols.append("literal")
                continue
            if any(fn + "(" in lower for fn in _ALLOWED_FUNCTIONS):
                for fn in _ALLOWED_FUNCTIONS:
                    if fn + "(" in lower:
                        cols.append(fn)
                for identifier in re.findall(r"\b([a-zA-Z_][\w.]*)\b", lower):
                    base = identifier.split(".")[-1]
                    if base not in _ALLOWED_FUNCTIONS and base not in {"as", "total", "null", "ifnull"}:
                        cols.append(base)
                continue
            token = re.split(r"\s+as\s+|\s+", token, flags=re.IGNORECASE)[0]
            cols.append(token.split(".")[-1].lower())
        return cols

    def _split_select_items(self, raw: str) -> list[str]:
        items: list[str] = []
        current: list[str] = []
        depth = 0
        for char in raw:
            if char == "(":
                depth += 1
            elif char == ")" and depth:
                depth -= 1
            if char == "," and depth == 0:
                items.append("".join(current))
                current = []
                continue
            current.append(char)
        if current:
            items.append("".join(current))
        return items

    def _validate_params_are_used(self, sql: str, params: dict[str, Any]) -> None:
        used = {p[1:] for p in _PARAM_RE.findall(sql)}
        extra = set(params) - used
        if extra:
            raise ValueError(f"unused SQL params: {', '.join(sorted(extra))}")

    def _reject(self, reason: str, table: str | None = None) -> SqlValidationResult:
        return SqlValidationResult(allowed=False, table_name=table, rejected_reason=reason)
