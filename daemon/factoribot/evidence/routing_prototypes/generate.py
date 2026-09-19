#!/usr/bin/env python3
"""Regenerate the pinned routing prototype fixtures (task 02).

From the repository root::

    .venv/bin/python daemon/factoribot/evidence/routing_prototypes/generate.py
    .venv/bin/python daemon/factoribot/evidence/routing_prototypes/generate.py --from-slice

The first form re-cuts the pinned slice from the verified base-only
``data/data-raw-dump-2.0.77-base.json``
and rebuilds everything from it. The second form needs no dump: it rebuilds the
extract, the manifests and the pilot coverage from the checked-in slice, reusing
the source dump identity already recorded in ``manifest.json``.

Both forms are deterministic: the same slice yields byte-identical outputs.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import sys
from collections import Counter
from pathlib import Path

HERE = Path(__file__).resolve().parent
REPO_ROOT = HERE.parents[3]
sys.path.insert(0, str(REPO_ROOT / "daemon"))

from factoribot.blueprint import decode_blueprint_string  # noqa: E402
from factoribot.transport_prototypes import (  # noqa: E402
    DEFAULT_REFERENCES, PROTOTYPE_SCHEMA_VERSION, TARGET_MECHANICS_PROFILE,
    Provenance, build_manifest, build_observation_index, extract_prototypes,
    load_json, load_observations, raw_from_slice, slice_raw_dump,
)

OBSERVATION_DIR = HERE.parent / "routing_mechanics_observations"
# wip_science.txt is test data, not evidence, so it stays under daemon/tests/
# even though this generator moved into the package with the evidence it builds.
PILOT_PATH = REPO_ROOT / "daemon" / "tests" / "fixtures" / "wip_science.txt"

# Observations about the source dump itself, recorded as provenance notes. They
# describe the dump whose SHA-256 the manifest records, and nothing else.
NOTES = (
    "Exported using Factorio 2.0.77 build 84539 in isolated write and mod "
    "directories. The retained mod-list enables only base 2.0.77; core is built in.",
    "The 2.0.76 documentation and mechanics records retain their historical profile. "
    "They are incompatible with this target until a 2.0.77 observation explicitly "
    "supersedes them, so they cannot tighten an arc.",
    "The base-only dump does not define the pilot's ee-super-substation. Blueprint "
    "import still retains every such entity as visible unsupported topology; absence "
    "from this extract is not permission to delete or ignore it.",
    "source_dump_sha256 is the SHA-256 of the dump file's bytes, the identity the MCP "
    "adapter already records for loaded game data. The 'sha256:'-prefixed hashes are "
    "canonical-JSON content hashes of decoded documents, a different thing.",
)

UNAVAILABLE_PILOT_INFORMATION = (
    "Which endpoints are fed from outside the blueprint, and at what rate: unknown. "
    "No feed is inferred.",
    "Which endpoints export or dispose of material, and the external service that "
    "removes it: unknown.",
    "Global per-material input budgets for the pilot: unknown. The design's stone 30/s, "
    "copper plate 30/s, plastic 30/s, iron plate 60/s scenario is a motivating "
    "hand-check target, not a measured property of this blueprint.",
    "Research levels (inserter capacity, productivity, speed): unknown, not zero.",
    "Enabled mods and exact game build for the save this blueprint came from: unknown.",
    "Power availability and network coverage: unknown; the 3 ee-super-substation "
    "entities are unsupported topology, not evidence of a powered network.",
    "Circuit control state: the blueprint carries 2 wire entries whose enabled or "
    "disabled effect is unresolved.",
    "Per-entity recipe assignment is present for assembling machines, but the "
    "76 electric furnaces carry no recipe: their candidate set is unresolved.",
)


def write_json(path: Path, value) -> None:
    path.write_text(json.dumps(value, indent=2, sort_keys=True) + "\n")
    print(f"wrote {path.relative_to(REPO_ROOT)}")


def build_pilot_coverage(extract) -> dict:
    text = PILOT_PATH.read_text()
    file_sha = hashlib.sha256(PILOT_PATH.read_bytes()).hexdigest()
    decoded = decode_blueprint_string(text.strip())
    blueprint = decoded["blueprint"]
    entities = blueprint["entities"]
    counts = Counter(e["name"] for e in entities)

    coverage = {}
    for name, count in sorted(counts.items()):
        proto = extract.get(name)
        coverage[name] = {
            "count": count,
            "in_extract": proto is not None,
            "prototype_type": None if proto is None else proto.prototype_type,
            "subsystem": None if proto is None else proto.subsystem,
            "support": None if proto is None else proto.support,
            "origin": None if proto is None else proto.origin,
        }
    version = int(blueprint["version"])
    return {
        "schema_version": PROTOTYPE_SCHEMA_VERSION,
        "blueprint": {
            "path": "daemon/tests/fixtures/wip_science.txt",
            "file_sha256": file_sha,
            "encoded_version": version,
            "encoded_version_decoded": ".".join(str((version >> shift) & 0xFFFF)
                                                for shift in (48, 32, 16, 0)),
            "encoded_version_note": (
                "The encoded format version is a 4x16-bit packing; it records the "
                "build that wrote the string, not the prototype environment, the "
                "enabled mods or the save's research."
            ),
            "label": blueprint.get("label"),
            "entity_count": len(entities),
            "wire_count": len(blueprint.get("wires", [])),
            "tile_count": len(blueprint.get("tiles", [])),
            "entity_record_keys": sorted({k for e in entities for k in e}),
        },
        "entity_counts": {name: counts[name] for name in sorted(counts)},
        "coverage": coverage,
        "unsupported_entities": sorted(
            name for name in counts
            if extract.get(name) is None or extract.get(name).support != "supported"),
        "unresolved_prototypes": {
            name: {
                "count": counts[name],
                "reason": (
                    "absent from the verified base-only export; retained from the "
                    "blueprint as visible unsupported topology with unknown mod origin"
                ),
                "subsystem": coverage[name]["subsystem"],
            }
            for name in sorted(counts) if name == "ee-super-substation"
        },
        "unavailable_information": list(UNAVAILABLE_PILOT_INFORMATION),
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--from-slice", action="store_true",
                        help="rebuild from the checked-in slice, without the full dump")
    args = parser.parse_args()

    manifest_path = HERE / "manifest.json"
    slice_path = HERE / "raw_prototype_slice.json"

    if args.from_slice:
        if not manifest_path.exists():
            parser.error("--from-slice needs an existing manifest.json for the "
                         "source dump identity")
        dump_sha = load_json(manifest_path)["source_dump"]["sha256"]
        slice_doc = load_json(slice_path)
    else:
        from factoribot.gamedata import read_dump

        _resolved, dump_sha, raw = read_dump(
            str(REPO_ROOT / "data" / "data-raw-dump-2.0.77-base.json"))
        slice_doc = slice_raw_dump(raw)
        write_json(slice_path, slice_doc)

    provenance = Provenance(
        schema_version=PROTOTYPE_SCHEMA_VERSION,
        target_mechanics_profile=TARGET_MECHANICS_PROFILE,
        game_version="2.0.77",
        declared_mods=(("base", "2.0.77"),),
        environment_status="identified",
        matches_target_profile="yes",
        source_kind="pinned-slice",
        source_dump_path="data/data-raw-dump-2.0.77-base.json",
        source_dump_sha256=dump_sha,
        source_slice_content_hash=None,
        references=DEFAULT_REFERENCES,
        notes=NOTES,
    )
    extract = extract_prototypes(raw_from_slice(slice_doc), provenance)
    write_json(HERE / "prototypes.json", extract.to_dict())

    index = build_observation_index(load_observations(OBSERVATION_DIR / "records"))
    write_json(OBSERVATION_DIR / "manifest.json", index)

    write_json(manifest_path, build_manifest(extract, slice_doc,
                                             observation_index=index))
    write_json(HERE / "pilot_coverage.json", build_pilot_coverage(extract))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
