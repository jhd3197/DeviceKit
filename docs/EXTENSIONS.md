# Extension docs moved

The extension documentation is now a small tree under [`docs/extensions/`](extensions/), split so
the reference material is *lookup-able* instead of buried in one long read:

| Doc | What it is |
| --- | --- |
| **[Extension Guide](extensions/guide.md)** | The narrative author guide — anatomy, contribution points, lifecycle, install sources, the registry, security posture. (This is the old `EXTENSIONS.md`, trimmed.) |
| **[First Extension Tutorial](extensions/tutorial.md)** | Scaffold, install, and see a step type render — in ~10 minutes. |
| **[Manifest Reference](extensions/manifest-reference.md)** | Every `extension.json` field, its rule, and its default. |
| **[SDK Reference](extensions/sdk-reference.md)** | Every `devicekit_sdk` export and signature. |

Start at the [documentation index](README.md) for the whole suite.

> This stub stays because external links, and the `validate_manifest` error message, point at
> `docs/EXTENSIONS.md`.
