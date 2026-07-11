# Architecture Decision Records

Short records of *why* DeviceKit is built the way it is. Each captures a decision already visible in
the plans and commits, so the reasoning survives beyond a commit message. They describe shipped
choices, not proposals.

| ADR | Decision |
| --- | --- |
| [0001](0001-in-process-extensions.md) | Extensions run in-process, not sandboxed. |
| [0002](0002-no-third-party-frontend-code.md) | Only builtin extensions ship frontend code. |
| [0003](0003-sqlalchemy-source-of-truth.md) | SQLAlchemy is the single source of truth. |
| [0004](0004-droidlink-name-on-pypi.md) | The Python library kept the `droidlink` name on PyPI. |
| [0005](0005-extension-ai-tools-always-gated.md) | Extension AI tools are always gated. |

Back to the [documentation index](../README.md).
