"""Shared, source-neutral semantic IR for engineering and historian requests.

This is the first building block of the new planner, NOT a router or an
executable plan. Model-proposed graph paths are checked against actual SHACL
shape paths before any backend compiler may consume them.
"""
from dataclasses import dataclass, field
from typing import Any, Literal

Source = Literal["graphdb", "timescaledb"]
Operator = Literal["eq", "ne", "contains", "starts_with", "regex", "gt", "gte", "lt", "lte", "exists"]
Logic = Literal["and", "or", "not"]


@dataclass(frozen=True)
class GraphPath:
    domain: str
    root_shape: str
    predicates: tuple[str, ...]
    evidence_ids: tuple[str, ...] = ()

    def validate(self, schema) -> "GraphPath":
        if not self.domain or not self.root_shape or not self.predicates:
            raise ValueError("Graph path requires domain, root shape and predicates")
        for hops in schema.shacl_paths(self.root_shape, max_depth=len(self.predicates),
                                       domain=self.domain):
            if tuple(h["property"] for h in hops) == self.predicates:
                evidence = tuple(eid for hop in hops for eid in hop["evidence_ids"])
                if self.evidence_ids and self.evidence_ids != evidence:
                    raise ValueError("Graph path evidence disagrees with SHACL")
                return GraphPath(self.domain, self.root_shape, self.predicates, evidence)
        raise ValueError("Graph path is not supported by SHACL")


@dataclass(frozen=True)
class Projection:
    name: str
    path: GraphPath | None = None
    source: Source = "graphdb"
    alias: str = "entity"


@dataclass(frozen=True)
class Predicate:
    field: str
    operator: Operator
    value: Any = None
    path: GraphPath | None = None
    alias: str | None = None

    def __post_init__(self):
        if not self.field or self.operator not in (
            "eq", "ne", "contains", "starts_with", "regex", "gt", "gte",
            "lt", "lte", "exists"
        ):
            raise ValueError("Invalid predicate")
        if (self.path is None) != (self.alias is None):
            raise ValueError("Path filter requires both SHACL path and entity alias")
        if self.alias is not None and not self.alias.isidentifier():
            raise ValueError("Invalid filter entity alias")
        if self.operator != "exists" and self.value is None:
            raise ValueError("Comparison requires a value")
        if self.operator == "exists" and self.value is not None:
            raise ValueError("Existence test must not supply a value")


@dataclass(frozen=True)
class BooleanExpression:
    operator: Logic
    children: tuple["BooleanExpression | Predicate", ...]

    def __post_init__(self):
        if self.operator not in ("and", "or", "not"):
            raise ValueError("Invalid Boolean operator")
        if len(self.children) != (1 if self.operator == "not" else 2) and (
            self.operator == "not" or len(self.children) < 2
        ):
            raise ValueError("Invalid Boolean arity")
        if not all(isinstance(c, (Predicate, BooleanExpression)) for c in self.children):
            raise ValueError("Invalid Boolean operand")


@dataclass(frozen=True)
class Join:
    left: str
    right: str
    left_path: GraphPath
    right_path: GraphPath

    def validate(self, schema) -> "Join":
        if not self.left or not self.right or self.left == self.right:
            raise ValueError("Join requires two distinct aliases")
        return Join(self.left, self.right, self.left_path.validate(schema),
                    self.right_path.validate(schema))


@dataclass(frozen=True)
class SemanticQuery:
    question: str
    projections: tuple[Projection, ...]
    joins: tuple[Join, ...] = ()
    where: BooleanExpression | Predicate | None = None
    group_by: tuple[str, ...] = ()
    aggregation: str | None = None
    order_by: tuple[str, ...] = ()
    limit: int | None = None
    run_id: str | None = None
    start_seconds: float | None = None
    end_seconds: float | None = None
    sources: tuple[Source, ...] = ("graphdb",)
    validated: bool = field(default=False, compare=False)

    def validate(self, schema) -> "SemanticQuery":
        from dataclasses import replace
        from uuid import UUID
        if not isinstance(self.question, str) or not 5 <= len(self.question.strip()) <= 1000:
            raise ValueError("Invalid question")
        if not self.projections:
            raise ValueError("At least one projection is required")
        if not self.sources or len(set(self.sources)) != len(self.sources) or any(
            s not in ("graphdb", "timescaledb") for s in self.sources
        ):
            raise ValueError("Invalid sources")
        if any(p.source not in self.sources or not p.name for p in self.projections):
            raise ValueError("Projection source missing or invalid")
        if self.where is not None and not isinstance(self.where, (Predicate, BooleanExpression)):
            raise ValueError("Invalid filter expression")
        if self.limit is not None and (type(self.limit) is not int or self.limit < 1):
            raise ValueError("Invalid limit")
        if self.aggregation not in (None, "count", "count_distinct", "min", "max", "avg", "sum"):
            raise ValueError("Invalid aggregation")
        if "timescaledb" in self.sources:
            if self.run_id is None:
                raise ValueError("Historian requires run UUID")
            UUID(self.run_id)
        if any(v is not None and (isinstance(v, bool) or not isinstance(v, (int, float))
                                  or not 0 <= v < float("inf"))
               for v in (self.start_seconds, self.end_seconds)):
            raise ValueError("Invalid simulation time")
        if (self.start_seconds is not None and self.end_seconds is not None
                and self.start_seconds > self.end_seconds):
            raise ValueError("Invalid time window")
        if any(not isinstance(p.alias, str) or not p.alias or not p.alias.isidentifier() for p in self.projections):
            raise ValueError("Invalid entity alias")
        projections = tuple(replace(p, path=p.path.validate(schema)) if p.path else p
                            for p in self.projections)
        joins = tuple(j.validate(schema) for j in self.joins)
        aliases = {(j.left, j.left_path.domain, j.left_path.root_shape) for j in joins}
        aliases.update((j.right, j.right_path.domain, j.right_path.root_shape) for j in joins)
        aliases.update((p.alias, p.path.domain, p.path.root_shape) for p in projections if p.path)
        def validate_filter(node):
            if isinstance(node, BooleanExpression):
                return replace(node, children=tuple(validate_filter(c) for c in node.children))
            if node.path is None:
                return node
            path = node.path.validate(schema)
            if (node.alias, path.domain, path.root_shape) not in aliases:
                raise ValueError("Filter path must share a bound entity alias and SHACL root")
            return replace(node, path=path)
        return replace(self, projections=projections, joins=joins,
                       where=validate_filter(self.where) if self.where else None,
                       validated=True)
