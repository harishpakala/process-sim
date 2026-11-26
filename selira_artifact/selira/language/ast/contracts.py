from dataclasses import dataclass

@dataclass(frozen=True)
class TemplateRef:
    alias: str
    identifier: str


@dataclass(frozen=True)
class UniqueRule:
    focus_variable: str
    focus_alias: str
    product_variable: str
    product_alias: str
    left_variable: str
    left_field: str
    right_variable: str
    right_field: str


@dataclass(frozen=True)
class MatchRule:
    focus_variable: str
    focus_alias: str
    left_variable: str
    left_field: str
    right_variable: str
    right_field: str


@dataclass(frozen=True)
class Contract:
    identifier: str
    rule: UniqueRule | MatchRule


@dataclass(frozen=True)
class Specification:
    name: str
    templates: tuple
    contracts: tuple


