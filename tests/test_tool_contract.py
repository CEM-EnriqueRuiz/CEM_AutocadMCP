"""Every advertised tool reaches a method that exists (upstream advertised nine it never implemented),
and no name is advertised twice (upstream listed delete_entities_by_color twice)."""
import asyncio
import json

import mcp.types as types
import pytest

from autocad_mcp import server as server_module
from autocad_mcp.server import AutoCADCOMServer


def listed_tools(acad):
    acad.setup_tools()
    handler = acad.server.request_handlers[types.ListToolsRequest]
    result = asyncio.run(handler(types.ListToolsRequest(method="tools/list")))
    return result.root.tools


def call(acad, name, arguments):
    handler = acad.server.request_handlers[types.CallToolRequest]
    request = types.CallToolRequest(method="tools/call", params=types.CallToolRequestParams(name=name, arguments=arguments))
    result = asyncio.run(handler(request))
    return json.loads(result.root.content[0].text)


def sample(schema):
    kind = schema.get("type")
    if "enum" in schema:
        return schema["enum"][0]
    if kind == "array":
        return [sample(schema.get("items", {"type": "number"}))] * 2
    return {"string": "x", "number": 1.0, "integer": 1, "boolean": True,
            "object": {"start": [0, 0], "end": [1, 0]}}[kind]


def required_arguments(tool):
    props = tool.inputSchema.get("properties", {})
    return {k: sample(props[k]) for k in tool.inputSchema.get("required", [])}


@pytest.fixture
def offline(monkeypatch):
    monkeypatch.setattr(server_module, "ACAD_PROGID", "AutoCAD.Application.26")
    monkeypatch.setattr(server_module, "ACAD_AUTOSTART", False)

    def no_autocad(progid):
        raise Exception("Operation unavailable")

    monkeypatch.setattr(server_module.win32com.client, "GetActiveObject", no_autocad)
    return AutoCADCOMServer()


def test_no_tool_is_listed_twice(offline):
    names = [t.name for t in listed_tools(offline)]
    assert len(names) == len(set(names))


def test_every_listed_tool_reaches_a_method(offline):
    tools = listed_tools(offline)
    for tool in tools:
        result = call(offline, tool.name, required_arguments(tool))
        if tool.name == "delete_all_entities":
            assert result == {"error": "Refusing to delete everything: pass confirm=true"} or "Not connected" in result["error"]
            continue
        if tool.name in ("get_export_status", "cancel_export"):  # the job lives in the server, not in AutoCAD
            assert result == {"error": "Unknown export job: x"}, (tool.name, result)
            continue
        assert "Not connected to AutoCAD" in result.get("error", ""), (tool.name, result)


def test_an_unknown_tool_is_reported(offline):
    listed_tools(offline)
    handler = offline.server.request_handlers[types.CallToolRequest]
    request = types.CallToolRequest(method="tools/call",
                                    params=types.CallToolRequestParams(name="no_such_tool", arguments={}))
    result = asyncio.run(handler(request)).root
    assert result.isError or "Unknown tool" in result.content[0].text
    assert "no_such_tool" in result.content[0].text


def test_the_handshake_does_not_connect(monkeypatch):
    def fail(progid):
        raise AssertionError("connected before the first tool call")

    monkeypatch.setattr(server_module.win32com.client, "GetActiveObject", fail)
    listed_tools(AutoCADCOMServer())
