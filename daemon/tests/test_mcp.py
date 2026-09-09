"""Exercise real stdio protocol initialization, discovery, calls and errors."""
import asyncio
import json
import sys
from datetime import timedelta

import pytest

pytest.importorskip('mcp')
pytest.importorskip('scipy')

from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client


def test_stdio_tools_without_model_credentials(tmp_path):
    raw = {
        'item': {'ore': {'type': 'item'}, 'plate': {'type': 'item'}},
        'recipe': {
            'plate': {'ingredients': [{'name': 'ore', 'amount': 2}],
                      'results': [{'name': 'plate', 'amount': 1}], 'energy_required': 1},
            'split': {'ingredients': [{'name': 'ore', 'amount': 1}],
                      'results': [{'name': 'plate', 'amount': 2}, {'name': 'slag', 'amount': 3}], 'energy_required': 1},
        },
        'assembling-machine': {'assembler': {'crafting_categories': ['crafting'], 'crafting_speed': 1, 'energy_usage': '100W'}},
    }
    data = tmp_path / 'data.json'
    data.write_text(json.dumps(raw))

    async def exercise():
        params = StdioServerParameters(command=sys.executable,
            args=['-m', 'factoribot.cli', '--data', str(data), 'mcp'],
            env={'OPENAI_API_KEY': '', 'FACTORIBOT_DATA': str(data)})
        async with stdio_client(params) as (read, write):
            async with ClientSession(read, write, read_timeout_seconds=timedelta(seconds=30)) as session:
                await session.initialize()
                listed = await session.list_tools()
                names = {tool.name for tool in listed.tools}
                assert {'plan_production', 'get_capabilities', 'analyze_blueprint', 'list_belts'} <= names
                assert all(tool.annotations.readOnlyHint for tool in listed.tools)
                cap = await session.call_tool('get_capabilities', {})
                assert cap.structuredContent['planning_available']
                assert cap.structuredContent['data']['source']['sha256']
                request = {'inputs': {'ore': 12}, 'outputs': {'plate': {'ratio': 1}},
                           'objective': {'kind': 'maximize_ratio'}}
                result = await session.call_tool('plan_production', request)
                assert not result.isError
                assert result.structuredContent['outputs_per_s']['plate'] == pytest.approx(6)
                assert json.loads(result.content[0].text) == result.structuredContent
                request['outputs']['plate'] = {'rate': 7}
                request['objective']['kind'] = 'feasible'
                failure = await session.call_tool('plan_production', request)
                assert failure.isError
                assert failure.structuredContent['error'] == 'infeasible'
                split = await session.call_tool('solve_production', {
                    'targets': [{'name': 'plate', 'rate': 2}], 'recipes': {'plate': 'split'},
                    'byproducts': ['slag'],
                })
                assert not split.isError
                line = next(x for x in split.structuredContent['summary']['lines'] if x['recipe'] == 'split')
                assert line['crafts_per_s'] == pytest.approx(1)
                assert line['output_items_per_s'] == pytest.approx({'plate': 2, 'slag': 3})
                bad_option = await session.call_tool('evaluate_throughput', {
                    'product': 'plate', 'inputs': {'ore': 2},
                    'machines': {'not-a-category': 'assembler'},
                })
                assert bad_option.isError
                assert bad_option.structuredContent['error'] == 'bad_request'
                bad = await session.call_tool('plan_production', {'inputs': {}})
                assert bad.isError
                # The server remains usable after malformed and infeasible calls.
                assert not (await session.call_tool('get_recipe', {'name': 'plate'})).isError

    asyncio.run(exercise())
