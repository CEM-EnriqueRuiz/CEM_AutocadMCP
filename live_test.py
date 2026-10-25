r"""End-to-end check of the AutoCAD MCP server against the running AutoCAD / Civil 3D, through MCP.

Cemengal: starts the server over stdio as Claude Desktop does (its config's autocad-mcp entry, read only,
from a folder outside the repo), calls the read tools, creates a few entities on the current layer, deletes
them by handle, and checks they are gone and the layers are unchanged. It never saves, never deletes by
layer, colour or type, and never sends undo (docs/workflows/live-test.md).
Logs to %TEMP%\Cemengal\AutocadMCP\live-test-yyyyMMdd.log, never beside this script (docs/decisions/0003).
"""
import asyncio, json, os, sys, tempfile, time
from datetime import datetime, timedelta
from pathlib import Path

REPO = Path(__file__).resolve().parent
sys.path.insert(0, str(REPO))
import win32com.client
from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import get_default_environment, stdio_client
from autocad_mcp.server import AutoCADCOMServer
from autocad_mcp.temp_files import TempFolder

TOOL_TIMEOUT = timedelta(seconds=60)  # Claude Desktop's own limit per tool call
out, failures = [], []


def p(label, obj):
    out.append(f"{label}: {json.dumps(obj, ensure_ascii=False, default=str)[:600]}")
    print(out[-1])


def check(label, ok, detail=""):
    p(f"CHECK {label}", {"ok": bool(ok), "detail": detail})
    if not ok:
        failures.append(label)


def configured_server():
    """The autocad-mcp entry of Claude Desktop's config, else this repo's .venv."""
    local, roaming = Path(os.environ.get("LOCALAPPDATA", "")), Path(os.environ.get("APPDATA", ""))
    configs = sorted(local.glob("Claude-Data/*/claude_desktop_config.json"))
    configs += sorted(local.glob("Packages/Claude*/LocalCache/Roaming/Claude/claude_desktop_config.json"))
    configs += [roaming / "Claude" / "claude_desktop_config.json"]
    for cfg in configs:
        try:
            entry = json.loads(cfg.read_text(encoding="utf-8-sig"))["mcpServers"]["autocad-mcp"]
            return str(cfg), entry["command"], entry.get("args", []), entry.get("env") or {}
        except Exception:
            continue
    return None, str(REPO / ".venv" / "Scripts" / "python.exe"), ["-m", "autocad_mcp.server"], {}


def direct_layer_count():
    """Read only, straight through COM: the drawing's layer count before the server touches it."""
    for progid in AutoCADCOMServer.candidate_progids():
        try:
            doc = win32com.client.GetActiveObject(progid).ActiveDocument
            return {"progid": progid, "drawing": str(doc.Name), "layers": int(doc.Layers.Count),
                    "entities": int(doc.ModelSpace.Count)}
        except Exception:
            continue
    return None


async def call(session, name, args=None):
    started = time.perf_counter()
    result = await session.call_tool(name, args or {}, read_timeout_seconds=TOOL_TIMEOUT)
    text = result.content[0].text if result.content else ""
    try:
        data = json.loads(text)
    except ValueError:
        data = {"raw": text}
    shown = {k: v for k, v in data.items() if k not in ("available_layers", "entities", "entities_by_layer")} \
        if isinstance(data, dict) else data
    p(f"{name} {json.dumps(args or {})} [{time.perf_counter() - started:.2f}s]", shown)
    return data


def handles_of(result):
    return result.get("handles") or ([result["handle"]] if result.get("handle") else [])


async def main():
    cfg, command, args, env = configured_server()
    p("server", {"config": cfg, "command": command, "args": args, "cwd": tempfile.gettempdir()})
    before_direct = direct_layer_count()
    p("direct COM before (read only)", before_direct)
    params = StdioServerParameters(command=command, args=args, cwd=tempfile.gettempdir(),
                                   env={**get_default_environment(), **env})
    async with stdio_client(params) as (read, write):
        async with ClientSession(read, write) as session:
            init = await session.initialize()
            p("initialize", {"server": init.serverInfo.name, "version": init.serverInfo.version})
            tools = [t.name for t in (await session.list_tools()).tools]
            p("list_tools", tools)

            info = await call(session, "get_drawing_info")
            if "error" in info:
                check("connected", False, info["error"])
                return
            layers_before = sorted(l["name"] for l in info.get("available_layers", []))
            if before_direct:
                check("a read adds no layer", info["total_layers"] == before_direct["layers"],
                      f"{before_direct['layers']} before, {info['total_layers']} after get_drawing_info")
            entities = await call(session, "get_entities", {"max_entities": 25})
            check("get_entities", "error" not in entities and entities.get("returned_count", 0) <= 25)

            made = []
            for name, arguments in [
                ("create_line", {"start": [0, 0], "end": [10, 5], "color": "red", "thickness": 0.5}),
                ("create_circle", {"center": [5, 5], "radius": 2, "color": "blue"}),
                ("create_arc", {"center": [0, 0], "radius": 3, "start_angle": 0, "end_angle": 90}),
                ("create_text", {"position": [0, -2], "text": "CEM live test", "height": 0.5}),
            ]:
                result = await call(session, name, arguments)
                check(name, result.get("success") and handles_of(result), result.get("error", ""))
                made.append((name, handles_of(result)))
            circle = next(h for n, h in made if n == "create_circle")[0]
            result = await call(session, "change_entity_color", {"handle": circle, "color": "green"})
            check("change_entity_color", result.get("success"), result.get("error", ""))

            all_handles = [h for _, hs in made for h in hs]
            text_handle = next(h for n, h in made if n == "create_text")[0]
            result = await call(session, "delete_entity_by_handle", {"handle": text_handle})
            check("delete_entity_by_handle", result.get("success"), result.get("error", ""))
            rest = [h for h in all_handles if h != text_handle]
            result = await call(session, "delete_entities_by_handles", {"handles": rest})
            check("delete_entities_by_handles", result.get("deleted_count") == len(rest) and not result.get("not_found"),
                  f"{result.get('deleted_count')} of {len(rest)}")
            result = await call(session, "delete_entities_by_handles", {"handles": all_handles})
            check("every created entity is gone", result.get("deleted_count") == 0
                  and sorted(result.get("not_found", [])) == sorted(h.upper() for h in all_handles))

            after = await call(session, "get_drawing_info")
            check("layers unchanged", sorted(l["name"] for l in after.get("available_layers", [])) == layers_before)
            p("entity count", {"before": info.get("entity_count"), "after": after.get("entity_count"),
                               "note": "another agent may be editing the same session"})
            p("never saved", {"saved_flag": after.get("saved"), "note": "Saved=false only means the drawing has edits since it was opened"})


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except Exception as e:
        check("run", False, repr(e))
    log = TempFolder().log_path("live-test")
    with open(log, "a", encoding="utf-8") as f:
        f.write(f"=== {datetime.now():%Y-%m-%d %H:%M:%S}\n" + "\n".join(out) + "\n")
    print("FAILED: " + ", ".join(failures) if failures else "ALL CHECKS PASSED")
    print("Log:", log)
    sys.exit(1 if failures else 0)
