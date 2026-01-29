#!/usr/bin/env python3
"""CLI tool for querying code intelligence database."""

import json
import sqlite3
from pathlib import Path
from typing import Optional

import typer
from rich.console import Console
from rich.table import Table


app = typer.Typer(help="Query code intelligence database for worker-tetra")
console = Console()


def get_db_path() -> Path:
    """Get database path."""
    project_root = Path(__file__).parent.parent
    return project_root / ".code-intel" / "flash.db"


def check_db_exists() -> Path:
    """Check if database exists and return path."""
    db_path = get_db_path()
    if not db_path.exists():
        console.print(
            f"[red]Error:[/red] Database not found at {db_path}\n"
            "Run [cyan]make index[/cyan] to generate it.",
            style="bold",
        )
        raise typer.Exit(1)
    return db_path


def get_connection(db_path: Path) -> sqlite3.Connection:
    """Get database connection."""
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    return conn


@app.command()
def find(symbol: str) -> None:
    """Find classes, functions, or methods by name (partial match)."""
    db_path = check_db_exists()
    conn = get_connection(db_path)
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
        console.print(f"[yellow]No symbols found matching[/yellow] '{symbol}'")
        return

    table = Table(title=f"Symbols matching '{symbol}'", show_lines=True)
    table.add_column("Name", style="cyan")
    table.add_column("Kind", style="magenta")
    table.add_column("Location", style="green")
    table.add_column("Signature", style="blue", no_wrap=False)

    for row in rows:
        location = f"{row['file_path']}:{row['start_line']}"
        sig = row["signature"] or ""
        table.add_row(row["symbol_name"], row["kind"], location, sig)

    console.print(table)


@app.command("list-all")
def list_all(
    kind: Optional[str] = typer.Option(None, help="Filter by kind (class/function/method)"),
) -> None:
    """List all symbols in the codebase."""
    db_path = check_db_exists()
    conn = get_connection(db_path)
    cursor = conn.cursor()

    if kind:
        cursor.execute(
            """
            SELECT file_path, symbol_name, kind, start_line
            FROM symbols
            WHERE kind = ?
            ORDER BY file_path, symbol_name
            LIMIT 200
        """,
            (kind,),
        )
        title = f"All {kind}s"
    else:
        cursor.execute("""
            SELECT file_path, symbol_name, kind, start_line
            FROM symbols
            ORDER BY file_path, kind, symbol_name
            LIMIT 200
        """)
        title = "All Symbols"

    rows = cursor.fetchall()
    conn.close()

    if not rows:
        console.print("[yellow]No symbols found[/yellow]")
        return

    table = Table(title=title)
    table.add_column("Name", style="cyan")
    table.add_column("Kind", style="magenta")
    table.add_column("File", style="green")
    table.add_column("Line", style="yellow")

    for row in rows:
        table.add_row(row["symbol_name"], row["kind"], row["file_path"], str(row["start_line"]))

    console.print(table)


@app.command()
def interface(class_name: str) -> None:
    """Get the interface of a class (methods without implementations)."""
    db_path = check_db_exists()
    conn = get_connection(db_path)
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
        console.print(f"[red]Class '{class_name}' not found[/red]")
        conn.close()
        raise typer.Exit(1)

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

    # Print class info
    console.print(f"\n[bold cyan]Class: {class_row['symbol_name']}[/bold cyan]")
    console.print(f"[dim]File: {class_row['file_path']}:{class_row['start_line']}[/dim]\n")

    if class_row["docstring"]:
        console.print("[bold]Docstring:[/bold]")
        console.print(f"[dim]{class_row['docstring']}[/dim]\n")

    # Print methods table
    table = Table(title=f"Methods ({len(methods)})")
    table.add_column("Method", style="cyan")
    table.add_column("Signature", style="blue", no_wrap=False)
    table.add_column("Decorators", style="yellow")

    for method in methods:
        decorators = json.loads(method["decorator_json"] or "[]")
        dec_str = ", ".join(f"@{d}" for d in decorators) if decorators else ""
        table.add_row(method["symbol_name"], method["signature"] or "", dec_str)

    console.print(table)


@app.command()
def file(file_path: str) -> None:
    """List all symbols in a specific file."""
    db_path = check_db_exists()
    conn = get_connection(db_path)
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
        console.print(f"[yellow]No symbols found in '{file_path}'[/yellow]")
        return

    # Group symbols by type
    classes = [r for r in rows if r["kind"] == "class"]
    functions = [r for r in rows if r["kind"] == "function"]
    methods = [r for r in rows if r["kind"] == "method"]

    console.print(f"\n[bold cyan]File: {file_path}[/bold cyan]")
    console.print(f"[dim]Total symbols: {len(rows)}[/dim]\n")

    # Classes table
    if classes:
        table = Table(title="Classes")
        table.add_column("Name", style="cyan")
        table.add_column("Line", style="yellow")

        for row in classes:
            table.add_row(row["symbol_name"], str(row["start_line"]))

        console.print(table)

    # Functions table
    if functions:
        table = Table(title="Functions")
        table.add_column("Name", style="cyan")
        table.add_column("Line", style="yellow")

        for row in functions:
            table.add_row(row["symbol_name"], str(row["start_line"]))

        console.print(table)

    # Methods table
    if methods:
        table = Table(title="Methods")
        table.add_column("Name", style="cyan")
        table.add_column("Parent", style="magenta")
        table.add_column("Line", style="yellow")

        for row in methods:
            table.add_row(row["symbol_name"], row["parent_symbol"] or "", str(row["start_line"]))

        console.print(table)


def main() -> None:
    """Entry point."""
    app()


if __name__ == "__main__":
    main()
