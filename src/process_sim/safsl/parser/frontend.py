"""Portable SAFSL parser using the upstream Lark grammar and transformer."""
from importlib.resources import files
from lark import Lark
from process_sim.safsl.parser.transformer import SAFSLTransformer


def parse_safsl(source: str):
    grammar = files("process_sim.safsl").joinpath("grammar/process.lark").read_text(encoding="utf-8")
    parser = Lark(grammar, parser="lalr", start="start", propagate_positions=True)
    return SAFSLTransformer().transform(parser.parse(source))
