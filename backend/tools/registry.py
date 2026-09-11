"""The tool registry — how an agent discovers and calls anything in
`backend/tools`.

Until now every tool was a plain function: correct, tested, and
unreachable from the orchestrator. A tool the agent cannot call is not a
capability, and CLAUDE.md's own "When Asked to Add a New Tool" checklist
has always had "register it in the orchestrator's tool schema list" as
step 3 — this is that list.

WHAT REGISTRATION PROVIDES

  1. A JSON schema per tool, derived from the function's own type hints
     and docstring, in the shape Ollama and OpenAI-style tool calling
     expect. Derived rather than hand-written: a hand-maintained schema
     drifts from its function the first time a parameter is renamed, and
     nothing fails loudly when it does — the model simply starts sending
     an argument that no longer exists.
  2. Validated dispatch by name, so a hallucinated tool name or a
     missing argument is an error the agent can see and correct rather
     than a Python traceback that kills the turn.
  3. Declared safety properties per tool, checked centrally.

THE SAFETY PROPERTIES ARE THE POINT, not bookkeeping:

  * `requires_approval` — CLAUDE.md hard constraint #4. Any tool that
    writes a file, sends anything, or touches SAP must not run until a
    human has approved it. Making that a property of the REGISTRY rather
    than of each tool's own code means the gate cannot be forgotten by
    the next person who adds a tool: the dispatcher refuses, whatever
    the tool's body does.
  * `is_estimate` — hard constraint #3. A tool whose output is a model's
    guess rather than a computed value (chart reading, OCR of a
    handwritten page) is flagged here, so a caller assembling an answer
    can carry that qualifier through instead of rediscovering it per
    tool.
  * `computes_numbers` — the inverse. Tools that produce numbers from an
    executed SymPy/Pint/CoolProp call are marked, so "did a real
    computation happen?" is answerable by inspection rather than by
    reading every tool.

WHY NOT LANGCHAIN'S @tool: it exists and is already a transitive
dependency, but its schema generation pulls in pydantic-v1 compatibility
shims and its dispatch assumes a LangChain runtime. This registry is
forty lines, has no runtime of its own, and emits the plain JSON-schema
dicts the Ollama HTTP API takes directly — which is what the router
already speaks.
"""

import inspect
import typing
from dataclasses import dataclass, field
from typing import Any, Callable

# Python annotation -> JSON Schema type. Anything not here is described
# as a string, which is the honest fallback: a model can always send a
# string, and the tool's own validation is a better place to reject a
# bad value than a schema that guesses wrong.
_JSON_TYPES: dict[Any, str] = {
    str: "string",
    int: "integer",
    float: "number",
    bool: "boolean",
    list: "array",
    dict: "object",
}


@dataclass
class ToolSpec:
    name: str
    description: str
    category: str
    func: Callable
    priority: str = "🟡"
    # Hard constraint #4: no file write / send / SAP action without an
    # approval gate. Enforced by the dispatcher, not by trust.
    requires_approval: bool = False
    # Hard constraint #3: output is a model's estimate, not a computed
    # value, and must never be presented with the confidence of one.
    is_estimate: bool = False
    # Output comes from an executed numeric library call.
    computes_numbers: bool = False
    tools_md_row: int | None = None
    parameters: dict = field(default_factory=dict)

    def to_schema(self) -> dict:
        """OpenAI/Ollama function-calling schema for this tool."""
        return {
            "type": "function",
            "function": {
                "name": self.name,
                "description": self.description,
                "parameters": self.parameters,
            },
        }


_REGISTRY: dict[str, ToolSpec] = {}


def _json_schema_for(annotation: Any) -> dict:
    if annotation is inspect.Parameter.empty:
        return {"type": "string"}

    origin = typing.get_origin(annotation)
    if origin is not None:
        args = [a for a in typing.get_args(annotation) if a is not type(None)]

        # Container types are checked BEFORE the Optional unwrap below.
        # Real bug this ordering fixes: list[float] has exactly ONE type
        # argument, so an Optional-first check treated it as
        # Optional[float] and emitted {"type": "number"} -- telling the
        # model to send a single number where the tool takes an array.
        # It would then send 5 instead of [5], and the tool would fail
        # on input the schema had explicitly asked for.
        if origin in (list, set, tuple, frozenset):
            item = args[0] if args else str
            return {"type": "array", "items": _json_schema_for(item)}
        if origin is dict:
            return {"type": "object"}

        # Optional[X] / X | None -> schema for X. The absence of a value
        # is expressed by the parameter not being required, not by a
        # nullable type, which is what tool-calling models actually emit.
        if len(args) == 1:
            return _json_schema_for(args[0])

        # Literal["line", "bar"] -> an enum, which is far more useful to
        # a model than "string": it turns a guess into a choice.
        if origin is typing.Literal:
            options = list(typing.get_args(annotation))
            return {"type": "string", "enum": options}
        return {"type": "string"}

    return {"type": _JSON_TYPES.get(annotation, "string")}


def _describe_parameters(func: Callable) -> dict:
    """Build a JSON-Schema object from the signature.

    Per-argument descriptions are pulled from a Google-style Args:
    section when the docstring has one. Tools in this repo document
    their arguments there already, so the schema the model sees is the
    same prose a developer reads — one description, not two that drift.
    """
    signature = inspect.signature(func)
    doc = inspect.getdoc(func) or ""
    arg_docs: dict[str, str] = {}

    if "Args:" in doc:
        section = doc.split("Args:", 1)[1]
        for stop in ("Returns:", "Raises:", "Example:"):
            section = section.split(stop, 1)[0]
        current = None
        for raw in section.splitlines():
            line = raw.strip()
            if not line:
                continue
            if ":" in line and not line.startswith(" ") and len(line.split(":", 1)[0].split()) == 1:
                current, _, rest = line.partition(":")
                current = current.strip()
                arg_docs[current] = rest.strip()
            elif current:
                arg_docs[current] += " " + line

    properties: dict[str, dict] = {}
    required: list[str] = []
    for name, param in signature.parameters.items():
        if name in ("self", "cls") or param.kind in (
            inspect.Parameter.VAR_POSITIONAL,
            inspect.Parameter.VAR_KEYWORD,
        ):
            continue
        schema = _json_schema_for(param.annotation)
        if name in arg_docs:
            schema["description"] = arg_docs[name]
        properties[name] = schema
        if param.default is inspect.Parameter.empty:
            required.append(name)

    return {"type": "object", "properties": properties, "required": required}


def tool(
    name: str,
    description: str,
    category: str,
    priority: str = "🟡",
    requires_approval: bool = False,
    is_estimate: bool = False,
    computes_numbers: bool = False,
    tools_md_row: int | None = None,
):
    """Register a function as an agent-callable tool.

    The wrapped function is returned unchanged, so every tool stays
    directly importable and unit-testable without going through the
    registry — registration adds a capability, it does not take one away.
    """

    def decorator(func: Callable) -> Callable:
        if name in _REGISTRY:
            raise ValueError(
                f"Tool {name!r} is already registered by "
                f"{_REGISTRY[name].func.__module__}. Names are how the model "
                f"addresses a tool, so duplicates are ambiguous, not additive."
            )
        _REGISTRY[name] = ToolSpec(
            name=name,
            description=description,
            category=category,
            func=func,
            priority=priority,
            requires_approval=requires_approval,
            is_estimate=is_estimate,
            computes_numbers=computes_numbers,
            tools_md_row=tools_md_row,
            parameters=_describe_parameters(func),
        )
        return func

    return decorator


class ApprovalRequired(Exception):
    """Raised when a gated tool is called without an approval token.

    An exception rather than a silent no-op or a False return: hard
    constraint #4 is a design law, and a caller that ignores a return
    value would sail straight past it.
    """


def get_tool(name: str) -> ToolSpec | None:
    return _REGISTRY.get(name)


def all_tools() -> list[ToolSpec]:
    return sorted(_REGISTRY.values(), key=lambda t: (t.category, t.name))


def get_tool_schemas(category: str | None = None) -> list[dict]:
    """Schemas to hand a model, optionally narrowed to one category.

    Narrowing matters: presenting all tools to every sub-agent both
    wastes context and invites a model to reach for something outside
    its remit. A vision sub-agent has no business calling the SAP
    connector.
    """
    return [
        spec.to_schema()
        for spec in all_tools()
        if category is None or spec.category == category
    ]


def call_tool(name: str, arguments: dict | None = None, approved: bool = False) -> Any:
    """Dispatch a tool call by name, with validation and the safety gate.

    Args:
        name: registered tool name, as the model emitted it.
        arguments: keyword arguments for the tool.
        approved: set only by a caller that has obtained genuine human
            approval for THIS call. Never default it to True and never
            set it from a model's own output — a model asserting that a
            human approved something is exactly the failure hard
            constraint #4 exists to prevent.

    Raises:
        KeyError: unknown tool — a model can hallucinate a plausible tool
            name, and that must be a correctable error rather than a
            crash.
        ApprovalRequired: gated tool called without approval.
        TypeError: arguments that do not fit the signature.
    """
    spec = _REGISTRY.get(name)
    if spec is None:
        raise KeyError(
            f"No tool named {name!r}. Available: {', '.join(sorted(_REGISTRY))}"
        )

    if spec.requires_approval and not approved:
        raise ApprovalRequired(
            f"{name} writes, sends, or modifies something and needs explicit human "
            f"approval before it can run (CLAUDE.md hard constraint #4)."
        )

    arguments = arguments or {}
    signature = inspect.signature(spec.func)
    accepted = set(signature.parameters)
    unexpected = set(arguments) - accepted
    if unexpected:
        # Reported rather than silently dropped: a model sending an
        # argument the tool does not take usually means it has the wrong
        # tool, and telling it so is how it recovers.
        raise TypeError(
            f"{name} does not take {sorted(unexpected)}. It takes: {sorted(accepted)}"
        )

    return spec.func(**arguments)
