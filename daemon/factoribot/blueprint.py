"""Decode Factorio blueprint strings and extract a solver-friendly model.

A blueprint string is a version byte (``'0'``) followed by base64 of zlib-
compressed JSON; Factorio 2.0 also imports raw JSON directly. The decoded blob
is either ``{"blueprint": {...}}`` or ``{"blueprint_book": {"blueprints": [...]}}``.

We decode, flatten books, and group the crafting machines by (machine, recipe,
modules) so the analyzer can reason about capacity per recipe *stage*. Geometry
(belt routing, beacon coverage by position) is intentionally ignored here -- this
is the aggregate/ratio view, not a wiring diagram.
"""
from __future__ import annotations

import base64
import binascii
import json
import re
import zlib
from collections import defaultdict
from dataclasses import dataclass, field

from .model import Database

# A blueprint export string is a version digit followed by a long base64 run.
_BP_RE = re.compile(r"[0-9][A-Za-z0-9+/=]{60,}")


class BlueprintError(ValueError):
    """The input could not be decoded as a blueprint string."""


def decode_blueprint_string(s: str) -> dict:
    """Decode a blueprint export string (or raw JSON) into its dict form."""
    s = (s or "").strip()
    # Tolerate a pasted markdown fence around the string.
    if s.startswith("```"):
        s = s.strip("`").strip()
    if not s:
        raise BlueprintError("empty blueprint string")
    if s[0] == "{":  # 2.0 accepts uncompressed JSON
        try:
            return json.loads(s)
        except json.JSONDecodeError as e:
            raise BlueprintError(f"looks like JSON but won't parse: {e}") from e
    body = s[1:]  # skip the version byte
    try:
        return json.loads(zlib.decompress(base64.b64decode(body)).decode("utf-8"))
    except (binascii.Error, zlib.error, UnicodeDecodeError, json.JSONDecodeError) as e:
        raise BlueprintError(
            "not a valid blueprint string "
            "(expected a version byte followed by base64 of zlib-compressed JSON)"
        ) from e


def find_blueprint_string(text: str) -> str | None:
    """Pull a blueprint string out of free text (e.g. a pasted chat message).

    Returns the first long base64-ish run that actually decodes, so we can route
    a pasted blueprint to the analyzer without sending it through the LLM.
    """
    for m in _BP_RE.finditer(text or ""):
        cand = m.group(0)
        try:
            decode_blueprint_string(cand)
            return cand
        except BlueprintError:
            continue
    return None


def iter_blueprints(decoded: dict) -> list[dict]:
    """Flatten a decoded blob into the list of individual blueprint dicts.

    A blueprint book may nest books; entries look like ``{"index", "blueprint"}``
    or ``{"index", "blueprint_book"}``. Upgrade-planners/deconstruction-planners
    carry no entities and are skipped.
    """
    if not isinstance(decoded, dict):
        return []
    if "blueprint" in decoded:
        return [decoded["blueprint"]]
    book = decoded.get("blueprint_book")
    if book:
        out: list[dict] = []
        for entry in book.get("blueprints", []):
            out.extend(iter_blueprints(entry))
        return out
    if "entities" in decoded:  # already a bare blueprint
        return [decoded]
    return []


def _parse_modules(entity: dict) -> dict[str, int]:
    """Module name -> count for an entity, tolerating 1.x and 2.0 shapes.

    1.x: ``items = {"productivity-module-3": 2}``.
    2.0: ``items = [{"id": {"name", "quality"}, "items": {"in_inventory": [...]}}]``.
    We only sum counts by module name; quality and slot positions are ignored.
    """
    items = entity.get("items")
    if not items:
        return {}
    out: dict[str, int] = defaultdict(int)
    if isinstance(items, dict):  # 1.x
        for name, count in items.items():
            try:
                out[name] += int(count)
            except (TypeError, ValueError):
                out[name] += 1
    elif isinstance(items, list):  # 2.0
        for it in items:
            if not isinstance(it, dict):
                continue
            ident = it.get("id")
            name = ident.get("name") if isinstance(ident, dict) else ident
            if not name:
                continue
            inv = ((it.get("items") or {}).get("in_inventory")) or []
            n = sum(int(slot.get("count", 1)) for slot in inv) if inv else 1
            out[name] += n
    return dict(out)


@dataclass
class MachineGroup:
    """A run of identical crafting machines: same prototype, recipe, and modules."""

    machine: str  # entity prototype name, e.g. "assembling-machine-2"
    recipe: str | None  # recipe set on the machine, or None (e.g. furnaces)
    count: int
    modules: dict[str, int] = field(default_factory=dict)  # per-machine modules


@dataclass
class BlueprintSummary:
    """The aggregate, geometry-free view of one blueprint."""

    label: str | None
    groups: list[MachineGroup]  # crafting machines with a recipe set, grouped
    no_recipe: dict[str, int]  # crafting machine name -> count, recipe unset
    beacons: dict[str, int]  # beacon name -> count
    beacon_modules: dict[str, int]  # module name -> total count across beacons
    belts: dict[str, int]  # transport-belt name -> count
    other: dict[str, int]  # everything else (inserters, poles, modded, ...)
    total_entities: int


def summarize_blueprint(bp: dict, db: Database) -> BlueprintSummary:
    """Group a blueprint's entities into the analyzer's vocabulary using `db`."""
    ents = bp.get("entities") or []
    grouped: dict[tuple, int] = defaultdict(int)
    group_mods: dict[tuple, dict[str, int]] = {}
    no_recipe: dict[str, int] = defaultdict(int)
    beacons: dict[str, int] = defaultdict(int)
    beacon_modules: dict[str, int] = defaultdict(int)
    belts: dict[str, int] = defaultdict(int)
    other: dict[str, int] = defaultdict(int)

    for e in ents:
        name = e.get("name") if isinstance(e, dict) else None
        if not name:
            continue
        if name in db.machines:
            recipe = e.get("recipe")
            mods = _parse_modules(e)
            if recipe:
                key = (name, recipe, tuple(sorted(mods.items())))
                grouped[key] += 1
                group_mods[key] = mods
            else:
                no_recipe[name] += 1
        elif name in db.beacons:
            beacons[name] += 1
            for m, c in _parse_modules(e).items():
                beacon_modules[m] += c
        elif name in db.belts:
            belts[name] += 1
        else:
            other[name] += 1

    groups = [
        MachineGroup(machine=k[0], recipe=k[1], count=n, modules=dict(group_mods[k]))
        for k, n in sorted(grouped.items(), key=lambda kv: (-kv[1], kv[0]))
    ]
    return BlueprintSummary(
        label=bp.get("label"),
        groups=groups,
        no_recipe=dict(no_recipe),
        beacons=dict(beacons),
        beacon_modules=dict(beacon_modules),
        belts=dict(belts),
        other=dict(other),
        total_entities=len(ents),
    )


# ---------------------------------------------------------------------------
# Bounded decode/encode and explicit book selection (routing task 03).
#
# Everything below is additive. The legacy `decode_blueprint_string` /
# `iter_blueprints` pair keeps its exact behaviour: it is the aggregate tool's
# entry point and flattens books, which loses the path an entity was found at.
# The routing model needs the opposite: the *whole* decoded document as the
# preservation boundary, an explicit selection path, and hard limits enforced
# while decompressing rather than after an unbounded allocation.
# ---------------------------------------------------------------------------

#: Longest accepted encoded blueprint string. Cheap pre-filter before base64.
MAX_ENCODED_CHARS = 16 * 1024 * 1024
#: Contract's provisional decoded-byte ceiling (docs/blueprint-routing-contract.md).
MAX_DECOMPRESSED_BYTES = 32 * 1024 * 1024
#: Deepest JSON container nesting accepted in a decoded document.
MAX_JSON_DEPTH = 64
#: Contract's provisional normalized-entity ceiling, counted per leaf blueprint.
MAX_ENTITIES = 10_000

_DECOMPRESS_CHUNK = 256 * 1024


class BlueprintDecodeError(BlueprintError):
    """A structured decode/selection failure.

    Subclasses `BlueprintError` so existing callers keep catching one type;
    `code` names the machine-readable reason and `detail` carries the numbers.
    """

    def __init__(self, code: str, message: str, **detail):
        super().__init__(message)
        self.code = code
        self.detail = detail


@dataclass(frozen=True)
class DecodeLimits:
    """Resource ceilings applied while decoding one blueprint document."""

    max_encoded_chars: int = MAX_ENCODED_CHARS
    max_decompressed_bytes: int = MAX_DECOMPRESSED_BYTES
    max_depth: int = MAX_JSON_DEPTH
    max_entities: int = MAX_ENTITIES


DEFAULT_LIMITS = DecodeLimits()


def _inflate(payload: bytes, limit: int) -> bytes:
    """Inflate `payload`, refusing to allocate more than `limit` bytes.

    The limit is enforced *during* decompression: `decompressobj.decompress`
    is called with `max_length`, so a zip bomb stops at the ceiling instead of
    being fully expanded and measured afterwards.
    """
    obj = zlib.decompressobj()
    out = bytearray()
    pending = payload
    while True:
        want = limit - len(out) + 1  # +1 so overflow is observable
        chunk = obj.decompress(pending, min(want, _DECOMPRESS_CHUNK))
        out += chunk
        if len(out) > limit:
            raise BlueprintDecodeError(
                "decompressed_limit",
                f"decompressed blueprint exceeds {limit} bytes",
                limit=limit,
            )
        pending = obj.unconsumed_tail
        if obj.eof:
            break
        if not pending and not chunk:
            raise BlueprintDecodeError(
                "truncated_stream", "compressed blueprint data ended early"
            )
    return bytes(out)


def _check_depth(value, limit: int) -> None:
    """Reject documents nested deeper than `limit` containers."""
    stack = [(value, 1)]
    while stack:
        node, depth = stack.pop()
        if isinstance(node, dict):
            children = node.values()
        elif isinstance(node, list):
            children = node
        else:
            continue
        if depth > limit:
            raise BlueprintDecodeError(
                "nesting_limit", f"document nests deeper than {limit} levels", limit=limit
            )
        for child in children:
            stack.append((child, depth + 1))


def decode_blueprint(text: str, limits: DecodeLimits = DEFAULT_LIMITS) -> dict:
    """Decode an encoded string or raw JSON into the complete document.

    Unlike `decode_blueprint_string` this bounds the encoded length, the
    decompressed size (during decompression) and the nesting depth, and it
    fails with `BlueprintDecodeError` codes rather than one opaque message.
    The returned value is the entire root document; nothing is flattened,
    dropped or normalized here.
    """
    text = (text or "").strip()
    if text.startswith("```"):
        text = text.strip("`").strip()
    if not text:
        raise BlueprintDecodeError("empty_input", "empty blueprint string")
    if len(text) > limits.max_encoded_chars:
        raise BlueprintDecodeError(
            "encoded_limit",
            f"encoded blueprint exceeds {limits.max_encoded_chars} characters",
            limit=limits.max_encoded_chars,
            length=len(text),
        )
    if text[0] == "{":
        raw = text.encode("utf-8")
        if len(raw) > limits.max_decompressed_bytes:
            raise BlueprintDecodeError(
                "decompressed_limit",
                f"raw JSON blueprint exceeds {limits.max_decompressed_bytes} bytes",
                limit=limits.max_decompressed_bytes,
            )
    else:
        try:
            payload = base64.b64decode(text[1:], validate=False)
        except (binascii.Error, ValueError) as exc:
            raise BlueprintDecodeError("invalid_base64", f"invalid base64 body: {exc}") from exc
        if not payload:
            raise BlueprintDecodeError("invalid_base64", "empty base64 body")
        try:
            raw = _inflate(payload, limits.max_decompressed_bytes)
        except zlib.error as exc:
            raise BlueprintDecodeError("invalid_deflate", f"invalid deflate stream: {exc}") from exc
    try:
        document = json.loads(raw.decode("utf-8"))
    except UnicodeDecodeError as exc:
        raise BlueprintDecodeError("invalid_utf8", f"decoded bytes are not UTF-8: {exc}") from exc
    except RecursionError as exc:
        raise BlueprintDecodeError("nesting_limit", "document nests too deeply to parse") from exc
    except json.JSONDecodeError as exc:
        raise BlueprintDecodeError("invalid_json", f"decoded payload is not JSON: {exc}") from exc
    if not isinstance(document, dict):
        raise BlueprintDecodeError(
            "invalid_document", "blueprint document must be a JSON object"
        )
    _check_depth(document, limits.max_depth)
    return document


def encode_blueprint(document: dict) -> str:
    """Re-encode a decoded document as a Factorio blueprint string.

    Round-tripping is *semantic*: `decode_blueprint(encode_blueprint(d)) == d`.
    Byte equality with the original string is not attempted and not required,
    because key order and deflate parameters are not part of the format.
    """
    if not isinstance(document, dict):
        raise BlueprintDecodeError(
            "invalid_document", "blueprint document must be a JSON object"
        )
    try:
        body = json.dumps(document, separators=(",", ":"), ensure_ascii=False, allow_nan=False)
    except ValueError as exc:
        raise BlueprintDecodeError("invalid_document", f"document is not JSON-encodable: {exc}") from exc
    return "0" + base64.b64encode(zlib.compress(body.encode("utf-8"), 9)).decode("ascii")


#: Document keys that hold an addressable planner/blueprint payload.
LEAF_KINDS = ("blueprint", "blueprint_book", "upgrade_planner", "deconstruction_planner")


@dataclass(frozen=True)
class BookEntry:
    """One addressable entry of a decoded document.

    `path` is the sequence of book entry **index values** used by the routing
    contract's `EntityId.book_path` -- never array offsets. The root document
    has path `()`. `record` is the original nested dict, not a copy.
    """

    path: tuple[int, ...]
    kind: str
    record: dict


def _entry_payload(entry: dict) -> tuple[str, dict] | None:
    for kind in LEAF_KINDS:
        payload = entry.get(kind)
        if isinstance(payload, dict):
            return kind, payload
    return None


def walk_entries(document: dict, limits: DecodeLimits = DEFAULT_LIMITS) -> list[BookEntry]:
    """Every addressable entry of `document`, books included, in document order.

    Unselected and unsupported entries (planners, empty books) are returned too:
    they stay visible so a caller can report what it did *not* select.
    """
    if not isinstance(document, dict):
        raise BlueprintDecodeError("invalid_document", "blueprint document must be a JSON object")
    found = _entry_payload(document)
    if found is None:
        if "entities" in document:  # a bare blueprint record
            return [BookEntry((), "blueprint", document)]
        return []
    out: list[BookEntry] = []
    stack: list[tuple[tuple[int, ...], str, dict]] = [((), found[0], found[1])]
    while stack:
        path, kind, record = stack.pop(0)
        out.append(BookEntry(path, kind, record))
        if kind != "blueprint_book":
            continue
        if len(path) >= limits.max_depth:
            raise BlueprintDecodeError(
                "nesting_limit",
                f"blueprint book nests deeper than {limits.max_depth} levels",
                limit=limits.max_depth,
            )
        entries = record.get("blueprints")
        if entries is None:
            continue
        if not isinstance(entries, list):
            raise BlueprintDecodeError(
                "malformed_book", "blueprint_book 'blueprints' must be an array",
                path=list(path),
            )
        seen: set[int] = set()
        children: list[tuple[tuple[int, ...], str, dict]] = []
        for offset, entry in enumerate(entries):
            if not isinstance(entry, dict):
                raise BlueprintDecodeError(
                    "malformed_book", "book entry must be an object",
                    path=list(path), offset=offset,
                )
            index = entry.get("index")
            if type(index) is not int or index < 0:
                raise BlueprintDecodeError(
                    "malformed_book",
                    "book entry needs a nonnegative integer 'index'",
                    path=list(path), offset=offset, index=index,
                )
            if index in seen:
                raise BlueprintDecodeError(
                    "duplicate_book_index",
                    f"book at {list(path)} has two entries with index {index}",
                    path=list(path), index=index,
                )
            seen.add(index)
            payload = _entry_payload(entry)
            if payload is None:
                continue
            children.append((path + (index,), payload[0], payload[1]))
        stack = children + stack
    return out


def parse_selection_path(value) -> tuple[int, ...]:
    """Normalize a selection path from a sequence or a `bp/2/7` style string."""
    if isinstance(value, str):
        text = value.strip().removeprefix("bp/")
        if text in ("", "root"):
            return ()
        parts = text.split("/")
    elif isinstance(value, (list, tuple)):
        parts = list(value)
    elif value is None:
        return ()
    else:
        raise BlueprintDecodeError(
            "malformed_selection_path", f"selection path must be a sequence or string, got {type(value).__name__}"
        )
    out: list[int] = []
    for part in parts:
        if isinstance(part, bool) or not isinstance(part, (int, str)):
            raise BlueprintDecodeError(
                "malformed_selection_path", f"invalid selection path component {part!r}"
            )
        if isinstance(part, str):
            if not part.isdigit():
                raise BlueprintDecodeError(
                    "malformed_selection_path", f"invalid selection path component {part!r}"
                )
            part = int(part)
        if part < 0:
            raise BlueprintDecodeError(
                "malformed_selection_path", f"negative selection path component {part!r}"
            )
        out.append(part)
    return tuple(out)


def select_blueprint(
    document: dict, path=(), limits: DecodeLimits = DEFAULT_LIMITS
) -> dict:
    """Return the blueprint record at `path`, raising a structured error.

    `path` is the agreed sequence of book entry index values; `()` selects a
    standalone blueprint. The returned dict is the original record.
    """
    wanted = parse_selection_path(path)
    entries = walk_entries(document, limits)
    for entry in entries:
        if entry.path != wanted:
            continue
        if entry.kind != "blueprint":
            raise BlueprintDecodeError(
                "not_a_blueprint",
                f"entry at {list(wanted)} is a {entry.kind}, not a blueprint",
                path=list(wanted), kind=entry.kind,
            )
        return entry.record
    raise BlueprintDecodeError(
        "unknown_selection_path",
        f"no blueprint entry at {list(wanted)}",
        path=list(wanted),
        available=[list(e.path) for e in entries if e.kind == "blueprint"],
    )


def blueprint_leaves(document: dict, limits: DecodeLimits = DEFAULT_LIMITS) -> list[BookEntry]:
    """Every blueprint leaf of `document`, each with its selection path."""
    return [e for e in walk_entries(document, limits) if e.kind == "blueprint"]
