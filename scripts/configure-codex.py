#!/usr/bin/env python3
"""Register this checkout's skill and local stdio MCP server for Codex.

Only the project-local generated block and the Factoribot skill link are managed.
Existing unowned configuration/skills are never replaced. No global config changes.
"""
from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import re

START = "# BEGIN generated Factoribot MCP"
END = "# END generated Factoribot MCP"


def configure(root: Path, data: Path) -> None:
    python = root / '.venv' / 'bin' / 'python'
    skill = root / 'skills' / 'factoribot'
    config = root / '.codex' / 'config.toml'
    link = root / '.agents' / 'skills' / 'factoribot'
    if not python.is_file() or not data.is_file() or not (skill / 'SKILL.md').is_file():
        raise ValueError('Need .venv, the Factorio data dump and skills/factoribot/SKILL.md. Run setup and dump first.')
    if link.is_symlink():
        if link.resolve() != skill.resolve():
            raise ValueError(f'Refusing to replace the existing skill link at {link}.')
    elif link.exists():
        raise ValueError(f'Refusing to replace the existing skill at {link}.')
    existing = config.read_text() if config.exists() else ''
    block = '\n'.join([
        START, '[mcp_servers.factoribot]', f'command = {json.dumps(str(python))}',
        f'args = {json.dumps(["-m", "factoribot.cli", "--data", str(data), "mcp"])}',
        f'cwd = {json.dumps(str(root))}', 'startup_timeout_sec = 30', 'tool_timeout_sec = 60', END,
    ])
    if START in existing or END in existing:
        if existing.count(START) != 1 or existing.count(END) != 1 or existing.index(START) > existing.index(END):
            raise ValueError('Malformed generated Factoribot block; inspect .codex/config.toml.')
        start, end = existing.index(START), existing.index(END) + len(END)
        outside = existing[:start] + existing[end:]
        updated = existing[:start] + block + existing[end:]
    else:
        outside = existing
        updated = existing.rstrip() + ('\n\n' if existing.strip() else '') + block + '\n'
    if re.search(r'^\s*\[\s*mcp_servers\.(?:factoribot|"factoribot")(?:\s*\]|\.)', outside, re.M):
        raise ValueError('An existing Factoribot MCP configuration is not managed by this script; leaving it unchanged.')
    # All conflicts checked before making changes.
    config.parent.mkdir(parents=True, exist_ok=True)
    if updated != existing:
        config.write_text(updated)
    if not link.is_symlink():
        link.parent.mkdir(parents=True, exist_ok=True)
        link.symlink_to(os.path.relpath(skill, link.parent), target_is_directory=True)
    print(f'Skill: {link}')
    print(f'MCP: {config}')
    print('Reload the project or restart Codex if the new skill/tools are not discovered.')


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--data', type=Path, help='Factorio prototype dump; defaults to this checkout/data/data-raw-dump.json')
    args = parser.parse_args()
    root = Path(__file__).resolve().parents[1]
    try:
        configure(root, (args.data or root / 'data' / 'data-raw-dump.json').resolve())
    except (OSError, ValueError) as e:
        parser.exit(1, f'{e}\n')
