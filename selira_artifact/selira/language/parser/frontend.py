"""Portable SAFSL parser using the upstream Lark grammar and transformer."""

# Created: 2026-10-31
# Author: Harish
from importlib.resources import files
from lark import Lark
from selira.language.parser.transformer import SAFSLTransformer


def parse_safsl(source: str):
    grammar = files("selira.language").joinpath("grammar/process.lark").read_text(encoding="utf-8")
    parser = Lark(grammar, parser="lalr", start="start", propagate_positions=True)
    return SAFSLTransformer().transform(parser.parse(source))
