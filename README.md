# meo-mcp

Meo Mai Moi's protocol-independent agent gateway. The initial vertical slice exposes an
OAuth-protected, read-only `list_pets` MCP tool over stateless Streamable HTTP.

Development documentation lives in [`docs/deployment.md`](docs/deployment.md).

Run the test suite from a fresh clone without a production `.env`:

```bash
uv sync --all-groups
uv run pytest
uv run ruff check src tests
```
