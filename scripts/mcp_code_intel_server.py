#!/usr/bin/env python3
"""MCP server for code intelligence queries."""

import json
import re
import sqlite3
from pathlib import Path
from typing import Any

import anyio
from mcp.server import Server
from mcp.server.stdio import stdio_server
from mcp.types import Tool, TextContent, CallToolResult


# Initialize MCP server
server = Server("worker-flash-code-intel")


def get_db_path() -> Path:
    """Get database path relative to project root."""
    project_root = Path(__file__).parent.parent
    return project_root / ".code-intel" / "flash.db"


def get_connection() -> sqlite3.Connection:
    """Get database connection."""
    db_path = get_db_path()
    if not db_path.exists():
        raise FileNotFoundError(
            f"Database not found at {db_path}. Run 'make index' to generate it."
        )
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    return conn


@server.list_tools()
async def list_tools() -> list[Tool]:
    """List available tools."""
    return [
        Tool(
            name="find_symbol",
            description="Find classes, functions, or methods by name (partial match). Returns up to 50 results.",
            inputSchema={
                "type": "object",
                "properties": {
                    "symbol": {
                        "type": "string",
                        "description": "Symbol name to search (supports partial matches)",
                    }
                },
                "required": ["symbol"],
            },
        ),
        Tool(
            name="list_classes",
            description="List all classes in the codebase",
            inputSchema={"type": "object", "properties": {}, "required": []},
        ),
        Tool(
            name="get_class_interface",
            description="Get the interface of a class (methods without implementations)",
            inputSchema={
                "type": "object",
                "properties": {
                    "class_name": {"type": "string", "description": "Name of the class"}
                },
                "required": ["class_name"],
            },
        ),
        Tool(
            name="list_file_symbols",
            description="List all symbols in a specific file",
            inputSchema={
                "type": "object",
                "properties": {
                    "file_path": {
                        "type": "string",
                        "description": "File path (relative to project root, supports partial matches)",
                    }
                },
                "required": ["file_path"],
            },
        ),
        Tool(
            name="find_by_decorator",
            description="Find symbols with specific decorators",
            inputSchema={
                "type": "object",
                "properties": {
                    "decorator": {"type": "string", "description": "Decorator name to search for"}
                },
                "required": ["decorator"],
            },
        ),
        Tool(
            name="parse_test_output",
            description="Parse pytest output to extract test failures, errors, and coverage data. Use this after running pytest commands to analyze results efficiently. Returns structured summary of passed/failed/error counts, list of failed tests with error messages, and coverage percentage vs threshold. Provides 99% token reduction (200 tokens vs 20,000+) compared to reading raw output.",
            inputSchema={
                "type": "object",
                "properties": {
                    "output": {
                        "type": "string",
                        "description": "Raw pytest output text from running tests",
                    }
                },
                "required": ["output"],
            },
        ),
    ]


@server.call_tool()
async def call_tool(name: str, arguments: dict[str, Any]) -> CallToolResult:
    """Handle tool calls."""
    if name == "find_symbol":
        return await find_symbol(arguments["symbol"])
    elif name == "list_classes":
        return await list_classes()
    elif name == "get_class_interface":
        return await get_class_interface(arguments["class_name"])
    elif name == "list_file_symbols":
        return await list_file_symbols(arguments["file_path"])
    elif name == "find_by_decorator":
        return await find_by_decorator(arguments["decorator"])
    elif name == "parse_test_output":
        return await parse_test_output(arguments["output"])
    else:
        return CallToolResult(
            content=[TextContent(type="text", text=f"Unknown tool: {name}")], isError=True
        )


async def find_symbol(symbol: str) -> CallToolResult:
    """Find symbols by name (partial match)."""
    try:
        conn = get_connection()
        cursor = conn.cursor()

        cursor.execute(
            """
            SELECT file_path, symbol_name, kind, signature, start_line, docstring
            FROM symbols
            WHERE symbol_name LIKE ?
            ORDER BY kind, symbol_name
            LIMIT 50
        """,
            (f"%{symbol}%",),
        )

        rows = cursor.fetchall()
        conn.close()

        if not rows:
            return CallToolResult(
                content=[TextContent(type="text", text=f"No symbols found matching '{symbol}'")],
                isError=False,
            )

        result_text = f"Found {len(rows)} symbol(s) matching '{symbol}'"
        if len(rows) == 50:
            result_text += " (showing first 50 results, there may be more)"
        result_text += ":\n\n"
        for row in rows:
            result_text += f"**{row['symbol_name']}** ({row['kind']})\n"
            result_text += f"  File: {row['file_path']}:{row['start_line']}\n"
            if row["signature"]:
                result_text += f"  Signature: `{row['signature']}`\n"
            if row["docstring"]:
                first_line = row["docstring"].split("\n")[0]
                result_text += f"  Doc: {first_line}\n"
            result_text += "\n"

        return CallToolResult(content=[TextContent(type="text", text=result_text)], isError=False)

    except Exception as e:
        return CallToolResult(
            content=[TextContent(type="text", text=f"Error: {str(e)}")], isError=True
        )


async def list_classes() -> CallToolResult:
    """List all classes in the codebase."""
    try:
        conn = get_connection()
        cursor = conn.cursor()

        cursor.execute("""
            SELECT file_path, symbol_name, signature, start_line
            FROM symbols
            WHERE kind = 'class'
            ORDER BY file_path, symbol_name
            LIMIT 100
        """)

        rows = cursor.fetchall()
        conn.close()

        if not rows:
            return CallToolResult(
                content=[TextContent(type="text", text="No classes found")], isError=False
            )

        result_text = f"Found {len(rows)} class(es):\n\n"
        current_file = None

        for row in rows:
            if row["file_path"] != current_file:
                current_file = row["file_path"]
                result_text += f"**{current_file}**\n"

            result_text += f"  - `{row['symbol_name']}` (line {row['start_line']})\n"

        return CallToolResult(content=[TextContent(type="text", text=result_text)], isError=False)

    except Exception as e:
        return CallToolResult(
            content=[TextContent(type="text", text=f"Error: {str(e)}")], isError=True
        )


async def get_class_interface(class_name: str) -> CallToolResult:
    """Get the interface of a class (methods without implementations)."""
    try:
        conn = get_connection()
        cursor = conn.cursor()

        # Get class definition
        cursor.execute(
            """
            SELECT symbol_name, file_path, signature, docstring, start_line
            FROM symbols
            WHERE symbol_name = ? AND kind = 'class'
            LIMIT 1
        """,
            (class_name,),
        )

        class_row = cursor.fetchone()

        if not class_row:
            return CallToolResult(
                content=[TextContent(type="text", text=f"Class '{class_name}' not found")],
                isError=False,
            )

        # Get all methods
        cursor.execute(
            """
            SELECT symbol_name, signature, docstring, start_line, decorator_json
            FROM symbols
            WHERE parent_symbol = ? AND kind = 'method'
            ORDER BY start_line
        """,
            (class_name,),
        )

        methods = cursor.fetchall()
        conn.close()

        result_text = f"**Class: {class_row['symbol_name']}**\n"
        result_text += f"File: {class_row['file_path']}:{class_row['start_line']}\n\n"

        if class_row["docstring"]:
            result_text += f"Docstring:\n```\n{class_row['docstring']}\n```\n\n"

        result_text += f"**Methods ({len(methods)}):**\n\n"

        for method in methods:
            decorators = json.loads(method["decorator_json"] or "[]")
            if decorators:
                for dec in decorators:
                    result_text += f"  @{dec}\n"

            result_text += f"  `{method['signature']}`\n"

            if method["docstring"]:
                first_line = method["docstring"].split("\n")[0]
                result_text += f"    {first_line}\n"

            result_text += "\n"

        return CallToolResult(content=[TextContent(type="text", text=result_text)], isError=False)

    except Exception as e:
        return CallToolResult(
            content=[TextContent(type="text", text=f"Error: {str(e)}")], isError=True
        )


async def list_file_symbols(file_path: str) -> CallToolResult:
    """List all symbols in a specific file."""
    try:
        conn = get_connection()
        cursor = conn.cursor()

        cursor.execute(
            """
            SELECT symbol_name, kind, signature, start_line, parent_symbol
            FROM symbols
            WHERE file_path LIKE ?
            ORDER BY start_line
            LIMIT 100
        """,
            (f"%{file_path}%",),
        )

        rows = cursor.fetchall()
        conn.close()

        if not rows:
            return CallToolResult(
                content=[TextContent(type="text", text=f"No symbols found in '{file_path}'")],
                isError=False,
            )

        result_text = f"Symbols in '{file_path}' ({len(rows)} total):\n\n"

        for row in rows:
            indent = "  " if row["parent_symbol"] else ""
            result_text += (
                f"{indent}`{row['symbol_name']}` ({row['kind']}, line {row['start_line']})\n"
            )

            if row["signature"]:
                result_text += f"{indent}  Signature: `{row['signature']}`\n"

        return CallToolResult(content=[TextContent(type="text", text=result_text)], isError=False)

    except Exception as e:
        return CallToolResult(
            content=[TextContent(type="text", text=f"Error: {str(e)}")], isError=True
        )


async def find_by_decorator(decorator: str) -> CallToolResult:
    """Find symbols with specific decorators."""
    try:
        conn = get_connection()
        cursor = conn.cursor()

        cursor.execute(
            """
            SELECT file_path, symbol_name, kind, signature, start_line, decorator_json
            FROM symbols
            WHERE decorator_json LIKE ?
            ORDER BY kind, symbol_name
            LIMIT 50
        """,
            (f"%{decorator}%",),
        )

        rows = cursor.fetchall()
        conn.close()

        if not rows:
            return CallToolResult(
                content=[
                    TextContent(type="text", text=f"No symbols found with decorator '@{decorator}'")
                ],
                isError=False,
            )

        result_text = f"Found {len(rows)} symbol(s) with decorator '@{decorator}':\n\n"

        for row in rows:
            result_text += f"**{row['symbol_name']}** ({row['kind']})\n"
            result_text += f"  File: {row['file_path']}:{row['start_line']}\n"

            decorators = json.loads(row["decorator_json"] or "[]")
            for dec in decorators:
                result_text += f"  @{dec}\n"

            if row["signature"]:
                result_text += f"  Signature: `{row['signature']}`\n"

            result_text += "\n"

        return CallToolResult(content=[TextContent(type="text", text=result_text)], isError=False)

    except Exception as e:
        return CallToolResult(
            content=[TextContent(type="text", text=f"Error: {str(e)}")], isError=True
        )


async def parse_test_output(output: str) -> CallToolResult:
    """Parse pytest output to extract failures and coverage data."""
    try:
        # Extract test counts from summary line
        passed_match = re.search(r"(\d+)\s+passed", output)
        failed_match = re.search(r"(\d+)\s+failed", output)
        error_match = re.search(r"(\d+)\s+error", output)
        deselected_match = re.search(r"(\d+)\s+deselected", output)
        skipped_match = re.search(r"(\d+)\s+skipped", output)

        passed_count = int(passed_match.group(1)) if passed_match else 0
        failed_count = int(failed_match.group(1)) if failed_match else 0
        error_count = int(error_match.group(1)) if error_match else 0
        deselected_count = int(deselected_match.group(1)) if deselected_match else 0
        skipped_count = int(skipped_match.group(1)) if skipped_match else 0

        # Extract failed tests and their error messages
        failed_pattern = r"(FAILED|ERROR)\s+([\w/\-\.]+::\w+)\s*(?:-\s+(.+))?$"
        failed_tests = []
        for line in output.split("\n"):
            match = re.search(failed_pattern, line)
            if match:
                status, test_id, error_msg = match.groups()
                failed_tests.append(
                    {"status": status, "test_id": test_id, "error": error_msg or ""}
                )

        # Extract coverage data
        coverage_match = re.search(r"^TOTAL\s+.*?(\d+\.\d+)%", output, re.MULTILINE)
        if not coverage_match:
            coverage_match = re.search(r"coverage:\s*(\d+\.\d+)%", output)

        coverage_pct = float(coverage_match.group(1)) if coverage_match else None

        # Extract coverage threshold requirement
        threshold_match = re.search(r"Required test coverage of (\d+(?:\.\d+)?)%", output)
        threshold_pct = float(threshold_match.group(1)) if threshold_match else None

        # Format output
        result_text = format_test_summary(
            passed_count,
            failed_count,
            error_count,
            deselected_count,
            skipped_count,
            failed_tests,
            coverage_pct,
            threshold_pct,
        )

        return CallToolResult(content=[TextContent(type="text", text=result_text)], isError=False)

    except Exception as e:
        return CallToolResult(
            content=[TextContent(type="text", text=f"Error parsing test output: {str(e)}")],
            isError=True,
        )


def format_test_summary(
    passed: int,
    failed: int,
    errors: int,
    deselected: int,
    skipped: int,
    failed_tests: list[dict[str, str]],
    coverage: float | None,
    threshold: float | None,
) -> str:
    """Format parsed test data as markdown."""
    result = "## Test Summary\n\n"

    # Test counts
    total = passed + failed + errors + skipped
    result += f"**Total Tests:** {total}\n"
    result += f"✅ Passed: {passed}\n"

    if failed > 0:
        result += f"❌ Failed: {failed}\n"
    if errors > 0:
        result += f"⚠️ Errors: {errors}\n"
    if skipped > 0:
        result += f"⏭️ Skipped: {skipped}\n"
    if deselected > 0:
        result += f"⊘ Deselected: {deselected}\n"

    result += "\n"

    # Failed tests details
    if failed_tests:
        result += "### Failed Tests\n\n"
        for test in failed_tests:
            result += f"- **{test['status']}** `{test['test_id']}`\n"
            if test["error"]:
                result += f"  {test['error']}\n"
        result += "\n"

    # Coverage
    if coverage is not None:
        result += "### Coverage\n\n"
        if threshold is not None:
            if coverage >= threshold:
                result += f"✅ Coverage: {coverage}% (meets {threshold}% requirement)\n"
            else:
                result += f"❌ Coverage: {coverage}% (below {threshold}% requirement)\n"
        else:
            result += f"Coverage: {coverage}%\n"

    return result


async def main() -> None:
    """Run the MCP server."""
    async with stdio_server() as (read_stream, write_stream):
        await server.run(
            read_stream,
            write_stream,
            server.create_initialization_options(),
        )


if __name__ == "__main__":
    anyio.run(main)
