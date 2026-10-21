"""Validate documented mathematical calls without accepting raw command code."""

from .documentation import construction_commands
from .expressions import parse_expression
from .schema import DocumentedCommandStep, ExpressionArgument, ListArgument, ReferenceArgument


def command_references(step: DocumentedCommandStep) -> tuple[str, ...]:
    references = []

    def visit(argument, depth=0):
        if depth > 8:
            raise ValueError('command arguments exceed nesting depth 8')
        if isinstance(argument, ReferenceArgument):
            references.append(argument.ref)
        elif isinstance(argument, ExpressionArgument):
            parse_expression(argument.expression, frozenset({'x', 'y', 'z', 'u', 'v'}))
        elif isinstance(argument, ListArgument):
            for item in argument.items:
                visit(item, depth + 1)

    for argument in step.args:
        visit(argument)
    return tuple(references)


def validate_command(step: DocumentedCommandStep) -> None:
    name = construction_commands().get(step.name.lower())
    if name is None:
        raise ValueError(f'{step.name!r} is not a documented construction command; scripting commands are not construction steps')
    step.name = name
    command_references(step)
