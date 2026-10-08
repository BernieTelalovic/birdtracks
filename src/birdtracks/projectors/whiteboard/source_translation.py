"""Disposable, token-aware source view for the Python algebra parsers.

This module never rewrites saved/displayed notation or translates coefficients.
Original source continues to own all renderer offsets and occurrence identities.
"""

from __future__ import annotations

import re


_COMMAND = re.compile(r'\\([A-Za-z]+)')
_ALGEBRA_COMMANDS = frozenset({'def', 'birdtracks', 'pair', 'otimes', 'oplus',
                               'times', 'frac', 'tr', 'left', 'right'})
_TEXT_GROUPS = frozenset({'text', 'mathrmtext', 'mathbb', 'mathcal', 'mathfrak',
                        'mathrm', 'mathbf', 'operatorname'})


def algebra_command_spacing(source: str) -> str:
    """Separate algebra command tokens without changing names or text groups.

    TeX already treats an unescaped backslash as a command boundary. Supply
    that boundary to string-based algebra parsers and marker substitution, but
    leave escaped punctuation, subscripts, superscripts and text/font groups
    verbatim. Spacing is idempotent and does not evaluate any algebra.
    """
    def group_end(start: int) -> int:
        depth, index = 0, start
        while index < len(source):
            character = source[index]
            if character == '\\':
                index += 2
                continue
            if character == '{':
                depth += 1
            elif character == '}':
                depth -= 1
                if depth == 0:
                    return index+1
            index += 1
        return len(source)  # Keep incomplete groups as drafts, not repairs.

    parts: list[str] = []
    index = 0
    while index < len(source):
        start = index
        if source[index] in '_^':
            index += 1
            while index < len(source) and source[index].isspace():
                index += 1
            if index < len(source) and source[index] == '{':
                index = group_end(index)
            elif index < len(source) and source[index] == '\\':
                command = _COMMAND.match(source,index)
                index = command.end() if command else min(len(source),index+2)
            elif index < len(source):
                index += 1
            parts.append(source[start:index])
            continue
        if source[index] == '\\':
            command = _COMMAND.match(source,index)
            if command:
                if command[1] in _ALGEBRA_COMMANDS and parts and not parts[-1][-1].isspace():
                    parts.append(' ')
                index = command.end()
                if command[1] in _TEXT_GROUPS:
                    argument = index
                    while argument < len(source) and source[argument].isspace():
                        argument += 1
                    if argument < len(source) and source[argument] == '{':
                        index = group_end(argument)
            else:
                index = min(len(source),index+2)
                if source[start:index] in (r'\_',r'\^'):
                    argument = index
                    while argument < len(source) and source[argument].isspace():
                        argument += 1
                    if argument < len(source) and source[argument] == '{':
                        index = group_end(argument)
        else:
            index += 1
        parts.append(source[start:index])
    return ''.join(parts)
