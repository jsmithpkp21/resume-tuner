# Changelog

## [1.14.0](https://github.com/jsmithpkp21/tooling/compare/v1.13.2...v1.14.0) (2026-04-03)


### Features

* add .github/copilot-instructions.md for Copilot coding agent ([1d95c0f](https://github.com/jsmithpkp21/tooling/commit/1d95c0f4d1c605a0aa30a48f3e9a6314041b7733))
* add auto-merge-release workflow for automatic release PR merging ([7a49f76](https://github.com/jsmithpkp21/tooling/commit/7a49f764871cc6095ef06b05913bbfe9d4944dbc))
* add DRY pyproject.toml merge system ([75d00cc](https://github.com/jsmithpkp21/tooling/commit/75d00cc4fe39e4588df0e20e2bd06ada3f198096))
* add make check command and fix load_build_env path resolution ([b109403](https://github.com/jsmithpkp21/tooling/commit/b109403e7e2aed5b46d89dc030c3b9e0614de0c7))
* add project-template with automated setup script ([d14ce28](https://github.com/jsmithpkp21/tooling/commit/d14ce28b1f2d49b52b90fefeafe8571924ed58bf))
* **ci:** add consumer contract CI gate (resume-builder first) for sync + environment lifecycle ([b5b6c7b](https://github.com/jsmithpkp21/tooling/commit/b5b6c7bcb8314373a4abc47d48e4324fb7c787ec))
* **ci:** address contract gate review feedback ([8b7a294](https://github.com/jsmithpkp21/tooling/commit/8b7a294358ac9f6c4386673906a3e99138528bb5))
* create automated project creation tool (project-template) ([8a951a0](https://github.com/jsmithpkp21/tooling/commit/8a951a0f32ef096b4515f8655f974c8f1e76e804))
* **docs:** create docs/SETUP/NEW_PROJECT.md and add to sync manifest ([0543f33](https://github.com/jsmithpkp21/tooling/commit/0543f33109355981c49a9c73dbd8f8673e6d1f82))
* **issue-11:** implement release/stable branch automation ([07ee0d2](https://github.com/jsmithpkp21/tooling/commit/07ee0d20bdc69bd4f8a71e86e9cb2761e122428f)), closes [#11](https://github.com/jsmithpkp21/tooling/issues/11)
* prevent sync-tooling from running within tooling repo itself ([47e394f](https://github.com/jsmithpkp21/tooling/commit/47e394f6077b5a8c6209dbd0265b0097815c3df3))
* prevent sync-tooling from running within tooling repo itself ([1e97f83](https://github.com/jsmithpkp21/tooling/commit/1e97f83919beb9bea98f00fd2d03cc7dc9c856c5))
* prevent sync-tooling from running within tooling repo itself ([33f7d48](https://github.com/jsmithpkp21/tooling/commit/33f7d48018d6ea47fd87f27cddd2b0b494eacc84)), closes [#12](https://github.com/jsmithpkp21/tooling/issues/12)
* sync Docker docs and merge_pyproject updates from base_repo ([67752c1](https://github.com/jsmithpkp21/tooling/commit/67752c10ec6e0b083d8799453d30683c8649984e))
* **sync:** add guarded update-sync-script workflow and align docs/tests ([#49](https://github.com/jsmithpkp21/tooling/issues/49)) ([c20735a](https://github.com/jsmithpkp21/tooling/commit/c20735a647d82c110e797824e1a033e758ce4727))
* **sync:** adopt shared dev requirements contract ([#204](https://github.com/jsmithpkp21/tooling/issues/204)) ([b4e498b](https://github.com/jsmithpkp21/tooling/commit/b4e498b48035ff3a90c8d5903ea5c38401b6267a))
* **sync:** implement allow-list sync manifest contract ([#73](https://github.com/jsmithpkp21/tooling/issues/73)) ([a030ccf](https://github.com/jsmithpkp21/tooling/commit/a030ccff269bc44ee0a7bad3285462fdb647da0b))
* **sync:** persist lock metadata and add drift validator ([#76](https://github.com/jsmithpkp21/tooling/issues/76)) ([#77](https://github.com/jsmithpkp21/tooling/issues/77)) ([b30cb53](https://github.com/jsmithpkp21/tooling/commit/b30cb53730afc1381e03acc98307060b8f6e9755))


### Bug Fixes

* add execute permission to scripts/create_env.sh ([acd5a62](https://github.com/jsmithpkp21/tooling/commit/acd5a62eff83a3e4572f56e361ef024c8dde10e8))
* add explicit chmod for scripts in Docker build ([a1f01cc](https://github.com/jsmithpkp21/tooling/commit/a1f01cc236f719cb46032e4fd50efccd756a80a9))
* add metadata and update tests for DRY pyproject system ([cf89158](https://github.com/jsmithpkp21/tooling/commit/cf89158b7050db6603d1a4c3f3f912fda908044a))
* add path validation to prevent directory traversal ([d17113c](https://github.com/jsmithpkp21/tooling/commit/d17113c4e926bced6e1d248c248fd018ebb459b8))
* add pip version to tooling.toml and improve Dockerfile error handling ([0b2fdca](https://github.com/jsmithpkp21/tooling/commit/0b2fdcad426411b2385f1646ef284db0bf631d9e))
* add ruff-format to pre-commit hooks to catch formatting issues ([19f7557](https://github.com/jsmithpkp21/tooling/commit/19f755738e1796e4f891f667d7f6981284d5074a))
* add symlink traversal checks for sync destinations ([ba8eb8e](https://github.com/jsmithpkp21/tooling/commit/ba8eb8e1d924f6bb824bdd6bfa3dde2017fcc7c0))
* add tomli_w dependency and fix TOML generation ([41a16ab](https://github.com/jsmithpkp21/tooling/commit/41a16ab4cac9deea5fb1db285bd50e2079b84b79))
* address Copilot review comments for sync and verification scripts ([3b71977](https://github.com/jsmithpkp21/tooling/commit/3b71977993fddc6a27f5e7d0e9fe8869f27efba4))
* address GitHub review comments on version extraction and error handling ([52d9814](https://github.com/jsmithpkp21/tooling/commit/52d98145da56a6609545b924a7fb344c51b5e4a6))
* align env loading and sync behavior with repo conventions ([dc4dad9](https://github.com/jsmithpkp21/tooling/commit/dc4dad9a349a87215b5011fb650d378b837a7dd9))
* align Ruff versions and add formatter drift guard test ([9c3b48a](https://github.com/jsmithpkp21/tooling/commit/9c3b48a2127855f3fc2df3ce2dbfa6af636e06a3))
* align TOOLING_VERSION default and examples to use main branch ([a45b593](https://github.com/jsmithpkp21/tooling/commit/a45b593d492e6137cda073aafc35761ec98af833))
* align VERSION and .pyproject.meta.toml with latest release tag ([d3c6c2c](https://github.com/jsmithpkp21/tooling/commit/d3c6c2c7c9e462f0eed2b10850997e679617e304)), closes [#149](https://github.com/jsmithpkp21/tooling/issues/149)
* align VERSION and remove redundant install-hooks target ([bb4f59b](https://github.com/jsmithpkp21/tooling/commit/bb4f59b035c832b5feb4fd8f10cf8cd51dd7e093))
* allow sync_tooling.sh to auto-sync by removing from EXCLUDE_LIST ([1d882cd](https://github.com/jsmithpkp21/tooling/commit/1d882cd313603781737b1e6f1d4a3846578ca13b))
* apply code review fixes - security improvements and workflow corrections ([59fbabe](https://github.com/jsmithpkp21/tooling/commit/59fbabee78494e58ec3a17ca6e606450f8e9c378))
* **ci:** add permissions: contents: read to consumer-contract job ([4c2a13c](https://github.com/jsmithpkp21/tooling/commit/4c2a13cbf8c8eb17a8517fdeb4300c7f164008ac))
* **ci:** add trap-based cleanup for fix-pr-initial-commit temp files ([0872dc8](https://github.com/jsmithpkp21/tooling/commit/0872dc848732062175caebe652865a34c4687a14))
* **ci:** address contract tooling review feedback ([224727e](https://github.com/jsmithpkp21/tooling/commit/224727e19655f3d5534518f5cfd79e295a36215a))
* **ci:** address remaining PR 192 review feedback ([0d00cf2](https://github.com/jsmithpkp21/tooling/commit/0d00cf22761c90a04fbcd0e1f868f337fde9377a))
* **ci:** align action pin tests and validator with lock contract ([0eae647](https://github.com/jsmithpkp21/tooling/commit/0eae647e563ad21955a8b5fe104352d70f7215fd)), closes [#95](https://github.com/jsmithpkp21/tooling/issues/95)
* **ci:** broaden docker fingerprint to all tracked files ([51560d3](https://github.com/jsmithpkp21/tooling/commit/51560d30ddb1588e4d1d331434b0157930dd41c3))
* **ci:** correct Docker Hub optional-login gating to use validation-step output ([dda5bc9](https://github.com/jsmithpkp21/tooling/commit/dda5bc9a62a146eceb7c5625a3d26202b197d9b8)), closes [#179](https://github.com/jsmithpkp21/tooling/issues/179)
* **ci:** define commitlint workflow triggers and job ([#79](https://github.com/jsmithpkp21/tooling/issues/79)) ([9070d0d](https://github.com/jsmithpkp21/tooling/commit/9070d0dfb00d9e4bf3a1653a9e4859b2f1dc4301))
* **ci:** fix macOS/BSD ([84c279d](https://github.com/jsmithpkp21/tooling/commit/84c279df14a412ea2cc70be75e97f603bfbfaece))
* **ci:** grant artifact-read permission to consumer-contract job ([7ffd2d3](https://github.com/jsmithpkp21/tooling/commit/7ffd2d30a33ae96b04ca482f37d36b488eb1b8f6))
* **ci:** harden Docker Hub auth to prevent buildx and commitlint pull lockouts ([92b10c4](https://github.com/jsmithpkp21/tooling/commit/92b10c4ec6b6b7998e399674dc09b0df5ea353d5))
* **ci:** harden initial commit and consumer contract flow ([f0d66eb](https://github.com/jsmithpkp21/tooling/commit/f0d66ebd4718817e7275a6c7fe50bf2e65236ccf))
* **ci:** harden workflow action pin enforcement and test portability ([acf7c4e](https://github.com/jsmithpkp21/tooling/commit/acf7c4e57d01ca0e274a024ea875f04c337ddef8)), closes [#95](https://github.com/jsmithpkp21/tooling/issues/95)
* **ci:** harden workflow action pin enforcement hooks and lock parsing ([f06ca11](https://github.com/jsmithpkp21/tooling/commit/f06ca11babcfde54b7fb0847171108fc1876e798)), closes [#95](https://github.com/jsmithpkp21/tooling/issues/95)
* **ci:** harden workflow action pin validator error reporting ([8833f42](https://github.com/jsmithpkp21/tooling/commit/8833f4247b4f7dc3c8d126127fd37c6faf881fd0)), closes [#95](https://github.com/jsmithpkp21/tooling/issues/95)
* **ci:** harden workflow action pin validator lock and I/O error handling ([2c7aefc](https://github.com/jsmithpkp21/tooling/commit/2c7aefc42d5c51765f1748b43370217afcf0fe86)), closes [#95](https://github.com/jsmithpkp21/tooling/issues/95)
* **ci:** include version and pyproject metadata in docker cache fingerprint ([3a317de](https://github.com/jsmithpkp21/tooling/commit/3a317de85440773e21e8a9cfc6c0a02a99dbbdc6)), closes [#210](https://github.com/jsmithpkp21/tooling/issues/210)
* **ci:** make contract test env deterministic and quote activation paths ([fbd9ff8](https://github.com/jsmithpkp21/tooling/commit/fbd9ff8fdb0a79d1ce3a33d11630fc9f93d04bc0))
* **ci:** mark mounted repo as safe for lint ([3c97e2a](https://github.com/jsmithpkp21/tooling/commit/3c97e2ac03dd4aacb643e75c18e8ad6e55628eec))
* **ci:** mount workspace for verify-environment lint ([8ed6514](https://github.com/jsmithpkp21/tooling/commit/8ed65149d5b03070fc29b59ccac85dcd04769bb5))
* **ci:** narrow verify-environment docker cache fingerprint inputs ([65bf83b](https://github.com/jsmithpkp21/tooling/commit/65bf83b24cd71cd7cf512a78acf5f9f240cac859)), closes [#210](https://github.com/jsmithpkp21/tooling/issues/210)
* **ci:** realign release version metadata ([8e79768](https://github.com/jsmithpkp21/tooling/commit/8e797684f369c8268652b0dcd6dee4e9c831b0bb))
* **ci:** remove custom BuildKit daemon flags for buildx stability ([00008d2](https://github.com/jsmithpkp21/tooling/commit/00008d23d0d76019d4ba9cdfbdf82d81800bf37b))
* **ci:** run consumer-contract tests via env activation and python -m pytest ([d70552d](https://github.com/jsmithpkp21/tooling/commit/d70552d3b169c2a1f25723a13b03c0e29699ff71))
* **ci:** scope Docker Hub secrets to auth steps only ([10d5a44](https://github.com/jsmithpkp21/tooling/commit/10d5a443115ae39ded58d45c472b32f943490c48))
* **ci:** set pwermissions just for the config file. ([fde25e9](https://github.com/jsmithpkp21/tooling/commit/fde25e924f0d2ce441ef31c9aefa9f10518a8e9f))
* **ci:** tighten PR validation regex to reject PR=0 ([4774c50](https://github.com/jsmithpkp21/tooling/commit/4774c50e57c3c35ccb15639dfef5619507ef8d8c))
* **ci:** use env context for optional Docker Hub login in commitlint workflow ([0eb6ff1](https://github.com/jsmithpkp21/tooling/commit/0eb6ff1ce4f7f0ae618c4dd37c1c5d4f27d07d79))
* **ci:** use env context in release-please optional Docker Hub login ([ea741df](https://github.com/jsmithpkp21/tooling/commit/ea741df0c508c90fd9b56479c39830b39b90fdcf))
* **ci:** use full build-context detection for Docker rebuild gating ([4a8e593](https://github.com/jsmithpkp21/tooling/commit/4a8e593bebfbafd67ec660e7bfe3a9b9a84ecf97))
* **commitlint:** harden npm install path and add parity guard ([7f82ddf](https://github.com/jsmithpkp21/tooling/commit/7f82ddffa44cb0087213712b472be8d730e46a98))
* compute progress counter total dynamically from len(children) ([9274465](https://github.com/jsmithpkp21/tooling/commit/927446561707b7e6e50ed5c11606b7971a0baaa0))
* configure release-please to use correct changelog path ([f514001](https://github.com/jsmithpkp21/tooling/commit/f514001c4942e8a1c74a5dfec66418191b4b374b))
* correct COPY command in Dockerfile example ([b3cd9aa](https://github.com/jsmithpkp21/tooling/commit/b3cd9aa956506d7ad4e7cfb02e6d69fd2be4868b))
* correct test to use proper filenames and improve file type validation ([2bedab8](https://github.com/jsmithpkp21/tooling/commit/2bedab894a152140af3e6d0a32e812a4353f7535))
* **create_env:** enforce strict gawk runtime contract ([9320841](https://github.com/jsmithpkp21/tooling/commit/932084195b9f6c5843da8e75c77d4b87172b4778))
* **devx:** stabilize Docker-based tooling workflow ([bab3794](https://github.com/jsmithpkp21/tooling/commit/bab379423c6007e261d162e0211cfdb38c099163))
* download full tooling archive in setup.sh for correct sync and secure curl ([e5a2e73](https://github.com/jsmithpkp21/tooling/commit/e5a2e73d57dbeb79c5cba644b2de8f6151cb4087))
* enable manual dispatch and enforce shell runtime contract checks ([f040b95](https://github.com/jsmithpkp21/tooling/commit/f040b953924bf1587d036f97a9cf82a00bb7d35b))
* enforce shell runtime contract and harden parser portability ([263af67](https://github.com/jsmithpkp21/tooling/commit/263af6781567db8d1969d249fb3c1e5a7d7afa7b))
* **env:** guard trap cleanup before ENV_PATH is assigned ([64ed46f](https://github.com/jsmithpkp21/tooling/commit/64ed46f11b9b72e2392d1a7f5a2fcbf1b2933acb))
* **env:** preserve actionable remediation hint for missing requirements-dev.txt ([3850454](https://github.com/jsmithpkp21/tooling/commit/3850454dbaeb1d6d3098067bd373dbeefa30261c))
* **env:** require requirements-dev.txt in preflight ([352b720](https://github.com/jsmithpkp21/tooling/commit/352b720d2b4fbc809000842d45a3699ca82fcf06))
* **env:** split ERR/EXIT traps for accurate exit code and line number reporting ([882c446](https://github.com/jsmithpkp21/tooling/commit/882c446d81d9a8183bdd395c62357a42e2ca08ff))
* exclude cache directories from sync ([7c7413f](https://github.com/jsmithpkp21/tooling/commit/7c7413f24855fde69a68556d959b69346520c33b))
* exclude cache directories from sync ([9899cf8](https://github.com/jsmithpkp21/tooling/commit/9899cf8e3cc6304f5bff838f94f6b2db317ed64c))
* finalize sync_tooling symlink traversal hardening ([a335cf8](https://github.com/jsmithpkp21/tooling/commit/a335cf85042e54e852ee906a08f42c60e0d83d90))
* Fix parsing for SSH remotes. ([1fa2381](https://github.com/jsmithpkp21/tooling/commit/1fa2381bad6358a42460c49d326a12026b2d87f3))
* Fix parsing for SSH remotes. ([a8e58ba](https://github.com/jsmithpkp21/tooling/commit/a8e58ba143794c3d989b36ba88658fe529f9ebfa))
* Fix the file formatting for all files. ([8191b9d](https://github.com/jsmithpkp21/tooling/commit/8191b9d5a12c1a881dbbccebed4f664112859ef8))
* Fix the file formatting for validate_activation_command.py ([c96ee22](https://github.com/jsmithpkp21/tooling/commit/c96ee22384195dc976549162ed83ce285c75d5c6))
* gate chmod to successfully copied files only ([eb70185](https://github.com/jsmithpkp21/tooling/commit/eb701850e35f8d74414e7d97b58e3e184b5a48ac))
* **hooks:** align drift hook contract assertions with serialized entry ([4347b19](https://github.com/jsmithpkp21/tooling/commit/4347b19a239baed959feac2e64641dfebdef78ff))
* implement shell-based path normalization fallback for macOS/BSD ([9ad9233](https://github.com/jsmithpkp21/tooling/commit/9ad9233270a67b03c2760895dc0d31d649f62823))
* improve Dockerfile error handling for empty PIP_VERSION ([ec13fe6](https://github.com/jsmithpkp21/tooling/commit/ec13fe67e74038d137514a0af6c6847ace61ad77))
* improve find_tooling_dir with path validation and expansion ([9cf93fb](https://github.com/jsmithpkp21/tooling/commit/9cf93fb743bbb49d0fe90f030ae6c2218a0d1da5))
* improve sync_tooling security test coverage and array scoping ([ff2dcfb](https://github.com/jsmithpkp21/tooling/commit/ff2dcfb17aa075e2a8d5b7cfaa3720f46426032b))
* improve tooling repo detection by checking git remote URL ([fe623fb](https://github.com/jsmithpkp21/tooling/commit/fe623fbf15e4de7873b130f35eb76aa54a5be27a))
* **lint:** bump markdownlint-cli 0.45.0 → 0.47.0 to eliminate glob deprecation warning ([4401b35](https://github.com/jsmithpkp21/tooling/commit/4401b3531b82223c8896f4028a78ffe29e55a317))
* **lint:** correct test comment and rename _DEPRECATED_VERSION to _VULNERABLE_VERSION ([e2ff025](https://github.com/jsmithpkp21/tooling/commit/e2ff02528080493c09819aac1449dcea3c2ddcab))
* **lint:** suppress npx/npm noise in containerized markdown-lint target ([1c11cfd](https://github.com/jsmithpkp21/tooling/commit/1c11cfda268b2a7c0c8469a4bc4114e8ddc84c9e)), closes [#70](https://github.com/jsmithpkp21/tooling/issues/70)
* load_build_env.sh reads Python version from tooling.toml ([751d5fc](https://github.com/jsmithpkp21/tooling/commit/751d5fc607f8c6cfe5767b5ecae2f45e3115b447))
* make HTML validation more specific to avoid false positives ([cc9adf0](https://github.com/jsmithpkp21/tooling/commit/cc9adf02a5dd1dd95d7a0ff360801dcf04309ae5))
* make sync_tooling path validation portable to macOS/BSD ([101bfcb](https://github.com/jsmithpkp21/tooling/commit/101bfcbebddfd478ae47bab3cbf7d7111a7e7506))
* make test_sync_tooling.sh version-dynamic like test_sync_tooling_full.sh ([2af594e](https://github.com/jsmithpkp21/tooling/commit/2af594eb321221acb8a53bbecc256de68462ad1c))
* make tooling.toml optional in verify_env.sh for repo portability ([352d21d](https://github.com/jsmithpkp21/tooling/commit/352d21d7cbe8b4e83aadfaa676581e7df48e3898))
* **makefile:** quote ENV_PATH activation in consumer-contract-test ([35a984d](https://github.com/jsmithpkp21/tooling/commit/35a984d9fe1ac378afa5622a3fa20463c2af6e31))
* **makefile:** use DOCKER_COMPOSE in docker-up cleanup guidance ([771c2a8](https://github.com/jsmithpkp21/tooling/commit/771c2a82de2e316436a1ecdcf0deb63a99a166e6))
* **merge_pyproject:** add path validation and expansion to tooling dir args ([25e324c](https://github.com/jsmithpkp21/tooling/commit/25e324c8eb5f4a5749cb00136e198169e9feef24))
* mirror base_repo sync-source updates into tooling ([03821b8](https://github.com/jsmithpkp21/tooling/commit/03821b8603b74bc6e9efa682cba8980e576b8f83))
* move on_error function definition before trap statement ([2e3ec31](https://github.com/jsmithpkp21/tooling/commit/2e3ec310557a897a432b582a58bbef861903e341))
* normalize known-first-party for importable module names ([1c0f6cb](https://github.com/jsmithpkp21/tooling/commit/1c0f6cb007af4216a43574744bb20a92728e2539))
* pass repo-relative path to symlink traversal validator ([5c2e928](https://github.com/jsmithpkp21/tooling/commit/5c2e92812168bb34b481ea6411c60b62e12455d6))
* prevent normalize_sync_path from terminating sync under pipefail ([9ef361c](https://github.com/jsmithpkp21/tooling/commit/9ef361c927f6baddb28cf8df912ee38c659e5db4))
* prevent sync-tooling from overwriting project metadata and handle empty files ([b1fc22f](https://github.com/jsmithpkp21/tooling/commit/b1fc22fab81bb43b1285c3228832e398d37d0ecd))
* print warning if dooling_dir is not a directory ([93bf084](https://github.com/jsmithpkp21/tooling/commit/93bf084a20b819d867a8292e4aabe977869e7133))
* **project-template:** add tests package markers to template ([5fb1c1e](https://github.com/jsmithpkp21/tooling/commit/5fb1c1eb1e8c530b274540e4b624f8bc88e2e72c))
* **project-template:** clarify setup.sh remote step for existing origins ([2787da0](https://github.com/jsmithpkp21/tooling/commit/2787da0167961943462af188e6ae6bd29be6655f))
* **project-template:** remove dead [flake8] section and add [runtime] block to tooling.toml ([5af2ae2](https://github.com/jsmithpkp21/tooling/commit/5af2ae25613f10190e02f84a9a1879141b79d4c0))
* **project-template:** remove orphan ci workflow from template ([12b870e](https://github.com/jsmithpkp21/tooling/commit/12b870eab2d6034bf90b3d09a730b98ff684fd4b))
* **project-template:** set [python] version to 3.11.14 in tooling.toml ([0c77447](https://github.com/jsmithpkp21/tooling/commit/0c77447abf0c1dde520b1bae16b2870a13d1c47c))
* **project-template:** update setup.sh completion message — add git remote step ([772c054](https://github.com/jsmithpkp21/tooling/commit/772c054a6e449b0b03c6e12912d981fffa8ae374))
* **release-please:** add manifest source-of-truth and enforce version alignment ([0965c27](https://github.com/jsmithpkp21/tooling/commit/0965c27ab03b669c1a34637ab43216b9b563acc2))
* **release-please:** add manifest source-of-truth and enforce version sync ([76e6529](https://github.com/jsmithpkp21/tooling/commit/76e6529100b3c2cddede9161ea62fdf230c827c1))
* **release-please:** sync metadata version bumps with VERSION ([#97](https://github.com/jsmithpkp21/tooling/issues/97)) ([985a0c2](https://github.com/jsmithpkp21/tooling/commit/985a0c2c7093337855b815ba09ed578832601696))
* **release-please:** use path keys for extra-files entries ([6f34c55](https://github.com/jsmithpkp21/tooling/commit/6f34c5562e3fd251fa1e6586acdfb30dc8ae617c))
* **release:** harden post-release version sync workflow ([#206](https://github.com/jsmithpkp21/tooling/issues/206)) ([9933e22](https://github.com/jsmithpkp21/tooling/commit/9933e22af45dd18d759646da136c199460fecb20))
* **release:** trigger patch release for commit-subject hook ([f071f24](https://github.com/jsmithpkp21/tooling/commit/f071f244cee06258ddd720afd8d3e00fb041ca57))
* **release:** use supported extra-files type for VERSION ([7c0b966](https://github.com/jsmithpkp21/tooling/commit/7c0b966b2348805d0e2f5b798f3a273fa3617e45))
* remove stray 'ib' characters breaking the file ([817ba79](https://github.com/jsmithpkp21/tooling/commit/817ba795c3407d620530ca4a539d08bdb0073294))
* remove trailing newline from VERSION file ([ea508e9](https://github.com/jsmithpkp21/tooling/commit/ea508e9a7cf94cda84e3cc7ce077cb83674bae3b))
* replace buggy sed range with stateful awk parser for [python] section ([38febd6](https://github.com/jsmithpkp21/tooling/commit/38febd64da1a0b88d8b5764be0e9d4a21efe273b))
* replace tomllib with awk parser in verify_env.sh for consistency ([7c62e4d](https://github.com/jsmithpkp21/tooling/commit/7c62e4d264f34b9f72e6131ef1fc7a982962b0ba))
* replace Unicode symbols in test_setup.sh with plain ASCII for CI portability ([940897f](https://github.com/jsmithpkp21/tooling/commit/940897f9fceecb5e4adb4fbb733cad0fc7f28ee9))
* resolve CI KeyError by making verify-environment workflow DRY-compatible ([4ff88ac](https://github.com/jsmithpkp21/tooling/commit/4ff88aca87eb180d09e0b8fbba928f29415743d1))
* resolve mypy type error in merge_pyproject.py ([2e88387](https://github.com/jsmithpkp21/tooling/commit/2e88387de6f68ea6c6f6a5c174f33bcc308f3083))
* restore archive-compatible tooling source detection and add regressions ([c066490](https://github.com/jsmithpkp21/tooling/commit/c066490a2cfeb5c84acb3abc434e07d711c23268))
* restore robust activation pattern enforcement ([2bed9ec](https://github.com/jsmithpkp21/tooling/commit/2bed9ec3cdc564591246ff7a78370c0918e2c326))
* restore sync exclusions for project-template and sync script ([a3e7aae](https://github.com/jsmithpkp21/tooling/commit/a3e7aae3d707368b13ac89a36e360ec8107c7f77))
* **scripts:** preserve newline endings in action pin fixer ([ce8b3b1](https://github.com/jsmithpkp21/tooling/commit/ce8b3b16b6dec16f404772c2743d8974ebfd5c0c)), closes [#146](https://github.com/jsmithpkp21/tooling/issues/146)
* set default PYTHON_VERSION and PIP_VERSION before FROM statement ([4a1176b](https://github.com/jsmithpkp21/tooling/commit/4a1176bf7883ad0f00b35a053b739b167f09e177))
* simplify sync-tooling integration test to use REPO_ROOT as tooling ([50dc637](https://github.com/jsmithpkp21/tooling/commit/50dc63783e92b5c7bc1fcaa882786bf69b7ec0d6))
* simplify sync-tooling integration test to use REPO_ROOT as tooling ([044ce2b](https://github.com/jsmithpkp21/tooling/commit/044ce2b9a2a1c822068789328e9f39e4077c1577))
* sync project-template and preserve shell script executability ([4c1fd58](https://github.com/jsmithpkp21/tooling/commit/4c1fd5894af813df6b1e4eaa15752700eeeab098))
* sync project-template and preserve shell script executability ([6b457fa](https://github.com/jsmithpkp21/tooling/commit/6b457faff66e29fd6c4e3c175cf1ed0b2383b20a))
* **sync:** align update-sync-script source precedence and README wording ([#49](https://github.com/jsmithpkp21/tooling/issues/49)) ([6cf5d82](https://github.com/jsmithpkp21/tooling/commit/6cf5d8256178902e8e1ca5eb2d3ab1fe9ac40fda))
* **sync:** canonicalize target path and harden symlink checks in update script ([#49](https://github.com/jsmithpkp21/tooling/issues/49)) ([34d12aa](https://github.com/jsmithpkp21/tooling/commit/34d12aaa48b316f8e76e837eb5eff0446536d09a))
* **sync:** do not override existing release please manifest ([16fdc5c](https://github.com/jsmithpkp21/tooling/commit/16fdc5c9999a4ce52df4cb504a10ced4c8168d44))
* **sync:** harden drift enforcement and stale deletion safety ([d54c105](https://github.com/jsmithpkp21/tooling/commit/d54c10594cf2c0786c62b47cfa45f3375145400a))
* **sync:** harden manifest writes and narrow release docker inputs ([1348b32](https://github.com/jsmithpkp21/tooling/commit/1348b32a401f37fa8e9a3788dff34870afa1b0b0))
* **sync:** harden merge passthrough test and dedupe merge call ([21f0721](https://github.com/jsmithpkp21/tooling/commit/21f07214fd8a0aee28784afa3f2177c70e36215c))
* **sync:** harden tooling-source drift skip detection and stale-delete logging ([3ce3b67](https://github.com/jsmithpkp21/tooling/commit/3ce3b6779f0dfd4ccb90f5a61e17a74189135dd7))
* **sync:** harden update_sync_script symlink checks and relative-path traversal ([#49](https://github.com/jsmithpkp21/tooling/issues/49)) ([b39df15](https://github.com/jsmithpkp21/tooling/commit/b39df15cf71f60526e2c43fc010f05e8b96be0c7))
* **sync:** harden update-sync-script distribution and source detection ([#49](https://github.com/jsmithpkp21/tooling/issues/49)) ([16e4d40](https://github.com/jsmithpkp21/tooling/commit/16e4d40789e4de431c8e8493dbabef1e0c3943f8))
* **sync:** harden update-sync-script path handling and shell quoting ([#49](https://github.com/jsmithpkp21/tooling/issues/49)) ([d2f99a1](https://github.com/jsmithpkp21/tooling/commit/d2f99a149daea885600374835b36256b94aee4f3))
* **sync:** harden update-sync-script path resolution and env passthrough ([#49](https://github.com/jsmithpkp21/tooling/issues/49)) ([35ae0fb](https://github.com/jsmithpkp21/tooling/commit/35ae0fbbcc000b5df7461a5b7a63b1bb88964840))
* **sync:** harden update-sync-script per Copilot review feedback ([#49](https://github.com/jsmithpkp21/tooling/issues/49)) ([7e6b4d9](https://github.com/jsmithpkp21/tooling/commit/7e6b4d9bdab8a964bd8ef73a540c7a73cf56c72e))
* **sync:** harden update-sync-script per Copilot review feedback ([#49](https://github.com/jsmithpkp21/tooling/issues/49)) ([85143bd](https://github.com/jsmithpkp21/tooling/commit/85143bda228a889ee5f9fca0cbd283a3bc325ff6))
* **sync:** move version-sync validation hardening into shared tooling ([ec3308c](https://github.com/jsmithpkp21/tooling/commit/ec3308cccf8ceb6ab06462b4c2a176e1f66fa012))
* **sync:** move version-sync validation hardening into shared tooling ([0c21811](https://github.com/jsmithpkp21/tooling/commit/0c21811c7b35f27a27069ebb5ff5c99851354dd0)), closes [#52](https://github.com/jsmithpkp21/tooling/issues/52)
* **sync:** pass TOOLING_DIR through make update-sync-script and stderr aborts ([#49](https://github.com/jsmithpkp21/tooling/issues/49)) ([9be1b7b](https://github.com/jsmithpkp21/tooling/commit/9be1b7b3f0e28e2910476be356dd1550f11b4b45))
* **sync:** pass tooling-dir to merge_pyproject in archive mode ([8b00e71](https://github.com/jsmithpkp21/tooling/commit/8b00e71a348fd3202b90f17a4e2476a44228dea7))
* **sync:** pass tooling-dir to merge_pyproject in archive mode ([968c7d5](https://github.com/jsmithpkp21/tooling/commit/968c7d5c55b6344a3ccdcc41656a3c3b0510bf9d))
* **sync:** prevent empty managed docs from breaking consumer sync ([51664cb](https://github.com/jsmithpkp21/tooling/commit/51664cbe338de1741bc7e5725151a4fba417ea57))
* **sync:** prevent empty managed markdown docs from breaking consumer sync ([b325f40](https://github.com/jsmithpkp21/tooling/commit/b325f40519728b45d92ead4c5dcec2555986f93c))
* **sync:** resolve tooling source dirs with physical paths in update script ([#49](https://github.com/jsmithpkp21/tooling/issues/49)) ([3cb8e56](https://github.com/jsmithpkp21/tooling/commit/3cb8e5637a907cf73afea2a8328fde288af6c666))
* **sync:** ship consumer contract test in v1.13.1 ([3c0b1ed](https://github.com/jsmithpkp21/tooling/commit/3c0b1edcfd8ae2b26b5de375bc118a37a8597c7d))
* **sync:** skip non-regular stale targets during cleanup ([3cbd7d5](https://github.com/jsmithpkp21/tooling/commit/3cbd7d51e447ca4a9a7ff56d4eeedee3c6f72f3d))
* **template:** address review feedback for setup and docs ([67ccd62](https://github.com/jsmithpkp21/tooling/commit/67ccd62179e93f7ec8113e3cae1aaa27b66285c1))
* **template:** align lint formatter and clarify setup metadata ([ac8be49](https://github.com/jsmithpkp21/tooling/commit/ac8be49ef60173036af1e36228cda716a9c5870f))
* **tests:** avoid double-hashing drift lock fixture ([3986070](https://github.com/jsmithpkp21/tooling/commit/3986070c22057ebfd855ce4cbe64bc180d383172))
* **tests:** remove CWD mutation and add explicit encoding in workflow integration tests ([6db8b5f](https://github.com/jsmithpkp21/tooling/commit/6db8b5f7b8ffbc9e89ba1b23c00eeaccba861339))
* **tests:** satisfy consumer-contract checks after rebase ([57ee62e](https://github.com/jsmithpkp21/tooling/commit/57ee62eb5e1e771d61365fe61378c3407b11ce61))
* **tests:** skip real-manifest check in synced consumers ([fd2992d](https://github.com/jsmithpkp21/tooling/commit/fd2992db7ff1da68c4f3e1d2bb0d82fa3a433df3))
* **tooling:** enforce single source of truth for Python version ([3ae4a26](https://github.com/jsmithpkp21/tooling/commit/3ae4a263985c78d7d532d4410dd9f3c285ea8bc9))
* **tooling:** enforce single source of truth for Python version ([d666130](https://github.com/jsmithpkp21/tooling/commit/d66613076262941c9944ca09c3ddcd8904bf0de7))
* track and report actual Python version source in create_env.sh ([085fc04](https://github.com/jsmithpkp21/tooling/commit/085fc04d6a53843bf5010c99d9f962db1375e984))
* update documentation for GitHub Actions bypass ([bfbd201](https://github.com/jsmithpkp21/tooling/commit/bfbd201decf48c3e5f6257e8d4c8dc6461b689a6))
* update remaining base_env venv path references to REPO_NAME-env convention ([ba4f8bb](https://github.com/jsmithpkp21/tooling/commit/ba4f8bbf36b0fa24bf08c5a5f9a3e7f539eec3b9))
* Update scripts/create_env.sh ([1b3da25](https://github.com/jsmithpkp21/tooling/commit/1b3da25102d7dec220a054a8e4df4e8e9a77f355))
* update sync_tooling.sh to dynamically populate release-please config ([cc1b807](https://github.com/jsmithpkp21/tooling/commit/cc1b80763da150b7fa4d97c422474b1328ee41b8))
* update sync_tooling.sh to dynamically populate release-please config ([4b62737](https://github.com/jsmithpkp21/tooling/commit/4b62737aaf2a04bc710e545dba060bbe4f755413))
* use git config for consistent REPO_NAME detection ([3ecace6](https://github.com/jsmithpkp21/tooling/commit/3ecace642226d47051cb3fab0033902bb2e26ed6))
* use git probe instead of .git dir check in create_env.sh and verify_env.sh ([d11fbac](https://github.com/jsmithpkp21/tooling/commit/d11fbac12be896d700e0e6058bac5923a96cf342))
* use POSIX tools for Python version extraction (no Python 3.11+ dependency) ([1a0bcca](https://github.com/jsmithpkp21/tooling/commit/1a0bccab07566d119a6c771519748b68daf9712d))
* use stable venv name without version suffix ([e49d0f6](https://github.com/jsmithpkp21/tooling/commit/e49d0f6144803594b0397f7d39402061fd492763))
* use stable venv name without version suffix ([021da28](https://github.com/jsmithpkp21/tooling/commit/021da2875fa3dcba3b95e11c75d7855968b724b5))
* **version:** sync VERSION metadata with pyproject release version ([#91](https://github.com/jsmithpkp21/tooling/issues/91)) ([62212bf](https://github.com/jsmithpkp21/tooling/commit/62212bf064cea7a1138766bf542fc68bcab441c7))
* wire test_setup.sh into make test via test-shell target ([ae84218](https://github.com/jsmithpkp21/tooling/commit/ae84218ec4691b46106e56d87c8c7fa2d07727d5))
* worktree-safe git checks in setup.sh; add VERSION/tooling.toml/requirements.txt to template ([682d04a](https://github.com/jsmithpkp21/tooling/commit/682d04ac378573992830307ace06f508d7b79b9c))


### Performance Improvements

* **ci:** skip Docker rebuilds when inputs are unchanged ([eaf511d](https://github.com/jsmithpkp21/tooling/commit/eaf511d17622b3240dd8f03a6c59a8f35021ee2c))
* **ci:** upgrade workflow actions to Node.js 24 and add pytest --durations=10 ([c15b5ef](https://github.com/jsmithpkp21/tooling/commit/c15b5effb33c37008b0fac110a832d47ae70bd5b))


### Documentation

* add DYNAMIC_WORKFLOWS.md explaining all workflow changes ([7118c30](https://github.com/jsmithpkp21/tooling/commit/7118c308eca18e78c4eca7613e88a64112aacdd5))
* add PYPROJECT_ARCHITECTURE.md with corrected implementation details ([e8729be](https://github.com/jsmithpkp21/tooling/commit/e8729beb7dc7cb655e3a6f987d780487ac384ead))
* add sync governance guidance ([a554aa2](https://github.com/jsmithpkp21/tooling/commit/a554aa273f6fb0126bbf72578af81bbdab30a109))
* align FILE_DISTRIBUTION sync policy wording ([8ae3026](https://github.com/jsmithpkp21/tooling/commit/8ae3026250bbe7eb935ad884c4075a6c40b14dbf))
* clarify .pyproject.meta.toml is not synced ([6b5c7d9](https://github.com/jsmithpkp21/tooling/commit/6b5c7d9841de0666899e0ee2a0447f553b8bbc45))
* clarify FILE_DISTRIBUTION synced vs tooling-only sections ([3ed956e](https://github.com/jsmithpkp21/tooling/commit/3ed956ef144f8be8ffa5c066b85ea59eaea91d81))
* clarify sync_tooling.sh manual update path ([4746257](https://github.com/jsmithpkp21/tooling/commit/4746257767bc4228749e6109bf1a8caacd73912e))
* clarify tooling/pyproject.toml is not synced to projects ([06dda54](https://github.com/jsmithpkp21/tooling/commit/06dda54f9d5e828bbef934a6a73dbacdd9d484eb))
* complete audit and clarify sync_tooling.sh exclusion ([4860e51](https://github.com/jsmithpkp21/tooling/commit/4860e510f99d8903ce1d5869c02af87ca53f1646))
* **contributing:** add epic base-branch and merge-method checklist ([e28883f](https://github.com/jsmithpkp21/tooling/commit/e28883f397ba5c8b4789e716db40b515a60a7ff0))
* **docker:** list concrete runtime contract tests ([0416884](https://github.com/jsmithpkp21/tooling/commit/04168845d7088796fff71165aca940ea009518e5))
* fix file distribution link ([8f8218d](https://github.com/jsmithpkp21/tooling/commit/8f8218d323530ed2efa6f5e7e8ad1efb1d55c0d3))
* fix FILE_DISTRIBUTION to reflect project-template exclusion ([7f38709](https://github.com/jsmithpkp21/tooling/commit/7f387090838eb51f26b8de3eacff84c3aaae17e3))
* **lint:** enforce markdown link lint policy and CI alignment ([8e5c3e4](https://github.com/jsmithpkp21/tooling/commit/8e5c3e47ba9769ee603bc8f61244f0ccb73264aa)), closes [#70](https://github.com/jsmithpkp21/tooling/issues/70)
* remove stale git status snapshot from file distribution guide ([659b8f6](https://github.com/jsmithpkp21/tooling/commit/659b8f67339631fc04b3df840678de5f6146f9e9))
* replace broken TOOLING_ARCHITECTURE reference ([8e9e525](https://github.com/jsmithpkp21/tooling/commit/8e9e525966a02f6d72d80b4cdf5df56e1755f1bc))
* replace dead PYPROJECT_MERGE_IMPLEMENTATION link ([c009760](https://github.com/jsmithpkp21/tooling/commit/c009760b6e69871f2419db963e1de4c019d51947))
* **setup:** address PR feedback in gh auth troubleshooting ([a96abb4](https://github.com/jsmithpkp21/tooling/commit/a96abb49f3431bd46b1f361fbe24f34e6920fcf9))
* **setup:** address second round of review feedback on NEW_PROJECT.md ([0330393](https://github.com/jsmithpkp21/tooling/commit/03303930c44cad19488a7e48622c586bc68aab86))
* **setup:** address third round of review feedback on NEW_PROJECT.md ([9946e3a](https://github.com/jsmithpkp21/tooling/commit/9946e3aa4c43193bb504a1cdb7377f5cb78e8b74))
* **setup:** fix NEW_PROJECT bootstrap command examples and tooling guidance ([b36de2f](https://github.com/jsmithpkp21/tooling/commit/b36de2f15956dd65eaf561b1eedf1cde2a58a95d))
* sync fragile activation pattern fixes from base_repo ([1c797e7](https://github.com/jsmithpkp21/tooling/commit/1c797e79ccea0bb24de1e406af34c7e04e446b1f))
* **sync:** document allow-list contract, enforcement, and deletion workflow ([#63](https://github.com/jsmithpkp21/tooling/issues/63)) ([b4b9fe1](https://github.com/jsmithpkp21/tooling/commit/b4b9fe1d7abe3e2c9690f5e4cac35f9761f6df62))
* update FIX_GITHUB_ACTIONS_PR_PERMISSION.md with correct solution ([ac0d43b](https://github.com/jsmithpkp21/tooling/commit/ac0d43b77ea1eb4cce27919b819e495739f7217d))
* update pyproject architecture see also with repo-agnostic wording ([3351066](https://github.com/jsmithpkp21/tooling/commit/3351066f6f22aeefb21e34572514c0a90992ae07))
* update tooling/ to tooling repository ([00e29cc](https://github.com/jsmithpkp21/tooling/commit/00e29cc622bcaba26e861650c0cf56359641fc82))
* Updated PYPROJECT_ARCHITECTURE.md so it works in any project it is synced into. ([9ddb7fc](https://github.com/jsmithpkp21/tooling/commit/9ddb7fc28312ce3c401868d33da3aeb5ca314fe0))
* Updated PYPROJECT_ARCHITECTURE.md so it works in any project it… ([74f0e11](https://github.com/jsmithpkp21/tooling/commit/74f0e11140f7d63b230ed9a387eeba5d63ee52a8))
* updated tooling/ to tooling repo ([677177b](https://github.com/jsmithpkp21/tooling/commit/677177b5971b9a6b4079ce1c7b02450af9811967))
* **workflow:** add session handoff guide and cheat sheet ([#68](https://github.com/jsmithpkp21/tooling/issues/68)) ([ceab432](https://github.com/jsmithpkp21/tooling/commit/ceab432be6d3afb65b5a41dc271bb5ea74b39d5c))

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
