import json
from importlib.resources import files
from lark import Lark, Transformer
from ..ast.contracts import TemplateRef, UniqueRule, Contract, Specification

class CompilationError(ValueError):
    pass

class _ContractTransformer(Transformer):
    def NAME(self, token):
        return str(token)

    def STRING(self, token):
        return json.loads(str(token))

    def field(self, items):
        return tuple(items)

    def template_ref(self, items):
        return TemplateRef(*items)

    def unique_rule(self, items):
        return tuple(items)

    def forall_rule(self, items):
        focus_var, focus_alias, unique = items
        product_var, product_alias, left, right = unique
        return UniqueRule(focus_var, focus_alias, product_var,
                          product_alias, *left, *right)

    def contract(self, items):
        return Contract(*items)

    def start(self, items):
        return Specification(items[0],
                             tuple(x for x in items[1:] if isinstance(x, TemplateRef)),
                             tuple(x for x in items[1:] if isinstance(x, Contract)))


def parse_contract(source: str) -> Specification:
    grammar = files("selira.language").joinpath("grammar/contracts.lark").read_text(encoding="utf-8")
    parser = Lark(grammar, parser="lalr", start="start")
    try:
        return _ContractTransformer().transform(parser.parse(source))
    except Exception as exc:
        raise CompilationError(f"Invalid SAFSL contract: {exc}") from exc


