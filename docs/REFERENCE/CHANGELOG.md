# Changelog

## [1.7.4](https://github.com/jsmithpkp21/tooling/compare/v1.7.3...v1.7.4) (2026-03-11)


### Documentation

* Updated PYPROJECT_ARCHITECTURE.md so it works in any project it is synced into. ([9ddb7fc](https://github.com/jsmithpkp21/tooling/commit/9ddb7fc28312ce3c401868d33da3aeb5ca314fe0))
* Updated PYPROJECT_ARCHITECTURE.md so it works in any project it… ([74f0e11](https://github.com/jsmithpkp21/tooling/commit/74f0e11140f7d63b230ed9a387eeba5d63ee52a8))

## [1.7.3](https://github.com/jsmithpkp21/tooling/compare/v1.7.2...v1.7.3) (2026-03-11)


### Documentation

* update pyproject architecture see also with repo-agnostic wording ([3351066](https://github.com/jsmithpkp21/tooling/commit/3351066f6f22aeefb21e34572514c0a90992ae07))

## [1.7.2](https://github.com/jsmithpkp21/tooling/compare/v1.7.1...v1.7.2) (2026-03-10)


### Bug Fixes

* improve find_tooling_dir with path validation and expansion ([9cf93fb](https://github.com/jsmithpkp21/tooling/commit/9cf93fb743bbb49d0fe90f030ae6c2218a0d1da5))
* mirror base_repo sync-source updates into tooling ([03821b8](https://github.com/jsmithpkp21/tooling/commit/03821b8603b74bc6e9efa682cba8980e576b8f83))
* print warning if dooling_dir is not a directory ([93bf084](https://github.com/jsmithpkp21/tooling/commit/93bf084a20b819d867a8292e4aabe977869e7133))

## [1.7.1](https://github.com/jsmithpkp21/tooling/compare/v1.7.0...v1.7.1) (2026-03-10)


### Bug Fixes

* **tooling:** enforce single source of truth for Python version ([3ae4a26](https://github.com/jsmithpkp21/tooling/commit/3ae4a263985c78d7d532d4410dd9f3c285ea8bc9))
* **tooling:** enforce single source of truth for Python version ([d666130](https://github.com/jsmithpkp21/tooling/commit/d66613076262941c9944ca09c3ddcd8904bf0de7))

## [1.7.0](https://github.com/jsmithpkp21/tooling/compare/v1.6.1...v1.7.0) (2026-03-09)


### Features

* sync Docker docs and merge_pyproject updates from base_repo ([67752c1](https://github.com/jsmithpkp21/tooling/commit/67752c10ec6e0b083d8799453d30683c8649984e))


### Bug Fixes

* **create_env:** enforce strict gawk runtime contract ([9320841](https://github.com/jsmithpkp21/tooling/commit/932084195b9f6c5843da8e75c77d4b87172b4778))
* **merge_pyproject:** add path validation and expansion to tooling dir args ([25e324c](https://github.com/jsmithpkp21/tooling/commit/25e324c8eb5f4a5749cb00136e198169e9feef24))


### Documentation

* **docker:** list concrete runtime contract tests ([0416884](https://github.com/jsmithpkp21/tooling/commit/04168845d7088796fff71165aca940ea009518e5))
* remove stale git status snapshot from file distribution guide ([659b8f6](https://github.com/jsmithpkp21/tooling/commit/659b8f67339631fc04b3df840678de5f6146f9e9))

## [1.6.1](https://github.com/jsmithpkp21/tooling/compare/v1.6.0...v1.6.1) (2026-03-08)


### Bug Fixes

* exclude cache directories from sync ([7c7413f](https://github.com/jsmithpkp21/tooling/commit/7c7413f24855fde69a68556d959b69346520c33b))
* exclude cache directories from sync ([9899cf8](https://github.com/jsmithpkp21/tooling/commit/9899cf8e3cc6304f5bff838f94f6b2db317ed64c))

## [1.6.0](https://github.com/jsmithpkp21/tooling/compare/v1.5.3...v1.6.0) (2026-03-07)


### Features

* add make check command and fix load_build_env path resolution ([b109403](https://github.com/jsmithpkp21/tooling/commit/b109403e7e2aed5b46d89dc030c3b9e0614de0c7))


### Bug Fixes

* add path validation to prevent directory traversal ([d17113c](https://github.com/jsmithpkp21/tooling/commit/d17113c4e926bced6e1d248c248fd018ebb459b8))
* add symlink traversal checks for sync destinations ([ba8eb8e](https://github.com/jsmithpkp21/tooling/commit/ba8eb8e1d924f6bb824bdd6bfa3dde2017fcc7c0))
* align env loading and sync behavior with repo conventions ([dc4dad9](https://github.com/jsmithpkp21/tooling/commit/dc4dad9a349a87215b5011fb650d378b837a7dd9))
* finalize sync_tooling symlink traversal hardening ([a335cf8](https://github.com/jsmithpkp21/tooling/commit/a335cf85042e54e852ee906a08f42c60e0d83d90))
* gate chmod to successfully copied files only ([eb70185](https://github.com/jsmithpkp21/tooling/commit/eb701850e35f8d74414e7d97b58e3e184b5a48ac))
* implement shell-based path normalization fallback for macOS/BSD ([9ad9233](https://github.com/jsmithpkp21/tooling/commit/9ad9233270a67b03c2760895dc0d31d649f62823))
* improve sync_tooling security test coverage and array scoping ([ff2dcfb](https://github.com/jsmithpkp21/tooling/commit/ff2dcfb17aa075e2a8d5b7cfaa3720f46426032b))
* make sync_tooling path validation portable to macOS/BSD ([101bfcb](https://github.com/jsmithpkp21/tooling/commit/101bfcbebddfd478ae47bab3cbf7d7111a7e7506))
* normalize known-first-party for importable module names ([1c0f6cb](https://github.com/jsmithpkp21/tooling/commit/1c0f6cb007af4216a43574744bb20a92728e2539))
* pass repo-relative path to symlink traversal validator ([5c2e928](https://github.com/jsmithpkp21/tooling/commit/5c2e92812168bb34b481ea6411c60b62e12455d6))
* prevent normalize_sync_path from terminating sync under pipefail ([9ef361c](https://github.com/jsmithpkp21/tooling/commit/9ef361c927f6baddb28cf8df912ee38c659e5db4))
* restore archive-compatible tooling source detection and add regressions ([c066490](https://github.com/jsmithpkp21/tooling/commit/c066490a2cfeb5c84acb3abc434e07d711c23268))
* restore sync exclusions for project-template and sync script ([a3e7aae](https://github.com/jsmithpkp21/tooling/commit/a3e7aae3d707368b13ac89a36e360ec8107c7f77))


### Documentation

* add PYPROJECT_ARCHITECTURE.md with corrected implementation details ([e8729be](https://github.com/jsmithpkp21/tooling/commit/e8729beb7dc7cb655e3a6f987d780487ac384ead))
* align FILE_DISTRIBUTION sync policy wording ([8ae3026](https://github.com/jsmithpkp21/tooling/commit/8ae3026250bbe7eb935ad884c4075a6c40b14dbf))
* clarify .pyproject.meta.toml is not synced ([6b5c7d9](https://github.com/jsmithpkp21/tooling/commit/6b5c7d9841de0666899e0ee2a0447f553b8bbc45))
* clarify FILE_DISTRIBUTION synced vs tooling-only sections ([3ed956e](https://github.com/jsmithpkp21/tooling/commit/3ed956ef144f8be8ffa5c066b85ea59eaea91d81))
* clarify sync_tooling.sh manual update path ([4746257](https://github.com/jsmithpkp21/tooling/commit/4746257767bc4228749e6109bf1a8caacd73912e))
* clarify tooling/pyproject.toml is not synced to projects ([06dda54](https://github.com/jsmithpkp21/tooling/commit/06dda54f9d5e828bbef934a6a73dbacdd9d484eb))
* fix FILE_DISTRIBUTION to reflect project-template exclusion ([7f38709](https://github.com/jsmithpkp21/tooling/commit/7f387090838eb51f26b8de3eacff84c3aaae17e3))
* replace broken TOOLING_ARCHITECTURE reference ([8e9e525](https://github.com/jsmithpkp21/tooling/commit/8e9e525966a02f6d72d80b4cdf5df56e1755f1bc))
* replace dead PYPROJECT_MERGE_IMPLEMENTATION link ([c009760](https://github.com/jsmithpkp21/tooling/commit/c009760b6e69871f2419db963e1de4c019d51947))

## [1.5.3](https://github.com/jsmithpkp21/tooling/compare/v1.5.2...v1.5.3) (2026-03-06)


### Bug Fixes

* make HTML validation more specific to avoid false positives ([cc9adf0](https://github.com/jsmithpkp21/tooling/commit/cc9adf02a5dd1dd95d7a0ff360801dcf04309ae5))

## [1.5.2](https://github.com/jsmithpkp21/tooling/compare/v1.5.1...v1.5.2) (2026-03-06)


### Bug Fixes

* allow sync_tooling.sh to auto-sync by removing from EXCLUDE_LIST ([1d882cd](https://github.com/jsmithpkp21/tooling/commit/1d882cd313603781737b1e6f1d4a3846578ca13b))

## [1.5.1](https://github.com/jsmithpkp21/tooling/compare/v1.5.0...v1.5.1) (2026-03-06)


### Bug Fixes

* prevent sync-tooling from overwriting project metadata and handle empty files ([b1fc22f](https://github.com/jsmithpkp21/tooling/commit/b1fc22fab81bb43b1285c3228832e398d37d0ecd))
* simplify sync-tooling integration test to use REPO_ROOT as tooling ([50dc637](https://github.com/jsmithpkp21/tooling/commit/50dc63783e92b5c7bc1fcaa882786bf69b7ec0d6))
* simplify sync-tooling integration test to use REPO_ROOT as tooling ([044ce2b](https://github.com/jsmithpkp21/tooling/commit/044ce2b9a2a1c822068789328e9f39e4077c1577))

## [1.5.0](https://github.com/jsmithpkp21/tooling/compare/v1.4.0...v1.5.0) (2026-03-05)


### Features

* prevent sync-tooling from running within tooling repo itself ([47e394f](https://github.com/jsmithpkp21/tooling/commit/47e394f6077b5a8c6209dbd0265b0097815c3df3))


### Bug Fixes

* improve tooling repo detection by checking git remote URL ([fe623fb](https://github.com/jsmithpkp21/tooling/commit/fe623fbf15e4de7873b130f35eb76aa54a5be27a))

## [1.4.0](https://github.com/jsmithpkp21/tooling/compare/v1.3.0...v1.4.0) (2026-03-05)


### Features

* prevent sync-tooling from running within tooling repo itself ([1e97f83](https://github.com/jsmithpkp21/tooling/commit/1e97f83919beb9bea98f00fd2d03cc7dc9c856c5))

## [1.3.0](https://github.com/jsmithpkp21/tooling/compare/v1.2.2...v1.3.0) (2026-03-05)


### Features

* add DRY pyproject.toml merge system ([75d00cc](https://github.com/jsmithpkp21/tooling/commit/75d00cc4fe39e4588df0e20e2bd06ada3f198096))


### Bug Fixes

* add metadata and update tests for DRY pyproject system ([cf89158](https://github.com/jsmithpkp21/tooling/commit/cf89158b7050db6603d1a4c3f3f912fda908044a))
* add ruff-format to pre-commit hooks to catch formatting issues ([19f7557](https://github.com/jsmithpkp21/tooling/commit/19f755738e1796e4f891f667d7f6981284d5074a))
* add tomli_w dependency and fix TOML generation ([41a16ab](https://github.com/jsmithpkp21/tooling/commit/41a16ab4cac9deea5fb1db285bd50e2079b84b79))
* address GitHub review comments on version extraction and error handling ([52d9814](https://github.com/jsmithpkp21/tooling/commit/52d98145da56a6609545b924a7fb344c51b5e4a6))
* align Ruff versions and add formatter drift guard test ([9c3b48a](https://github.com/jsmithpkp21/tooling/commit/9c3b48a2127855f3fc2df3ce2dbfa6af636e06a3))
* enable manual dispatch and enforce shell runtime contract checks ([f040b95](https://github.com/jsmithpkp21/tooling/commit/f040b953924bf1587d036f97a9cf82a00bb7d35b))
* enforce shell runtime contract and harden parser portability ([263af67](https://github.com/jsmithpkp21/tooling/commit/263af6781567db8d1969d249fb3c1e5a7d7afa7b))
* load_build_env.sh reads Python version from tooling.toml ([751d5fc](https://github.com/jsmithpkp21/tooling/commit/751d5fc607f8c6cfe5767b5ecae2f45e3115b447))
* move on_error function definition before trap statement ([2e3ec31](https://github.com/jsmithpkp21/tooling/commit/2e3ec310557a897a432b582a58bbef861903e341))
* replace buggy sed range with stateful awk parser for [python] section ([38febd6](https://github.com/jsmithpkp21/tooling/commit/38febd64da1a0b88d8b5764be0e9d4a21efe273b))
* replace tomllib with awk parser in verify_env.sh for consistency ([7c62e4d](https://github.com/jsmithpkp21/tooling/commit/7c62e4d264f34b9f72e6131ef1fc7a982962b0ba))
* resolve CI KeyError by making verify-environment workflow DRY-compatible ([4ff88ac](https://github.com/jsmithpkp21/tooling/commit/4ff88aca87eb180d09e0b8fbba928f29415743d1))
* resolve mypy type error in merge_pyproject.py ([2e88387](https://github.com/jsmithpkp21/tooling/commit/2e88387de6f68ea6c6f6a5c174f33bcc308f3083))
* track and report actual Python version source in create_env.sh ([085fc04](https://github.com/jsmithpkp21/tooling/commit/085fc04d6a53843bf5010c99d9f962db1375e984))
* update sync_tooling.sh to dynamically populate release-please config ([cc1b807](https://github.com/jsmithpkp21/tooling/commit/cc1b80763da150b7fa4d97c422474b1328ee41b8))
* update sync_tooling.sh to dynamically populate release-please config ([4b62737](https://github.com/jsmithpkp21/tooling/commit/4b62737aaf2a04bc710e545dba060bbe4f755413))
* use POSIX tools for Python version extraction (no Python 3.11+ dependency) ([1a0bcca](https://github.com/jsmithpkp21/tooling/commit/1a0bccab07566d119a6c771519748b68daf9712d))

## [1.2.2](https://github.com/jsmithpkp21/tooling/compare/v1.2.1...v1.2.2) (2026-03-04)


### Bug Fixes

* sync project-template and preserve shell script executability ([4c1fd58](https://github.com/jsmithpkp21/tooling/commit/4c1fd5894af813df6b1e4eaa15752700eeeab098))
* sync project-template and preserve shell script executability ([6b457fa](https://github.com/jsmithpkp21/tooling/commit/6b457faff66e29fd6c4e3c175cf1ed0b2383b20a))

## [1.2.1](https://github.com/jsmithpkp21/tooling/compare/v1.2.0...v1.2.1) (2026-03-04)


### Bug Fixes

* add execute permission to scripts/create_env.sh ([acd5a62](https://github.com/jsmithpkp21/tooling/commit/acd5a62eff83a3e4572f56e361ef024c8dde10e8))
* address Copilot review comments for sync and verification scripts ([3b71977](https://github.com/jsmithpkp21/tooling/commit/3b71977993fddc6a27f5e7d0e9fe8869f27efba4))
* align VERSION and remove redundant install-hooks target ([bb4f59b](https://github.com/jsmithpkp21/tooling/commit/bb4f59b035c832b5feb4fd8f10cf8cd51dd7e093))
* apply code review fixes - security improvements and workflow corrections ([59fbabe](https://github.com/jsmithpkp21/tooling/commit/59fbabee78494e58ec3a17ca6e606450f8e9c378))
* configure release-please to use correct changelog path ([f514001](https://github.com/jsmithpkp21/tooling/commit/f514001c4942e8a1c74a5dfec66418191b4b374b))
* correct COPY command in Dockerfile example ([b3cd9aa](https://github.com/jsmithpkp21/tooling/commit/b3cd9aa956506d7ad4e7cfb02e6d69fd2be4868b))
* Fix the file formatting for all files. ([8191b9d](https://github.com/jsmithpkp21/tooling/commit/8191b9d5a12c1a881dbbccebed4f664112859ef8))
* Fix the file formatting for validate_activation_command.py ([c96ee22](https://github.com/jsmithpkp21/tooling/commit/c96ee22384195dc976549162ed83ce285c75d5c6))
* make tooling.toml optional in verify_env.sh for repo portability ([352d21d](https://github.com/jsmithpkp21/tooling/commit/352d21d7cbe8b4e83aadfaa676581e7df48e3898))
* remove stray 'ib' characters breaking the file ([817ba79](https://github.com/jsmithpkp21/tooling/commit/817ba795c3407d620530ca4a539d08bdb0073294))
* remove trailing newline from VERSION file ([ea508e9](https://github.com/jsmithpkp21/tooling/commit/ea508e9a7cf94cda84e3cc7ce077cb83674bae3b))
* restore robust activation pattern enforcement ([2bed9ec](https://github.com/jsmithpkp21/tooling/commit/2bed9ec3cdc564591246ff7a78370c0918e2c326))
* set default PYTHON_VERSION and PIP_VERSION before FROM statement ([4a1176b](https://github.com/jsmithpkp21/tooling/commit/4a1176bf7883ad0f00b35a053b739b167f09e177))


### Documentation

* sync fragile activation pattern fixes from base_repo ([1c797e7](https://github.com/jsmithpkp21/tooling/commit/1c797e79ccea0bb24de1e406af34c7e04e446b1f))

## [1.2.0](https://github.com/jsmithpkp21/tooling/compare/v1.1.2...v1.2.0) (2026-03-03)


### Features

* add project-template with automated setup script ([d14ce28](https://github.com/jsmithpkp21/tooling/commit/d14ce28b1f2d49b52b90fefeafe8571924ed58bf))
* create automated project creation tool (project-template) ([8a951a0](https://github.com/jsmithpkp21/tooling/commit/8a951a0f32ef096b4515f8655f974c8f1e76e804))


### Bug Fixes

* align TOOLING_VERSION default and examples to use main branch ([a45b593](https://github.com/jsmithpkp21/tooling/commit/a45b593d492e6137cda073aafc35761ec98af833))
* **ci:** set pwermissions just for the config file. ([fde25e9](https://github.com/jsmithpkp21/tooling/commit/fde25e924f0d2ce441ef31c9aefa9f10518a8e9f))
* download full tooling archive in setup.sh for correct sync and secure curl ([e5a2e73](https://github.com/jsmithpkp21/tooling/commit/e5a2e73d57dbeb79c5cba644b2de8f6151cb4087))
* Fix parsing for SSH remotes. ([1fa2381](https://github.com/jsmithpkp21/tooling/commit/1fa2381bad6358a42460c49d326a12026b2d87f3))
* Fix parsing for SSH remotes. ([a8e58ba](https://github.com/jsmithpkp21/tooling/commit/a8e58ba143794c3d989b36ba88658fe529f9ebfa))
* replace Unicode symbols in test_setup.sh with plain ASCII for CI portability ([940897f](https://github.com/jsmithpkp21/tooling/commit/940897f9fceecb5e4adb4fbb733cad0fc7f28ee9))
* **template:** address review feedback for setup and docs ([67ccd62](https://github.com/jsmithpkp21/tooling/commit/67ccd62179e93f7ec8113e3cae1aaa27b66285c1))
* **template:** align lint formatter and clarify setup metadata ([ac8be49](https://github.com/jsmithpkp21/tooling/commit/ac8be49ef60173036af1e36228cda716a9c5870f))
* update remaining base_env venv path references to REPO_NAME-env convention ([ba4f8bb](https://github.com/jsmithpkp21/tooling/commit/ba4f8bbf36b0fa24bf08c5a5f9a3e7f539eec3b9))
* Update scripts/create_env.sh ([1b3da25](https://github.com/jsmithpkp21/tooling/commit/1b3da25102d7dec220a054a8e4df4e8e9a77f355))
* use git config for consistent REPO_NAME detection ([3ecace6](https://github.com/jsmithpkp21/tooling/commit/3ecace642226d47051cb3fab0033902bb2e26ed6))
* use git probe instead of .git dir check in create_env.sh and verify_env.sh ([d11fbac](https://github.com/jsmithpkp21/tooling/commit/d11fbac12be896d700e0e6058bac5923a96cf342))
* use stable venv name without version suffix ([e49d0f6](https://github.com/jsmithpkp21/tooling/commit/e49d0f6144803594b0397f7d39402061fd492763))
* use stable venv name without version suffix ([021da28](https://github.com/jsmithpkp21/tooling/commit/021da2875fa3dcba3b95e11c75d7855968b724b5))
* wire test_setup.sh into make test via test-shell target ([ae84218](https://github.com/jsmithpkp21/tooling/commit/ae84218ec4691b46106e56d87c8c7fa2d07727d5))
* worktree-safe git checks in setup.sh; add VERSION/tooling.toml/requirements.txt to template ([682d04a](https://github.com/jsmithpkp21/tooling/commit/682d04ac378573992830307ace06f508d7b79b9c))

## [1.1.2](https://github.com/jsmithpkp21/tooling/compare/v1.1.1...v1.1.2) (2026-03-02)


### Bug Fixes

* improve Dockerfile error handling for empty PIP_VERSION ([ec13fe6](https://github.com/jsmithpkp21/tooling/commit/ec13fe67e74038d137514a0af6c6847ace61ad77))

## [1.1.1](https://github.com/jsmithpkp21/tooling/compare/v1.1.0...v1.1.1) (2026-03-02)


### Bug Fixes

* add pip version to tooling.toml and improve Dockerfile error handling ([0b2fdca](https://github.com/jsmithpkp21/tooling/commit/0b2fdcad426411b2385f1646ef284db0bf631d9e))

## [1.1.0](https://github.com/jsmithpkp21/tooling/compare/v1.0.3...v1.1.0) (2026-03-02)


### Features

* add auto-merge-release workflow for automatic release PR merging ([7a49f76](https://github.com/jsmithpkp21/tooling/commit/7a49f764871cc6095ef06b05913bbfe9d4944dbc))


### Documentation

* complete audit and clarify sync_tooling.sh exclusion ([4860e51](https://github.com/jsmithpkp21/tooling/commit/4860e510f99d8903ce1d5869c02af87ca53f1646))

## [1.0.3](https://github.com/jsmithpkp21/tooling/compare/v1.0.2...v1.0.3) (2026-03-02)


### Bug Fixes

* correct test to use proper filenames and improve file type validation ([2bedab8](https://github.com/jsmithpkp21/tooling/commit/2bedab894a152140af3e6d0a32e812a4353f7535))
* make test_sync_tooling.sh version-dynamic like test_sync_tooling_full.sh ([2af594e](https://github.com/jsmithpkp21/tooling/commit/2af594eb321221acb8a53bbecc256de68462ad1c))
* update documentation for GitHub Actions bypass ([bfbd201](https://github.com/jsmithpkp21/tooling/commit/bfbd201decf48c3e5f6257e8d4c8dc6461b689a6))


### Documentation

* add DYNAMIC_WORKFLOWS.md explaining all workflow changes ([7118c30](https://github.com/jsmithpkp21/tooling/commit/7118c308eca18e78c4eca7613e88a64112aacdd5))
* update FIX_GITHUB_ACTIONS_PR_PERMISSION.md with correct solution ([ac0d43b](https://github.com/jsmithpkp21/tooling/commit/ac0d43b77ea1eb4cce27919b819e495739f7217d))

## [1.0.2](https://github.com/jsmithpkp21/tooling/compare/v1.0.1...v1.0.2) (2026-03-02)


### Bug Fixes

* correct test to use proper filenames and improve file type validation ([2bedab8](https://github.com/jsmithpkp21/tooling/commit/2bedab894a152140af3e6d0a32e812a4353f7535))
* make test_sync_tooling.sh version-dynamic like test_sync_tooling_full.sh ([2af594e](https://github.com/jsmithpkp21/tooling/commit/2af594eb321221acb8a53bbecc256de68462ad1c))
* update documentation for GitHub Actions bypass ([bfbd201](https://github.com/jsmithpkp21/tooling/commit/bfbd201decf48c3e5f6257e8d4c8dc6461b689a6))


### Documentation

* add DYNAMIC_WORKFLOWS.md explaining all workflow changes ([7118c30](https://github.com/jsmithpkp21/tooling/commit/7118c308eca18e78c4eca7613e88a64112aacdd5))
* update FIX_GITHUB_ACTIONS_PR_PERMISSION.md with correct solution ([ac0d43b](https://github.com/jsmithpkp21/tooling/commit/ac0d43b77ea1eb4cce27919b819e495739f7217d))
