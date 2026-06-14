from __future__ import annotations

from enum import Enum
from typing import Any, Optional

from pydantic import BaseModel, ConfigDict, Field


class StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


class AgentOperationType(str, Enum):
    select = "select"
    insert = "insert"
    update = "update"
    final_response = "final_response"
    ask_clarification = "ask_clarification"
    no_op = "no_op"


class AgentPlanStep(StrictModel):
    step_id: str
    operation_type: AgentOperationType
    purpose: str
    table_name: Optional[str] = None
    sql: Optional[str] = None
    params: dict[str, Any] = Field(default_factory=dict)
    expected_result_name: Optional[str] = None
    depends_on: list[str] = Field(default_factory=list)
    result_usage: Optional[str] = None
    requires_result_before_next_step: bool = False
    user_visible: bool = False
    confidence: float = Field(ge=0, le=1, default=0)


class AgentPlan(StrictModel):
    intent: str
    language: str = "fa"
    reasoning_summary_for_backend_only: Optional[str] = None
    requires_db: bool = False
    steps: list[AgentPlanStep] = Field(default_factory=list)
    final_response_instruction: Optional[str] = None
    final_response_hint: Optional[str] = None
    clarification_question: Optional[str] = None
    confidence: float = Field(ge=0, le=1, default=0)


class AgentExecutionResult(StrictModel):
    step_id: str
    operation_type: AgentOperationType
    allowed: bool
    executed: bool
    rows: list[dict[str, Any]] = Field(default_factory=list)
    inserted_id: Optional[int] = None
    updated_id: Optional[int] = None
    summary: Optional[str] = None
    rejected_reason: Optional[str] = None
    error: Optional[str] = None


class AgentFinalResponse(StrictModel):
    message: str
    operations_summary: list[str] = Field(default_factory=list)
    metadata: dict[str, Any] = Field(default_factory=dict)


class TablePolicy(StrictModel):
    table_name: str
    business_name: str
    allowed_select: bool = False
    allowed_insert: bool = False
    allowed_update: bool = False
    allowed_delete: bool = False
    user_scoped: bool = False
    user_id_column: Optional[str] = "user_id"
    forbidden_columns: set[str] = Field(default_factory=set)
    insertable_columns: set[str] = Field(default_factory=set)
    updateable_columns: set[str] = Field(default_factory=set)
    selectable_columns: set[str] = Field(default_factory=set)
    max_select_rows: int = 25
    system_only: bool = False


class SchemaColumnInfo(StrictModel):
    name: str
    type: str
    nullable: bool
    foreign_key: Optional[str] = None


class SchemaTableInfo(StrictModel):
    table_name: str
    business_name: str
    allowed_operations: list[AgentOperationType]
    columns: list[SchemaColumnInfo]
    user_scoped: bool = False
    user_id_column: Optional[str] = None
    max_select_rows: int = 25


class DbWorld(StrictModel):
    tables: list[SchemaTableInfo]
    instructions: list[str]


class SqlValidationResult(StrictModel):
    allowed: bool
    operation_type: Optional[AgentOperationType] = None
    table_name: Optional[str] = None
    sql: Optional[str] = None
    params: dict[str, Any] = Field(default_factory=dict)
    columns: list[str] = Field(default_factory=list)
    limit: Optional[int] = None
    rejected_reason: Optional[str] = None
