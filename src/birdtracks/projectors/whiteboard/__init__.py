"""Backend-neutral whiteboard state and evaluation primitives.

The package deliberately has no notebook, widget, or rendering dependency.
Frontends create expression values from :mod:`.model` and submit them to an
``EvaluationEnvironment``.  The environment talks to an algebra backend
through :mod:`.protocol`, so the projector implementation can later be
replaced without changing the document or frontend layers.
"""

from .engine import EvaluationEnvironment
from .latex import to_latex, whiteboard_latex
from .diagram_backend import DiagramAlgebraBackend, diagram_backend
from .diagram_codec import DiagramValueCodec, diagram_codec
from .model import (
    DefinitionKind,
    DefinitionLine,
    Expression,
    ProductExpression,
    SymbolDefinition,
    SymbolReference,
    product,
    reference,
)
from .projector_backend import ProjectorAlgebraBackend, projector_backend
from .projector_codec import ProjectorValueCodec, projector_codec
from .protocol import AlgebraBackend, ValueCodec
from .sidecar import (
    TypedWhiteboardSidecar,
    WhiteboardSidecar,
    WhiteboardStores,
    resolve_sidecar_path,
    write_sidecar,
    write_typed_sidecar,
)

__all__ = [
    "AlgebraBackend",
    "DiagramAlgebraBackend",
    "DiagramValueCodec",
    "DefinitionKind",
    "DefinitionLine",
    "EvaluationEnvironment",
    "Expression",
    "ProductExpression",
    "ProjectorAlgebraBackend",
    "ProjectorValueCodec",
    "SymbolDefinition",
    "SymbolReference",
    "ValueCodec",
    "TypedWhiteboardSidecar",
    "WhiteboardSidecar",
    "WhiteboardStores",
    "diagram_backend",
    "diagram_codec",
    "product",
    "projector_codec",
    "projector_backend",
    "reference",
    "resolve_sidecar_path",
    "write_sidecar",
    "write_typed_sidecar",
    "to_latex",
    "whiteboard_latex",
]
