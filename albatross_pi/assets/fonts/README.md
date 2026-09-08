# Bundled HUD font

The cockpit HUD loads `orbitron/Orbitron-Bold.ttf` directly through Pygame.
No OS font installation, fontconfig refresh, network access or root access is
required. Copy the entire repository, not only its Python files. Git checkouts,
GitHub source ZIPs and the existing USB update bundle include this directory.

Orbitron Bold preserves the font selected on the development bench. Previously
the system-font preference list could choose VT323, Press Start 2P, Orbitron or
another fallback depending on the machine. That machine-dependent selection has
been replaced by one consistent bundled face. Normal and emphasized HUD text
both use this bold face, as on the previous Orbitron-only bench installation.
The separate bench application's Consolas/system monospace text is unchanged.

## License and provenance

Author: Matt McInerney. Copyright 2009. Reserved Font Name: Orbitron.
License: SIL Open Font License 1.1, reproduced unchanged in
`orbitron/OFL.markdown`. The font remains under that license independently of the
application. It may be bundled with software; do not sell the font by itself or
omit its copyright/license. No font outlines, metadata or formats were modified.

Upstream: https://github.com/theleagueof/orbitron
Pinned revision: `13e6a5222aa6818d81c9acd27edd701a2d744152`.
Original filename: `Orbitron Bold.ttf` (local filename uses a hyphen).
Downloaded 2026-09-08 from:

- https://raw.githubusercontent.com/theleagueof/orbitron/13e6a5222aa6818d81c9acd27edd701a2d744152/Orbitron%20Bold.ttf
- https://raw.githubusercontent.com/theleagueof/orbitron/13e6a5222aa6818d81c9acd27edd701a2d744152/Open%20Font%20License.markdown

If the asset is missing or unreadable, the HUD logs one warning and uses Pygame's
built-in font, rather than crashing or requiring a particular system font.
Restore the assets to recover the intended styling. The paths are resolved from
the installed Python package, independent of the service's working directory.
