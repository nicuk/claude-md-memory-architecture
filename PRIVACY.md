# Privacy

Cairn Memory collects nothing.

- The skill is instructions that Claude reads inside your own session.
- The audit script (`skills/memory-architecture/scripts/audit_memory.py`) reads only the paths you pass it, and runs `git ls-files` in the repository you name.
- It writes nothing to your project. `--self-test` creates a temporary folder and deletes it afterwards.
- It makes no network requests. It has no telemetry, no analytics, no accounts and no API keys.

The author receives no data about you, your repositories or your use of the plugin.

Questions: open an issue at https://github.com/nicuk/claude-md-memory-architecture/issues
