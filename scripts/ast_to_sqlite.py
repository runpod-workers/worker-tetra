#!/usr/bin/env python3
"""AST-based code indexer that extracts symbols and stores them in SQLite."""

import ast
import json
import sqlite3
import sys
import time
from pathlib import Path
from typing import Any, Optional

# Configuration: which dependencies to index
DEPENDENCIES_TO_INDEX = ["runpod_flash"]


class ASTIndexer(ast.NodeVisitor):
    """Walks AST and extracts class, function, and method definitions."""

    def __init__(self, file_path: str, source: str) -> None:
        self.file_path = file_path
        self.source = source
        self.lines = source.split("\n")
        self.symbols: list[dict[str, Any]] = []
        self.current_class: Optional[str] = None

    def visit_ClassDef(self, node: ast.ClassDef) -> None:
        """Extract class definition."""
        signature = self._build_class_signature(node)
        decorators = [ast.unparse(d) for d in node.decorator_list]

        self.symbols.append(
            {
                "file_path": self.file_path,
                "symbol_name": node.name,
                "kind": "class",
                "signature": signature,
                "docstring": ast.get_docstring(node),
                "start_line": node.lineno,
                "end_line": node.end_lineno or node.lineno,
                "parent_symbol": None,
                "decorators": decorators,
                "type_hints": {},
            }
        )

        prev_class = self.current_class
        self.current_class = node.name
        self.generic_visit(node)
        self.current_class = prev_class

    def visit_FunctionDef(self, node: ast.FunctionDef) -> None:
        """Extract function or method definition."""
        signature = self._build_function_signature(node)
        decorators = [ast.unparse(d) for d in node.decorator_list]
        type_hints = self._extract_type_hints(node)

        self.symbols.append(
            {
                "file_path": self.file_path,
                "symbol_name": node.name,
                "kind": "method" if self.current_class else "function",
                "signature": signature,
                "docstring": ast.get_docstring(node),
                "start_line": node.lineno,
                "end_line": node.end_lineno or node.lineno,
                "parent_symbol": self.current_class,
                "decorators": decorators,
                "type_hints": type_hints,
            }
        )

        self.generic_visit(node)

    def visit_AsyncFunctionDef(self, node: ast.AsyncFunctionDef) -> None:
        """Extract async function or method definition."""
        signature = f"async {self._build_function_signature(node)}"
        decorators = [ast.unparse(d) for d in node.decorator_list]
        type_hints = self._extract_type_hints(node)

        self.symbols.append(
            {
                "file_path": self.file_path,
                "symbol_name": node.name,
                "kind": "method" if self.current_class else "function",
                "signature": signature,
                "docstring": ast.get_docstring(node),
                "start_line": node.lineno,
                "end_line": node.end_lineno or node.lineno,
                "parent_symbol": self.current_class,
                "decorators": decorators,
                "type_hints": type_hints,
            }
        )

        self.generic_visit(node)

    def _build_class_signature(self, node: ast.ClassDef) -> str:
        """Build class signature with bases."""
        bases = ", ".join(ast.unparse(base) for base in node.bases)
        if bases:
            return f"class {node.name}({bases})"
        return f"class {node.name}"

    def _build_function_signature(self, node: ast.FunctionDef | ast.AsyncFunctionDef) -> str:
        """Build function signature with arguments and return type."""
        args = self._format_arguments(node.args)
        returns = f" -> {ast.unparse(node.returns)}" if node.returns else ""
        return f"def {node.name}({args}){returns}"

    def _format_arguments(self, args: ast.arguments) -> str:
        """Format function arguments with type hints."""
        formatted: list[str] = []

        # Positional arguments
        for i, arg in enumerate(args.args):
            annotation = f": {ast.unparse(arg.annotation)}" if arg.annotation else ""
            formatted.append(f"{arg.arg}{annotation}")

        # Keyword-only arguments
        for arg in args.kwonlyargs:
            annotation = f": {ast.unparse(arg.annotation)}" if arg.annotation else ""
            formatted.append(f"{arg.arg}{annotation}")

        # *args
        if args.vararg:
            annotation = (
                f": {ast.unparse(args.vararg.annotation)}" if args.vararg.annotation else ""
            )
            formatted.append(f"*{args.vararg.arg}{annotation}")

        # **kwargs
        if args.kwarg:
            annotation = f": {ast.unparse(args.kwarg.annotation)}" if args.kwarg.annotation else ""
            formatted.append(f"**{args.kwarg.arg}{annotation}")

        return ", ".join(formatted)

    def _extract_type_hints(self, node: ast.FunctionDef | ast.AsyncFunctionDef) -> dict[str, str]:
        """Extract type hints from function arguments."""
        hints: dict[str, str] = {}

        for arg in node.args.args + node.args.kwonlyargs:
            if arg.annotation:
                hints[arg.arg] = ast.unparse(arg.annotation)

        if node.args.vararg and node.args.vararg.annotation:
            hints[f"*{node.args.vararg.arg}"] = ast.unparse(node.args.vararg.annotation)

        if node.args.kwarg and node.args.kwarg.annotation:
            hints[f"**{node.args.kwarg.arg}"] = ast.unparse(node.args.kwarg.annotation)

        if node.returns:
            hints["return"] = ast.unparse(node.returns)

        return hints


def create_database(db_path: Path) -> None:
    """Create SQLite database with schema."""
    db_path.parent.mkdir(parents=True, exist_ok=True)

    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()

    cursor.execute("""
        CREATE TABLE IF NOT EXISTS symbols (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            file_path TEXT NOT NULL,
            symbol_name TEXT NOT NULL,
            kind TEXT NOT NULL,
            signature TEXT,
            docstring TEXT,
            start_line INTEGER NOT NULL,
            end_line INTEGER,
            parent_symbol TEXT,
            decorator_json TEXT,
            type_hints TEXT,
            created_at INTEGER
        )
    """)

    cursor.execute("CREATE INDEX IF NOT EXISTS idx_symbol_name ON symbols(symbol_name)")
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_file_path ON symbols(file_path)")
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_kind ON symbols(kind)")
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_parent ON symbols(parent_symbol)")

    conn.commit()
    conn.close()


def index_directory(
    directory: Path, base_path: Path, cursor: sqlite3.Cursor, skip_private: bool = True
) -> int:
    """Index all Python files in a directory recursively.

    Args:
        directory: The directory to scan
        base_path: The base path for relative path calculation
        cursor: Database cursor for inserting symbols
        skip_private: If True, skip files whose names start with underscore (_).
                     Project files typically skip private files, while dependency
                     indexing includes them to capture internal APIs.

    Returns:
        Number of symbols indexed
    """
    total_symbols = 0

    for py_file in sorted(directory.rglob("*.py")):
        if skip_private and py_file.name.startswith("_"):
            continue

        try:
            source = py_file.read_text()
            tree = ast.parse(source)

            rel_path = str(py_file.relative_to(base_path))
            indexer = ASTIndexer(rel_path, source)
            indexer.visit(tree)

            for symbol in indexer.symbols:
                cursor.execute(
                    """
                    INSERT INTO symbols (
                        file_path, symbol_name, kind, signature, docstring,
                        start_line, end_line, parent_symbol, decorator_json,
                        type_hints, created_at
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                    (
                        symbol["file_path"],
                        symbol["symbol_name"],
                        symbol["kind"],
                        symbol["signature"],
                        symbol["docstring"],
                        symbol["start_line"],
                        symbol["end_line"],
                        symbol["parent_symbol"],
                        json.dumps(symbol["decorators"]),
                        json.dumps(symbol["type_hints"]),
                        int(time.time()),
                    ),
                )

            total_symbols += len(indexer.symbols)

        except SyntaxError as e:
            print(f"⚠️  Syntax error in {py_file}: {e}")

    return total_symbols


def index_files(src_dir: Path, db_path: Path) -> int:
    """Index all Python files in src directory."""
    create_database(db_path)

    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()

    total_symbols = index_directory(src_dir, src_dir.parent, cursor, skip_private=True)

    conn.commit()
    conn.close()

    return total_symbols


def get_dependency_path(dep_name: str, site_packages: Path) -> Optional[Path]:
    """Get the actual path to a dependency, handling editable installs.

    Args:
        dep_name: The dependency package name (e.g., "runpod_flash")
        site_packages: The site-packages directory path

    Returns:
        Path to the dependency, or None if not found
    """
    # First check for editable install via direct_url.json
    dist_info_pattern = f"{dep_name.replace('_', '-')}-*.dist-info"
    dist_info_dirs = list(site_packages.glob(dist_info_pattern))

    if dist_info_dirs:
        direct_url_file = dist_info_dirs[0] / "direct_url.json"
        if direct_url_file.exists():
            with open(direct_url_file) as f:
                data = json.load(f)
                if data.get("dir_info", {}).get("editable"):
                    # Extract path from file:// URL
                    url = data.get("url", "")
                    if url.startswith("file://"):
                        editable_path = Path(url.replace("file://", ""))
                        # Find the actual package directory
                        package_dir = editable_path / dep_name
                        if package_dir.exists():
                            return package_dir
                        # Might be in src/ subdirectory
                        src_package_dir = editable_path / "src" / dep_name
                        if src_package_dir.exists():
                            return src_package_dir

    # Not editable - check regular site-packages location
    dep_path = site_packages / dep_name
    if dep_path.exists() and dep_path.is_dir():
        return dep_path

    return None


def index_dependencies(venv_dir: Path, db_path: Path) -> int:
    """Index configured dependency packages from site-packages or editable installs.

    Args:
        venv_dir: Path to the virtual environment
        db_path: Path to the database file

    Returns:
        Total number of symbols indexed from dependencies
    """
    site_packages = (
        venv_dir
        / "lib"
        / f"python{sys.version_info.major}.{sys.version_info.minor}"
        / "site-packages"
    )

    if not site_packages.exists():
        return 0

    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()
    total_symbols = 0

    for dep_name in DEPENDENCIES_TO_INDEX:
        dep_path = get_dependency_path(dep_name, site_packages)
        if dep_path:
            # Determine base path for relative path calculation
            # For editable installs, use the editable root; for regular, use site-packages
            if str(dep_path).startswith(str(site_packages)):
                base_path = site_packages
            else:
                # Editable install - use parent of package directory
                base_path = dep_path.parent

            print(f"  Indexing dependency: {dep_name} (from {dep_path})")
            dep_symbols = index_directory(dep_path, base_path, cursor, skip_private=False)
            total_symbols += dep_symbols
        else:
            print(f"  ⚠️  Dependency not found: {dep_name}")

    conn.commit()
    conn.close()
    return total_symbols


def main() -> None:
    """Main entry point."""
    project_root = Path(__file__).parent.parent
    src_dir = project_root / "src"
    venv_dir = project_root / ".venv"
    db_path = project_root / ".code-intel" / "flash.db"

    # Clear old database
    if db_path.exists():
        db_path.unlink()

    print("🔍 Starting code intelligence indexing...")

    start_time = time.time()

    # Index project source
    total = index_files(src_dir, db_path)

    # Index dependencies
    dep_total = index_dependencies(venv_dir, db_path)

    elapsed = time.time() - start_time

    db_size_kb = db_path.stat().st_size / 1024

    print(f"✅ Indexed {total} project symbols + {dep_total} dependency symbols in {elapsed:.2f}s")
    print(f"📊 Database: {db_path} ({db_size_kb:.1f} KB)")


if __name__ == "__main__":
    main()
