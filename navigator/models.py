"""Pydantic models for LLM outputs (provider-neutral, strict-schema friendly: every field required, nullable)."""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field

Category = Literal[
    "rent_increase_limits",
    "just_cause_eviction",
    "security_deposits",
    "application_screening_fees",
    "screening_restrictions",
    "algorithmic_rent_setting",
]
Fact = Literal[
    "year_built",
    "units",
    "owner_type",
    "certificate_of_occupancy",
    "owner_occupied",
    "subsidized",
    "new_construction_filing",
    "tenant_status",
    "other",
]
Instrument = Literal["statute", "ordinance", "regulation", "bill", "ballot_measure", "agency_guidance"]


class ExemptionOut(BaseModel):
    description: str
    max_units: int | None = Field(description="exemption only possible for buildings with at most this many units")
    min_units: int | None
    built_after: str | None = Field(description="ISO date; exemption for buildings built/certified after this date")
    newer_than_years: int | None = Field(description="rolling exemption, e.g. 15 for 'issued within the last 15 years'")
    depends_on: list[Fact]


class CoverageOut(BaseModel):
    applies_to: str = Field(description="plain-language summary of which rental units are covered")
    min_units: int | None
    max_units: int | None
    built_before: str | None = Field(description="ISO date; covers buildings built/certified BEFORE this date")
    built_after: str | None
    cutoff_basis: Literal["year_built", "certificate_of_occupancy", "not_stated"]
    requires_facts_not_in_data: list[Fact]
    exemptions: list[ExemptionOut]
    coverage_span: str | None = Field(description="verbatim quote stating the threshold or cutoff, or null")


class CandidateRuleOut(BaseModel):
    jurisdiction: str
    level: Literal["state", "city"]
    category: Category
    instrument: Instrument
    enacted: bool
    failed: bool
    title: str
    requirement: str
    key_value: str | None
    key_value_span: str | None
    effective_date: str | None = Field(description="YYYY, YYYY-MM or YYYY-MM-DD")
    effective_date_span: str | None
    effective_date_basis: str | None = Field(description="how a relative date was computed, else null")
    sunset_date: str | None
    citation: str
    quoted_span: str
    coverage: CoverageOut
    interaction: str | None = Field(description="how this rule relates to rules at the other level")
    preemption_note: str | None
    confidence: float


class ExtractionOut(BaseModel):
    rules: list[CandidateRuleOut]
    categories_discussed_without_rule: list[Category]


class RepairOut(BaseModel):
    quote: str | None = Field(description="exact passage copied verbatim from the options, or null")
