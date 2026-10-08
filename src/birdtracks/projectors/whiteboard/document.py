"""Revisioned source transactions and live occurrence references for a document.

Notation parsing is deliberately not evaluation. Expensive algebra remains an
explicit calculation; valid source and embedded editor values share this object.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from copy import deepcopy
from dataclasses import dataclass
import re


_SYMBOLS = set("alpha beta gamma delta epsilon varepsilon zeta eta theta vartheta iota kappa lambda mu nu xi pi varpi rho sigma tau upsilon phi varphi chi psi omega Gamma Delta Theta Lambda Xi Pi Sigma Phi Psi Omega cdot times pm mp leq geq neq infty to mapsto partial nabla sum prod int oplus otimes def tr".split())
_GROUP_COMMANDS = {"frac": 2, "sqrt": 1, "text": 1, "mathrmtext": 1,
                   "mathbb": 1, "mathcal": 1, "mathfrak": 1, "mathrm": 1, "mathbf": 1}
_MARKERS = re.compile(r"\\(?P<kind>birdtracks|pair)\b")


@dataclass(frozen=True)
class ParsedSource:
    """Immutable notation, referencing—not duplicating—embedded algebra."""

    source: str
    references: tuple[str, ...]


def parse_source(source: str, block_id: str) -> ParsedSource:
    """Validate supported notation completeness without multiplying operators.

    The browser's existing MathML parser remains a disposable immediate preview.
    This strict boundary does not accept its permissive incomplete-group output
    as committed source. Export still uses the original LaTeX spelling.
    """
    if not isinstance(source, str):
        raise ValueError("source must be text")
    index = 0

    def spaces() -> None:
        nonlocal index
        while index < len(source) and source[index].isspace():
            index += 1

    def group(*, raw: bool = False) -> str:
        nonlocal index
        spaces()
        if index >= len(source) or source[index] != "{":
            raise ValueError("expected a braced argument")
        start = index + 1
        index += 1
        sequence("}", raw=raw)
        return source[start:index-1]

    def sequence(closing: str | None = None, *, raw: bool = False) -> None:
        nonlocal index
        scripts = set()
        script_argument = False
        while index < len(source):
            character = source[index]
            if character == closing:
                index += 1
                return
            if character == "}" or not raw and character in "])":
                raise ValueError(f"unexpected {character!r}")
            if not raw and character in '_^':
                if character in scripts:
                    raise ValueError('duplicate subscript' if character == '_' else 'duplicate superscript')
                scripts.add(character)
                script_argument = True
                index += 1
                spaces()
                if index == len(source):
                    raise ValueError('incomplete script')
                continue
            if not raw and not character.isspace():
                if not script_argument:
                    scripts.clear()
                script_argument = False
            if character in "{[(" and not raw:
                index += 1
                sequence({"{": "}", "[": "]", "(": ")"}[character])
                continue
            if raw:
                if character == "{":
                    index += 1
                    sequence("}", raw=True)
                elif character == "\\" and index+1 < len(source):
                    index += 2
                else:
                    index += 1
                continue
            if character == "\\":
                index += 1
                command = re.match(r"[A-Za-z]+", source[index:])
                if command is None:
                    if index == len(source):
                        raise ValueError("incomplete command")
                    index += 1  # escaped punctuation, including \_ and math delimiters
                    continue
                name = command.group()
                index += len(name)
                if name in _GROUP_COMMANDS:
                    arguments = [group(raw=name in {"text", "mathrmtext"}) for _ in range(_GROUP_COMMANDS[name])]
                    if name == "frac" and re.fullmatch(r"\s*[+-]?0+(?:[.,]0+)?\s*", arguments[1]):
                        raise ValueError("a coefficient denominator cannot be zero")
                elif name in {"birdtracks", "pair"}:
                    spaces()
                    if index < len(source) and source[index] == "{":
                        group(raw=True)
                elif name in {"left", "right"}:
                    spaces()
                    if index == len(source):
                        raise ValueError(f"incomplete \\{name} delimiter")
                    # Sized delimiters are paired by the ordinary group scanner.
                    if name == "left" and source[index] in "([":
                        delimiter = source[index]
                        index += 1
                        sequence({"(": ")", "[": "]"}[delimiter])
                    elif name != "right":
                        index += 1
                elif name not in _SYMBOLS:
                    raise ValueError(f"unsupported command \\{name}")
                continue
            number = re.match(r'[0-9.,]+', source[index:])
            index += len(number.group()) if number else 1
        if closing is not None:
            raise ValueError(f"missing closing {closing!r}")

    sequence()
    if len(re.findall(r"(?<!\\)\$", source)) % 2:
        raise ValueError("unclosed math delimiter")
    if re.search(r"(?:[+*/=^-]|\\(?:oplus|otimes|times|def))\s*$", source):
        raise ValueError("expected an expression after the operator")
    counts = {"birdtracks": 0, "pair": 0}
    references = []
    for marker in _MARKERS.finditer(source):
        kind = marker.group('kind')
        references.append(f"{block_id}:{'projector' if kind == 'birdtracks' else 'pair'}:{counts[kind]}")
        counts[kind] += 1
    return ParsedSource(source, tuple(references))


class DocumentSession:
    """One authoritative document; drafts and valid source are distinct fields."""

    def __init__(self, blocks: Sequence[Mapping[str, object]]) -> None:
        self.revision = 0
        self._blocks = deepcopy(list(blocks))
        self.occurrences: dict[str, object] = {}

    @property
    def blocks(self) -> list[dict[str, object]]:
        return deepcopy(self._blocks)

    @property
    def committed_blocks(self) -> list[dict[str, object]]:
        return [{**block, "source": block.get("source_edit", {}).get("committed_source", block.get("source", ""))}
                for block in self.blocks]

    def source_value(self, block_id: str) -> ParsedSource:
        """Read the immutable last-valid notation and its live occurrence IDs."""
        block = next(b for b in self.committed_blocks if b['id'] == block_id)
        return parse_source(block['source'], block_id)

    def payload(self) -> dict[str, object]:
        return {"version": 1, "revision": self.revision, "blocks": self.blocks}

    def check_revision(self, revision: int) -> None:
        if isinstance(revision, bool) or not isinstance(revision, int) or revision != self.revision:
            raise ValueError("stale document command; use the current revision")

    def _source(self, block: dict[str, object], source: str) -> dict[str, object]:
        previous = block.get('source_edit', {})
        committed = previous.get('committed_source', block.get('source', ''))
        try:
            parse_source(source, block['id'])
            committed, error = source, ''
            block = deepcopy(block)
            for field, marker in (('projector_snapshots', 'birdtracks'), ('pair_snapshots', 'pair'), ('pair_cell_styles', 'pair')):
                count = len(re.findall(r'\\'+marker+r'\b(?!\s*\{)', source))
                stored = block.get(field)
                if isinstance(stored, dict) and all(str(key).isdigit() for key in stored):
                    block[field] = {key:value for key,value in stored.items() if int(key) < count}
        except ValueError as exc:
            error = str(exc)
        return {**block, 'source': source, 'source_edit': {
            'revision': int(previous.get('revision', 0))+1,
            'committed_source': committed, 'error': error,
        }}

    def reconcile(self, blocks: Sequence[Mapping[str, object]]) -> None:
        """Bridge trusted Python structural/presentation updates into the object."""
        candidate = deepcopy(list(blocks))
        if len({b['id'] for b in candidate}) != len(candidate):
            raise ValueError("document block IDs must be unique")
        old = {b['id']: b for b in self._blocks}
        for index, block in enumerate(candidate):
            previous = old.get(block['id'])
            if previous and 'source_edit' in previous:
                if block.get('source') != previous.get('source'):
                    candidate[index] = self._source({**block, 'source_edit': previous['source_edit']}, block.get('source', ''))
                else:
                    candidate[index].setdefault('source_edit', previous['source_edit'])
        if candidate != self._blocks:
            self._blocks = candidate
            self.revision += 1

    def edit_source(self, block_id: str, source: str, *, base_revision: int) -> list[dict[str, object]]:
        self.check_revision(base_revision)
        if not isinstance(block_id, str) or not block_id or not isinstance(source, str):
            raise ValueError("source editing requires a block ID and text")
        blocks = self.blocks
        index = next((i for i,b in enumerate(blocks) if b['id'] == block_id), len(blocks))
        block = blocks[index] if index < len(blocks) else {'id': block_id, 'source': ''}
        if block.get('read_only'):
            raise ValueError("generated source is read-only")
        if source == block.get('source') and 'source_edit' in block:
            return blocks
        updated = self._source(block, source)
        updated['line_id'] = (blocks[index-1].get('line_id', blocks[index-1]['id'])
                              if index > 0 and re.match(r'^\s*&', source) else block_id)
        if index == len(blocks):
            blocks.append(updated)
        else:
            blocks[index] = updated
        if blocks != self._blocks:
            self._blocks = blocks
            self.revision += 1
        return self.blocks

    def patch_blocks(self, changes: list[dict[str, object]], order: list[str], *, base_revision: int) -> list[dict[str, object]]:
        self.check_revision(base_revision)
        if (not isinstance(changes, list) or not isinstance(order, list)
                or any(not isinstance(i, str) or not i for i in order) or len(set(order)) != len(order)):
            raise ValueError('document patch requires unique ordered block IDs')
        blocks = {b['id']: b for b in self.blocks}
        for change in changes:
            identity = change['id']
            if not isinstance(identity, str) or identity not in order or not isinstance(change['fields'], Mapping):
                raise ValueError('document patch references an unknown block')
            if 'source_edit' in change['fields'] or 'source_edit' in change.get('remove', []):
                raise ValueError('source parse metadata is Python-owned')
            block = {**blocks.get(identity, {'id': identity, 'source': ''}), **change['fields']}
            for field in change.get('remove', []):
                block.pop(field, None)
            if block.get('id') != identity or not isinstance(block.get('source'), str):
                raise ValueError('document patch must preserve block identity and source type')
            if block.get('source') != blocks.get(identity, {}).get('source'):
                block = self._source({**block, 'source': blocks.get(identity, {}).get('source', '')}, block['source'])
            blocks[identity] = block
        if not set(order) <= blocks.keys():
            raise ValueError('document patch order references unknown blocks')
        self.reconcile([blocks[i] for i in order])
        return self.blocks

    def occurrence_value(self, identity: str) -> object:
        """Read the live Python owner, never a frontend/saved copy."""
        editor = self.occurrences[identity]
        session = getattr(editor, '_editor_session', None)
        if session is not None:
            return session.state.projector
        if hasattr(editor, 'pair_expression'):
            from ...young_diagrams import PairExpression

            return PairExpression.from_state(editor.pair_expression)
        return editor.projector
