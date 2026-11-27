"""Compile the restricted Boolean policy AST into a SPARQL SELECT."""
from lark import Tree
from rdflib import Graph, Literal
from selira.language.ast.nodes import (
    AssignmentNode, Identifier, Operation, ExpressionStatement,
)


def compile_policy(process):
    inputs = [p.name for p in process.interface.ports if p.direction == "Input"]
    outputs = [p.name for p in process.interface.ports if p.direction == "Output"]
    if not outputs or len(set(inputs + outputs)) != len(inputs + outputs):
        raise ValueError("Invalid policy interface")
    env = {name: f"?i{i}" for i, name in enumerate(inputs)}
    lines = []

    def expression(node):
        if isinstance(node, Identifier):
            if node.name not in env:
                raise ValueError(f"Unbound identifier: {node.name}")
            return env[node.name]
        if isinstance(node, ExpressionStatement):
            return expression(node.expression)
        if isinstance(node, Operation):
            args = [expression(a) for a in node.operands]
            if node.operator in ("and", "or"):
                op = " && " if node.operator == "and" else " || "
                return "(" + op.join(args) + ")" if args else (
                    "true" if node.operator == "and" else "false")
            if node.operator == "notS" and len(args) == 1:
                return "(!" + args[0] + ")"
        raise ValueError("Unsupported policy expression")

    def statement(node):
        if isinstance(node, Tree) and node.data == "statement" and len(node.children) == 1:
            statement(node.children[0])
        elif isinstance(node, AssignmentNode) and node.operator == "assign":
            value = expression(node.value)
            var = f"?v{len(lines)}"
            lines.append(f"  BIND({value} AS {var})")
            env[node.target.name] = var
        else:
            raise ValueError("Unsupported policy statement")

    for node in process.body.statements:
        statement(node)
    if any(name not in env for name in outputs):
        raise ValueError("Unassigned output")
    projection = " ".join(f"({env[name]} AS ?o{i})"
                          for i, name in enumerate(outputs))
    return {"inputs": inputs, "outputs": outputs,
            "query": "SELECT " + projection + " WHERE {\n" +
                     "\n".join(lines) + "\n}\n"}


def execute_compiled(compiled, inputs):
    if set(inputs) != set(compiled["inputs"]) or not all(
            type(v) is bool for v in inputs.values()):
        raise ValueError("Invalid policy inputs")
    bindings = {f"i{i}": Literal(inputs[name])
                for i, name in enumerate(compiled["inputs"])}
    rows = list(Graph().query(compiled["query"], initBindings=bindings))
    if len(rows) != 1:
        raise ValueError("Expected one policy result")
    result = {}
    for i, name in enumerate(compiled["outputs"]):
        term = rows[0][i]
        value = term.toPython() if isinstance(term, Literal) else None
        if type(value) is not bool:
            raise ValueError("Invalid policy result")
        result[name] = value
    return result
