# Changelog

## [0.3.0](https://github.com/heyalexej/bidkit-cli/compare/v0.2.0...v0.3.0) (2026-07-26)


### ⚠ BREAKING CHANGES

* **session:** `bidkit session gc --keep-days N` is replaced by `bidkit session prune`, which never deletes session files without --records and an explicit range.

### Features

* **session:** record an auditable session log of every invocation ([24889e0](https://github.com/heyalexej/bidkit-cli/commit/24889e0fed49f91944aac10b1bdf7df146fc25f0))
* **session:** replace gc with an explicit prune; nothing expires on its own ([1ec309b](https://github.com/heyalexej/bidkit-cli/commit/1ec309b26f867078dc92b6cb66ffd38598afa07d))


### Bug Fixes

* restore the documented git install path ([d486415](https://github.com/heyalexej/bidkit-cli/commit/d48641543bb41f32656ed33697914fcea19e3a72))
* **session:** keep revert plans about decisions, not noise ([c6e7239](https://github.com/heyalexej/bidkit-cli/commit/c6e72397c3d974d04803e3f19fe86354ee9634c4))

## [0.2.0](https://github.com/heyalexej/bidkit-cli/compare/v0.1.0...v0.2.0) (2026-07-26)


### ⚠ BREAKING CHANGES

* transport errors surfaced by the CLI are httpx2 exception types, TLS verification uses the operating system trust store (truststore), and wire-debug logger names are httpx2/httpcore2.
* **config:** anything that hardcoded the old default path should pass --config or move the file; resolution order is explicit --config, then ~/.config/bidkit/config.json, then the legacy path.

### Features

* bidkit CLI — every generated eBay operation, callable from the shell ([13351ce](https://github.com/heyalexej/bidkit-cli/commit/13351ce84faddbf59d081e4893f62065182df50a))
* move to bidkit 0.2.0 and httpx2 ([d4b9528](https://github.com/heyalexej/bidkit-cli/commit/d4b95281bbadef6aaa76d7aa6323cb3ca20d6a4d))


### Bug Fixes

* repair pre-split repository paths in user-facing messages ([586570c](https://github.com/heyalexej/bidkit-cli/commit/586570c2c7b617d9d6d0370cf118fe667841d7dd))


### Code Refactoring

* **config:** default config path is ~/.config/bidkit/config.json ([dd4317e](https://github.com/heyalexej/bidkit-cli/commit/dd4317e11932ba387146f0c9db6acd9fa1d33f90))
