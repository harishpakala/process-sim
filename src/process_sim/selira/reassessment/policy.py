"""Restricted Boolean policy execution, not a general SAFSL runtime."""
from lark import Tree
from process_sim.safsl.ast.nodes import AssignmentNode, Identifier, Operation, ExpressionStatement
from process_sim.safsl.parser.frontend import parse_safsl


def load_policy(path):
    spec = parse_safsl(path.read_text(encoding="utf-8")).children[0]
    if len(spec.processes) != 1:
        raise ValueError("Expected one policy process")
    return spec.processes[0]


def evaluate_policy(process, inputs):
    env = dict(inputs)
    if set(env) != {p.name for p in process.interface.ports if p.direction == "Input"} or not all(type(v) is bool for v in env.values()):
        raise ValueError("Invalid policy inputs")

    def evaluate(node):
        if isinstance(node, Identifier):
            return env[node.name]
        if isinstance(node, ExpressionStatement):
            return evaluate(node.expression)
        if isinstance(node, Operation):
            args = [evaluate(a) for a in node.operands]
            if node.operator == "and":
                return all(args)
            if node.operator == "or":
                return any(args)
            if node.operator == "notS":
                if len(args) != 1:
                    raise ValueError("Invalid unary operation")
                return not args[0]
        raise AssertionError(f"Unsupported expression: {node!r}")

    def execute(node):
        if isinstance(node, Tree) and node.data == "statement":
            if len(node.children) != 1:
                raise ValueError("Invalid statement wrapper")
            execute(node.children[0])
        elif isinstance(node, AssignmentNode):
            if node.operator != "assign":
                raise ValueError("Unsupported assignment")
            env[node.target.name] = evaluate(node.value)
        else:
            raise AssertionError(f"Unsupported statement: {node!r}")

    for statement in process.body.statements:
        execute(statement)
    return {p.name: env[p.name] for p in process.interface.ports if p.direction == "Output"}


