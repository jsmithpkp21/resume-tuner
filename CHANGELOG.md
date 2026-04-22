# Changelog

## [0.15.1](https://github.com/jsmithpkp21/resume-builder/compare/v0.15.0...v0.15.1) (2026-04-22)


### Bug Fixes

* **ci:** harden copilot kickoff against integration 403 ([93bb2d3](https://github.com/jsmithpkp21/resume-builder/commit/93bb2d3f07b221972c160fe9f0d2648bbf280463))
* **ci:** tighten kickoff dedupe and fail signaling ([11cb139](https://github.com/jsmithpkp21/resume-builder/commit/11cb13927459f5a95d7e3e870dbedc78401f63f5))

## [0.15.0](https://github.com/jsmithpkp21/resume-builder/compare/v0.14.1...v0.15.0) (2026-04-21)


### Features

* **data:** add graphcore-targeted bullets to experience_db ([1169b95](https://github.com/jsmithpkp21/resume-builder/commit/1169b95e12072d3a01f34febf5b09dffebdd8378))
* **resume:** enforce company-agnostic rendering and line-budget trimming ([aec9755](https://github.com/jsmithpkp21/resume-builder/commit/aec975550ce2a1c29ad1c9ea290aacc529a1a135))
* **review:** add next-layer PR review helper workflow ([5f6d3c2](https://github.com/jsmithpkp21/resume-builder/commit/5f6d3c20b093feac2cbb08b17b27a1d9e2ac6dd0))
* **review:** add PR review helper and address latest PR 123 comments ([6017aef](https://github.com/jsmithpkp21/resume-builder/commit/6017aefb06cf98c1b4f557a76f3f026eba41c327))
* **scripts:** add copilot review kickoff helper ([9bc276f](https://github.com/jsmithpkp21/resume-builder/commit/9bc276f24c7ef0291f9a1d4052c0f25ac724852e))


### Bug Fixes

* address 4 new review comments on PR [#123](https://github.com/jsmithpkp21/resume-builder/issues/123) ([30a0da5](https://github.com/jsmithpkp21/resume-builder/commit/30a0da5e3407fb5157cd6eadd5be6b83d245133c))
* **ci:** add fonts-liberation to Dockerfile and skip-guard font tests ([0064e14](https://github.com/jsmithpkp21/resume-builder/commit/0064e14488d7f68e6081bf04e9bc30a5249f9704))
* **ci:** align kickoff/docs with company-agnostic policy and dedupe ([d24c06c](https://github.com/jsmithpkp21/resume-builder/commit/d24c06ca153687bbc5674c147a9eac460f844d5f))
* **ci:** use pull_request_target for copilot kickoff ([f6e80c0](https://github.com/jsmithpkp21/resume-builder/commit/f6e80c0b83574ad6502ac085ebea79ad84644595))
* **resume:** address 7 PR 123 review comments ([bf6a25f](https://github.com/jsmithpkp21/resume-builder/commit/bf6a25fe3580641fc56897d57e2123d19b40330b))
* **review:** correct Makefile comment, tighten github assertion, add fork guard ([91279d2](https://github.com/jsmithpkp21/resume-builder/commit/91279d2a573c1057c8a26082115d0d1c9f3d1f95))
* **review:** defer managed Makefile wording to tooling ([64d8b4a](https://github.com/jsmithpkp21/resume-builder/commit/64d8b4acd4fb10479322dab78830c648c4f7f3d5))
* **review:** handle gh-missing errors and align test intent ([cc33eb8](https://github.com/jsmithpkp21/resume-builder/commit/cc33eb8da8d0b41e12d8e614181bb65c07b74d03))
* **review:** handle long-token wrapping and add copilot kickoff ([0e8763e](https://github.com/jsmithpkp21/resume-builder/commit/0e8763e3e25419f48c74d24a9b5e17f1582c12f9))
* **review:** harden kickoff/pr-review helpers and add unit coverage ([ed92998](https://github.com/jsmithpkp21/resume-builder/commit/ed92998f6a1b7ce4675a3052e481f7a1153d5470))
* **review:** tighten kickoff duplicate matching and summary fallback label ([c135c0f](https://github.com/jsmithpkp21/resume-builder/commit/c135c0f089524d183d095310337a0c0744bd46cf))
* **scripts:** include gh stderr/stdout context in kickoff helper failures ([10c6f35](https://github.com/jsmithpkp21/resume-builder/commit/10c6f356b41db5102907600b285139dca92b065c))
* **scripts:** replace --paginate with explicit pagination in request_copilot_review ([32112ca](https://github.com/jsmithpkp21/resume-builder/commit/32112cae5e29df85080b6aecb9f6c71aa8c42e89))
* **skills:** broaden fallback font path discovery for CI environments ([b54b69c](https://github.com/jsmithpkp21/resume-builder/commit/b54b69c05b5b6a61245070d4ade43f6411fca462))
* **summary:** prevent empty-data fallback from leaking target role ([bed242d](https://github.com/jsmithpkp21/resume-builder/commit/bed242d02479cb1ec05fadfaa48a466212c1f57e))
* **test:** remove graceful font skip guards - fail hard if fonts missing ([bc42173](https://github.com/jsmithpkp21/resume-builder/commit/bc42173ee14fa5394f92a1bc7ae2644c2867a96f))
* **test:** skip skills line check gracefully when no font available in CI ([a50977d](https://github.com/jsmithpkp21/resume-builder/commit/a50977d7685fa595818cda514e2d7085435c54f9))
* **trim:** warn when line budget cannot beat min-bullets floor ([947ccbd](https://github.com/jsmithpkp21/resume-builder/commit/947ccbdbc2a1ed10b888f327301513a0ca71a428))


### Documentation

* **graphcore:** add analysis, gap report, and generation preferences for issue 120 ([bfeb24d](https://github.com/jsmithpkp21/resume-builder/commit/bfeb24d5e905fdb1bfdfc253a981409c4a12cbb1))
* **review:** align target-role docs with current headline behavior ([0d66117](https://github.com/jsmithpkp21/resume-builder/commit/0d661178ede7d970b948fa202f63fa2ef929c0fa))

## [0.14.1](https://github.com/jsmithpkp21/resume-builder/compare/v0.14.0...v0.14.1) (2026-04-20)


### Bug Fixes

* **review:** use word-boundary matching for skill alias detection ([0fe280f](https://github.com/jsmithpkp21/resume-builder/commit/0fe280f0bd65613126264ef26efc5f2507150211))

## [0.14.0](https://github.com/jsmithpkp21/resume-builder/compare/v0.13.1...v0.14.0) (2026-04-19)


### Features

* **data:** finalize experience bullet and skill alignment ([776b261](https://github.com/jsmithpkp21/resume-builder/commit/776b261562989d370dee531d22b80ed44f89e8e5))
* **review:** add skill-text mismatch warning and reason-code parsing ([ccfca3b](https://github.com/jsmithpkp21/resume-builder/commit/ccfca3b483d48396a75a285af85ead9c7b9a849f))


### Bug Fixes

* **data:** apply agreed experience bullet updates ([35cd166](https://github.com/jsmithpkp21/resume-builder/commit/35cd1669640939a380e7b4716480dfac8f093d4f))

## [0.13.1](https://github.com/jsmithpkp21/resume-builder/compare/v0.13.0...v0.13.1) (2026-04-17)


### Bug Fixes

* **heuristics:** address PR review comments ([df6ede3](https://github.com/jsmithpkp21/resume-builder/commit/df6ede3a4ed8224d4bb18074b7992e5f24f17f4a))
* **tests:** import has_measurable_outcome from shared module ([9b56943](https://github.com/jsmithpkp21/resume-builder/commit/9b569434803d2b507c9e8c44ab98ea657339dfe8))

## [0.13.0](https://github.com/jsmithpkp21/resume-builder/compare/v0.12.1...v0.13.0) (2026-04-17)


### Features

* **generator:** add gap summary and measurable outcome targeting ([936c33e](https://github.com/jsmithpkp21/resume-builder/commit/936c33edd9904411bab34ca4725cc7cb663f5ee3))
* **generator:** refine title and skills review follow-ups ([a62204f](https://github.com/jsmithpkp21/resume-builder/commit/a62204fc11b828c93bcb66527f31e0b7fd5d92ef))
* **skills:** apply top-n cap before budget packing ([#97](https://github.com/jsmithpkp21/resume-builder/issues/97)) ([6ed4620](https://github.com/jsmithpkp21/resume-builder/commit/6ed46204805b1f01511fae59d829172682d6ab47))
* **skills:** normalize near-duplicate skill labels ([#97](https://github.com/jsmithpkp21/resume-builder/issues/97)) ([10a42ed](https://github.com/jsmithpkp21/resume-builder/commit/10a42ed08d825828645d45d55f66b3ac70512148))


### Bug Fixes

* **generator:** address follow-up review comments ([856a2a9](https://github.com/jsmithpkp21/resume-builder/commit/856a2a93b55fc214fa1ce29c7c66c852eee218c5))
* **heuristics:** broaden measurable outcome detection ([acbffaa](https://github.com/jsmithpkp21/resume-builder/commit/acbffaa6be1ac3e63939e0218e1f803c06d86924))
* **skills:** ensure _compute_skill_scores covers all matrix skills for top-N cap ranking ([bca1c32](https://github.com/jsmithpkp21/resume-builder/commit/bca1c324363063eca414b45f5a5a6de90cc6505e))
* **skills:** normalize dupes before cap, cover all matrix skills, drop dead alias ([28b0937](https://github.com/jsmithpkp21/resume-builder/commit/28b0937ea54e3cee4c12f119d77b1dd49710a7a9))
* **skills:** use keyword arg for cap call and update select_skills docstring ([b662ff6](https://github.com/jsmithpkp21/resume-builder/commit/b662ff6209f9d881056c5805e03c8cdd20d1870b))

## [0.12.1](https://github.com/jsmithpkp21/resume-builder/compare/v0.12.0...v0.12.1) (2026-04-15)


### Bug Fixes

* **docs:** align WSL path format examples (use backslash UNC in from column) ([c2017a1](https://github.com/jsmithpkp21/resume-builder/commit/c2017a1e6c7c0cccd0ddee3465b1a40e3f6564ab))
* **docs:** clarify tooling owns manifest in consumer agent guidance ([d2385f6](https://github.com/jsmithpkp21/resume-builder/commit/d2385f6da32176ee5bb8f0aad82e97073795b8a5))
* **sync:** update lock hashes for AGENTS and copilot instructions ([13b4c20](https://github.com/jsmithpkp21/resume-builder/commit/13b4c20d741ed8033ea2356f36e0379f49eb61a0))
* **version:** align VERSION with release-please manifest ([dfa3146](https://github.com/jsmithpkp21/resume-builder/commit/dfa31462f42acaef00ac81859366ebed73cf2ef0))


### Documentation

* **sync:** align consumer agent guidance with tooling contract ([27892ca](https://github.com/jsmithpkp21/resume-builder/commit/27892ca5fbb055aa43810fa7b34f032bcc4dafcc))

## [0.12.0](https://github.com/jsmithpkp21/resume-builder/compare/v0.11.1...v0.12.0) (2026-04-14)


### Features

* **profile:** support local-only personal overrides ([31f8c19](https://github.com/jsmithpkp21/resume-builder/commit/31f8c1978f868728efbb81035d95c9f1da188aea))


### Bug Fixes

* **profile:** address latest PR review comments ([dac73a6](https://github.com/jsmithpkp21/resume-builder/commit/dac73a64d3a9867b8774ba2a23083d490aa8db0b))
* **profile:** address PR review feedback ([9e4729b](https://github.com/jsmithpkp21/resume-builder/commit/9e4729b43ae7722172091d0b3d68f7ed5e6e4b7f))
* **profile:** address remaining PR comments ([ec71057](https://github.com/jsmithpkp21/resume-builder/commit/ec71057e7206f3828fa6b8286eaad120174a0b7a))
* **profile:** allow local section overrides and left-align info blocks ([824831c](https://github.com/jsmithpkp21/resume-builder/commit/824831ca39647c8dd37120ea4e26304a9fc514e3))
* **profile:** make baseline test deterministic ([d365406](https://github.com/jsmithpkp21/resume-builder/commit/d36540685436e4c12e92201087962e8ec2803ee4))
* **profile:** reject local override as base profile ([cbad9fd](https://github.com/jsmithpkp21/resume-builder/commit/cbad9fdf6ea48cee76b44f2ec506f30a98226816))
* **profile:** validate local section overrides ([42c612a](https://github.com/jsmithpkp21/resume-builder/commit/42c612ac95ab9046ee81661a44306810e2a9b8a3))

## [0.11.1](https://github.com/jsmithpkp21/resume-builder/compare/v0.11.0...v0.11.1) (2026-04-13)


### Documentation

* **repo:** add missing heading spacing in runbook ([c48e2a2](https://github.com/jsmithpkp21/resume-builder/commit/c48e2a2297ea0a77a5b4c21860eee23994444b82))
* **repo:** add public settings runbook for issue 99 ([fe45f39](https://github.com/jsmithpkp21/resume-builder/commit/fe45f390934ea18d4a092f8a379dd72b2137aa6e))
* **repo:** address additional runbook review comments ([6ecb9ed](https://github.com/jsmithpkp21/resume-builder/commit/6ecb9ed110c85f27a48ad062e68e44cfb21e73ff))
* **repo:** address runbook review feedback ([9241146](https://github.com/jsmithpkp21/resume-builder/commit/9241146ead9a21f6773b773fae6b87b6e08390a8))
* **repo:** clarify rewrite force-push exception flow ([caa093b](https://github.com/jsmithpkp21/resume-builder/commit/caa093b18ea5826ad24bdbf82e1fb370ca4e7d4d))

## [0.11.0](https://github.com/jsmithpkp21/resume-builder/compare/v0.10.2...v0.11.0) (2026-04-13)


### Features

* **resume:** align enrich gating with signal availability ([996231f](https://github.com/jsmithpkp21/resume-builder/commit/996231f3f82a21c72e7f8e817d8e5df8b2c1a8b7))


### Bug Fixes

* **resume:** honor role_hint in enrich_data gating ([06d11d4](https://github.com/jsmithpkp21/resume-builder/commit/06d11d4eade22076b03e8e993544a28cabcd2168))

## [0.10.2](https://github.com/jsmithpkp21/resume-builder/compare/v0.10.1...v0.10.2) (2026-04-13)


### Bug Fixes

* **security:** reduce dns rebinding window in fetch path ([7c76e82](https://github.com/jsmithpkp21/resume-builder/commit/7c76e82fa6d898d2b1bd99d2122415c81cd6009e))

## [0.10.1](https://github.com/jsmithpkp21/resume-builder/compare/v0.10.0...v0.10.1) (2026-04-13)


### Bug Fixes

* **security:** block dns-resolved private job hosts ([b14537f](https://github.com/jsmithpkp21/resume-builder/commit/b14537f87f575221c3f834de2d7334af9aaa5dd6))
* **security:** block ipv4-mapped ipv6 private hosts ([4d2fe72](https://github.com/jsmithpkp21/resume-builder/commit/4d2fe72a37952ae3fa3e3973400c9dd8159cfd66))

## [0.10.0](https://github.com/jsmithpkp21/resume-builder/compare/v0.9.0...v0.10.0) (2026-04-12)


### Features

* **title:** implement generic issue [#30](https://github.com/jsmithpkp21/resume-builder/issues/30) framing and reporting ([81d244c](https://github.com/jsmithpkp21/resume-builder/commit/81d244c20456edfd27123720833dbc41b5377f66))

## [0.9.0](https://github.com/jsmithpkp21/resume-builder/compare/v0.8.1...v0.9.0) (2026-04-12)


### Features

* **data:** add starter data layout for ai inputs ([288d291](https://github.com/jsmithpkp21/resume-builder/commit/288d2915526ddc478cb09f09c5761adece44e9c6)), closes [#7](https://github.com/jsmithpkp21/resume-builder/issues/7)
* **data:** define skill-category contract and seed master experience data ([f2b4322](https://github.com/jsmithpkp21/resume-builder/commit/f2b4322322571d8091cd9f5f7b30a809bc4c470b))
* **data:** establish starter data layout for AI resume inputs ([d2b0681](https://github.com/jsmithpkp21/resume-builder/commit/d2b0681d0d3e2475eb65d7d72818c201db119e7c))
* **data:** reconcile resume experience inventory ([924ccb8](https://github.com/jsmithpkp21/resume-builder/commit/924ccb839be0e70697fe6f516f01da6168dd3266))
* **font:** add RESUME_FONT_STRICT env var and --strict-font CLI flag ([1cda260](https://github.com/jsmithpkp21/resume-builder/commit/1cda260296ff2ba69b4bb29995a98d586538276f)), closes [#45](https://github.com/jsmithpkp21/resume-builder/issues/45)
* **output:** add baseline resume generation pipeline ([#34](https://github.com/jsmithpkp21/resume-builder/issues/34)) ([35d69ed](https://github.com/jsmithpkp21/resume-builder/commit/35d69ed2417f7a2d5e8910d5635fc4870f9af674))
* **output:** add dynamic headline and profile bottom sections ([#34](https://github.com/jsmithpkp21/resume-builder/issues/34)) ([2e180c8](https://github.com/jsmithpkp21/resume-builder/commit/2e180c8997dc086a603d81392e0d989f66191b9e))
* **output:** auto-build social URLs from handles ([#34](https://github.com/jsmithpkp21/resume-builder/issues/34)) ([339c1f1](https://github.com/jsmithpkp21/resume-builder/commit/339c1f1b5043a7d8c73c4dc1ec682a3196609ea6))
* **output:** dynamic headline and bottom profile sections ([0186571](https://github.com/jsmithpkp21/resume-builder/commit/0186571595e8bbb7686c15a73d03763e35b67756))
* **output:** dynamic headline and bottom profile sections ([57ba628](https://github.com/jsmithpkp21/resume-builder/commit/57ba628dde307a7aa27a2432a2e6d56c3f5e6209))
* **output:** ingest job URL with deterministic company context ([#34](https://github.com/jsmithpkp21/resume-builder/issues/34)) ([e29e677](https://github.com/jsmithpkp21/resume-builder/commit/e29e677b5383a60fec6438fe23e1598134ae6435))
* **resume:** add company output aliases and sandbox-first run guidance ([#55](https://github.com/jsmithpkp21/resume-builder/issues/55)) ([4f2f293](https://github.com/jsmithpkp21/resume-builder/commit/4f2f293833774b5985d905c663d7632d37b74a24))
* **resume:** add diff-friendly text snapshot artifact ([c21ae47](https://github.com/jsmithpkp21/resume-builder/commit/c21ae472e69daaa8499395f09b5ef1a791037094))
* **resume:** add source-backed SDET bullets and data-driven summaries ([47b64f2](https://github.com/jsmithpkp21/resume-builder/commit/47b64f282fc9e875eb0a5c002177e2e755bef8ce))
* **resume:** calibrate profile summary word cap from sandbox resumes ([#53](https://github.com/jsmithpkp21/resume-builder/issues/53)) ([ec1f441](https://github.com/jsmithpkp21/resume-builder/commit/ec1f4413698a72119dd16b4cd0b74b4e0e2d4147))
* **resume:** implement enrich and rule-based trimming ([9d409e2](https://github.com/jsmithpkp21/resume-builder/commit/9d409e2f30c9907c412f98aade96f32018bc61f3))
* **resume:** improve processed summary readability ([d34ecd6](https://github.com/jsmithpkp21/resume-builder/commit/d34ecd64c1385c9c941923f7506cfdfa6616673c))
* **resume:** issue [#39](https://github.com/jsmithpkp21/resume-builder/issues/39) umbrella - LLM-driven resume adaptation ([b6d918f](https://github.com/jsmithpkp21/resume-builder/commit/b6d918f58727e6f675af0b02dbc183e4684beaf2))
* **resume:** pack skills into unified categories and standardize output filenames ([989d041](https://github.com/jsmithpkp21/resume-builder/commit/989d041063a737340a19136e24aca7b9f60ea202))
* **resume:** raise total bullet cap to 20 ([181ae25](https://github.com/jsmithpkp21/resume-builder/commit/181ae256cf06106e32cbb83d8d3c8fa8e544e5f3))
* **resume:** refine experience layout and headers ([0e6309f](https://github.com/jsmithpkp21/resume-builder/commit/0e6309f5092cad965541d4268d4154208ef30b5a))
* **resume:** support job text file and company-site URL fallback ([d9e8fd2](https://github.com/jsmithpkp21/resume-builder/commit/d9e8fd207791bf8f1f7930004b277edcba2a7416))
* **resume:** unify template contract and add generated resume title ([9b3d085](https://github.com/jsmithpkp21/resume-builder/commit/9b3d08503c60dfea675cb412ea22c13416883869))
* **resume:** unify template section contract and add generated title block ([36deca6](https://github.com/jsmithpkp21/resume-builder/commit/36deca6084dd8ccf79cd49a2d14d8551b8c6df6b))
* **scripts:** enforce canonical-only runtime inputs ([#20](https://github.com/jsmithpkp21/resume-builder/issues/20)) ([03ad6b9](https://github.com/jsmithpkp21/resume-builder/commit/03ad6b9853fc19c41a0c4767fbdc2af53203ef22))
* **scripts:** enforce canonical-only runtime inputs ([#20](https://github.com/jsmithpkp21/resume-builder/issues/20)) ([210a67e](https://github.com/jsmithpkp21/resume-builder/commit/210a67ebd23a87fe57d2973754e9cbaa9d68c1a3))
* **skills:** implement deterministic 11-13 line skills packing ([#42](https://github.com/jsmithpkp21/resume-builder/issues/42)) ([8478e99](https://github.com/jsmithpkp21/resume-builder/commit/8478e99b3c64645d70738ba08e4456b027b1910b))
* **skills:** prioritize category reduction in packing ([01d6d18](https://github.com/jsmithpkp21/resume-builder/commit/01d6d18a1c77d1f91fe8523e5419671a9b706640))
* **spike:** add report artifact and tests for skills line measurement ([8e6995b](https://github.com/jsmithpkp21/resume-builder/commit/8e6995b0f7dcf80a3c1c2e853f4fedcef1a968a2))
* **spike:** start pdf-first skills line measurement loop for wrap-aware packing ([2790213](https://github.com/jsmithpkp21/resume-builder/commit/2790213200449102f92db08b17bd60248f99139d))
* **transform:** add rewrite guardrails for tone drift ([34d9aee](https://github.com/jsmithpkp21/resume-builder/commit/34d9aee343e07bea8458c6d47f460b8ce900fd75))
* **trim:** log score maps before bullet ranking ([40254b8](https://github.com/jsmithpkp21/resume-builder/commit/40254b8f94ba345f970b0bec1028833b9f75f26e))


### Bug Fixes

* **artifact:** align baseline JSON target_lines_max to 12 per DESIGN.md ([d995ff2](https://github.com/jsmithpkp21/resume-builder/commit/d995ff2db20f9b55be1e9bc513dddb4ebca7dbc8))
* **cli:** clarify secondary template help and harden related_skills contract test ([14644f2](https://github.com/jsmithpkp21/resume-builder/commit/14644f25d57999d18c7b9677802b5d0fcddef50f))
* **data:** add debugging time reduction to audio error-handling bullet ([f35fa12](https://github.com/jsmithpkp21/resume-builder/commit/f35fa123fa7773c027f2455cb8a45ee067b306c4))
* **data:** clarify Android-based embedded UI testing in b01 bullet ([610a78f](https://github.com/jsmithpkp21/resume-builder/commit/610a78f801a20d9d4fe2b1499a1a3f80a5b98140))
* **data:** combine headset lab action and quantified outcome ([71ff2cb](https://github.com/jsmithpkp21/resume-builder/commit/71ff2cbd24e0b1ae283ef869186762f8332e6213))
* **data:** commit experience_db and reviewer_notes changes from WS:13 session ([083db9d](https://github.com/jsmithpkp21/resume-builder/commit/083db9d2cba22db45df6fe6a338d6dd79d17787b))
* **data:** move remote logging bullet to correct 2008-2015 role ([1c7da96](https://github.com/jsmithpkp21/resume-builder/commit/1c7da968a6c07dd5887df2477ac7529ffb3bdace))
* **data:** resolve AMD WS:13 CT_SCOPE conflict for Lead Framework Designer role ([85f97ff](https://github.com/jsmithpkp21/resume-builder/commit/85f97ff87163c8706fea2b8713656bf4e3cd4af6))
* **data:** resolve type hints in experience validation script ([80fda09](https://github.com/jsmithpkp21/resume-builder/commit/80fda097b62caf135fa6db4dc76a2ca9f96efc80))
* **data:** split reviewer notes into valid CSV rows ([968b526](https://github.com/jsmithpkp21/resume-builder/commit/968b526f678bddcd4118790cadd6ef3fd2481d86))
* **data:** tighten quantified bullet wording in experience db ([470f860](https://github.com/jsmithpkp21/resume-builder/commit/470f8602500cf38ce40d6b7b2847307a99e274b6))
* **e2e:** make fixture harness portable and deterministic ([a9261f8](https://github.com/jsmithpkp21/resume-builder/commit/a9261f821fb32ef9b24ec12aeadef17eba499b93))
* **font:** enforce Calibri in strict mode for explicit paths ([4b9a981](https://github.com/jsmithpkp21/resume-builder/commit/4b9a9811ddb68dbc74fb41485164f22dd950eb94))
* **pipeline:** f-string placeholders, NaN/inf guard, and live-mode cache path ([841f724](https://github.com/jsmithpkp21/resume-builder/commit/841f7241f969e621ac1b1a92d0cbc667a42ccdfe))
* regenerate pyproject.toml and remove create_issues.sh ([0b58d74](https://github.com/jsmithpkp21/resume-builder/commit/0b58d7486fe5c6492c1f1ee7786058c8d06612a9))
* **render:** tighten skills category spacing in HTML output ([#42](https://github.com/jsmithpkp21/resume-builder/issues/42)) ([26cd794](https://github.com/jsmithpkp21/resume-builder/commit/26cd7945827e7cbb30dd967ec92c11b04eb70793))
* **render:** tighten skills category spacing in HTML output ([#42](https://github.com/jsmithpkp21/resume-builder/issues/42)) ([6d7be66](https://github.com/jsmithpkp21/resume-builder/commit/6d7be66186bd51c903d925d4c1aece8bae5aee51))
* **resume:** address PR [#40](https://github.com/jsmithpkp21/resume-builder/issues/40) review comments ([fca79e5](https://github.com/jsmithpkp21/resume-builder/commit/fca79e5c3b9b3a6ab3739901a31b0ada1ab8ea33))
* **resume:** address summary review follow-ups ([092d5a7](https://github.com/jsmithpkp21/resume-builder/commit/092d5a777d6adc23b9a1895c4ff7925de66118d7))
* **resume:** harden input validation and review workflow policy ([e59a784](https://github.com/jsmithpkp21/resume-builder/commit/e59a784d88fa68a1de0941b9bd0ccdd2121eb347))
* **resume:** make job-url tests offline and harden ingest ([6a90a6e](https://github.com/jsmithpkp21/resume-builder/commit/6a90a6ee7f19110d6501c5d5801a00ccea46f1f5))
* **resume:** raise min bullets to 3 and fix trim ordering ([8839c82](https://github.com/jsmithpkp21/resume-builder/commit/8839c826d378d3f7ca3961cb69ac9cd38b8a8140))
* **resume:** resolve remaining PR [#35](https://github.com/jsmithpkp21/resume-builder/issues/35) review threads ([7954f48](https://github.com/jsmithpkp21/resume-builder/commit/7954f483069ae314a98d5b80b470892f6102e5a1))
* **review:** address pr 49 follow-up comments ([b3f6080](https://github.com/jsmithpkp21/resume-builder/commit/b3f6080336fb487f66e6cba5312bc579dc16ce5c))
* **review:** address remaining pr 49 comments ([852fcdd](https://github.com/jsmithpkp21/resume-builder/commit/852fcdd4a5714d49366cec2a8a63ab71c25f525b))
* **review:** align template docs and output naming ([477b7a7](https://github.com/jsmithpkp21/resume-builder/commit/477b7a7bd17861c9453e3361eefceef7fa0f65e8))
* **review:** resolve AMD architect scope conflict with source-faithful split ([db58c18](https://github.com/jsmithpkp21/resume-builder/commit/db58c18067a1506e1091b44392da954da24deda2))
* **review:** sync baseline output docs and artifacts ([9e2143b](https://github.com/jsmithpkp21/resume-builder/commit/9e2143b768c4d50cd65b2905ec51daf75a029ed9))
* **scope:** align ownership wording with actual authority ([a4d9f94](https://github.com/jsmithpkp21/resume-builder/commit/a4d9f94ba00bbcce66ce06b57c88247e26406f19))
* **scripts:** align [#20](https://github.com/jsmithpkp21/resume-builder/issues/20) tests/messages with PR [#33](https://github.com/jsmithpkp21/resume-builder/issues/33) feedback ([712fd8f](https://github.com/jsmithpkp21/resume-builder/commit/712fd8f09d3a2b89acc264fc9c59c54d21fb334c))
* **scripts:** avoid sys.path mutation for shared runtime guard imports ([abb10d8](https://github.com/jsmithpkp21/resume-builder/commit/abb10d885c4c24aab0171b7084b4fb6ad6928df4))
* **scripts:** read skills matrix csv with utf-8 newline handling ([83cdd48](https://github.com/jsmithpkp21/resume-builder/commit/83cdd486d707eadffc851d10137b69824f58710d))
* **scripts:** resolve remaining PR [#33](https://github.com/jsmithpkp21/resume-builder/issues/33) review comments ([10af5ee](https://github.com/jsmithpkp21/resume-builder/commit/10af5eeab4f505f6395f64e1313b3e57b176b581))
* **security:** close remaining PR [#35](https://github.com/jsmithpkp21/resume-builder/issues/35) review threads ([d1ada9f](https://github.com/jsmithpkp21/resume-builder/commit/d1ada9ff376ece9df5713a6a766b089ce9cb6d82))
* **security:** harden job-url metadata fetch guards ([01691bd](https://github.com/jsmithpkp21/resume-builder/commit/01691bd93c19215f8b2288804464bd480d047d57))
* **security:** harden URL validation and social slug normalization ([016d9b4](https://github.com/jsmithpkp21/resume-builder/commit/016d9b483f7fa75ea2d5be540b9e86fe9aac8195))
* **skills:** address review feedback ([cbc2182](https://github.com/jsmithpkp21/resume-builder/commit/cbc2182fce04a1236360247d8f305546861cf297))
* **skills:** deduplicate category entries and enforce casing ([2986ddb](https://github.com/jsmithpkp21/resume-builder/commit/2986ddb2a159702d6d8bbf776496841247bc4347))
* **skills:** make wrap triggers actionable and harden prefix-kern test ([a99f371](https://github.com/jsmithpkp21/resume-builder/commit/a99f3711421c654c145f9ee3cbb3f7a5be1c5627))
* **skills:** order categories by role relevance ([49f1af1](https://github.com/jsmithpkp21/resume-builder/commit/49f1af1e770cdc78af87fb595de3e7ca90fe1cbf))
* **skills:** remove redundant industry hint normalization ([02e5e40](https://github.com/jsmithpkp21/resume-builder/commit/02e5e4059bb510df5c14f135ba09b1aa2707f26f))
* **skills:** resolve PR [#78](https://github.com/jsmithpkp21/resume-builder/issues/78) review comments ([d66ce0e](https://github.com/jsmithpkp21/resume-builder/commit/d66ce0e024846fbafb1657c1609ca7b37e921849))
* **skills:** resolve PR [#82](https://github.com/jsmithpkp21/resume-builder/issues/82) follow-up review comments ([1dc0cb0](https://github.com/jsmithpkp21/resume-builder/commit/1dc0cb0eeb17d169004b44b074d51c626dbccbe4))
* **skills:** resolve PR [#82](https://github.com/jsmithpkp21/resume-builder/issues/82) review comments ([261845b](https://github.com/jsmithpkp21/resume-builder/commit/261845b9f52f936f710e22ba752d194ed46c3b19))
* **spike:** address PR [#44](https://github.com/jsmithpkp21/resume-builder/issues/44) review findings for skills measurement ([e8c0f39](https://github.com/jsmithpkp21/resume-builder/commit/e8c0f39418112384d17fc32557e282cf51348e8c))
* **spike:** address remaining kerning wrap review findings ([7f3ef7a](https://github.com/jsmithpkp21/resume-builder/commit/7f3ef7a725a4d21e50b82734646266c6edac049c))
* **spike:** align budget and font labeling with review feedback ([8bcd15f](https://github.com/jsmithpkp21/resume-builder/commit/8bcd15fc11cdc5a0d7292e427f3e5b8eed6e0f98))
* **spike:** align skills spike docs and artifact schema ([8f61b64](https://github.com/jsmithpkp21/resume-builder/commit/8f61b64ca29c303c9026133a88eb64eea592d498))
* **spike:** avoid applying Regular kern table to bold prefix widths ([083a2c0](https://github.com/jsmithpkp21/resume-builder/commit/083a2c013c00aba86770afc717bb37edf6eb7787))
* **spike:** gate --kern on Calibri and align test kern loading ([ec7d607](https://github.com/jsmithpkp21/resume-builder/commit/ec7d60747ee2735e13b17f311d36db09aa754a0d))
* **spike:** harden font fallback loading and clarify kerning docs ([52bfea5](https://github.com/jsmithpkp21/resume-builder/commit/52bfea5da850a9ef0d5dcceea753931d02d1ac37))
* **spike:** temporarily allow fallback fonts for CI stability ([e7eed0a](https://github.com/jsmithpkp21/resume-builder/commit/e7eed0a488c317a867c14edc3c2fe2e74db85346))
* **summary:** address PR review findings on role summaries ([1990ec9](https://github.com/jsmithpkp21/resume-builder/commit/1990ec920e68f72b30c85baa8a0fad0adc0429fb))
* **summary:** address review feedback and restore check ([3927da5](https://github.com/jsmithpkp21/resume-builder/commit/3927da5d607e56f2f377ff8b7cccb3e793ee67ad))
* **summary:** prevent fragmented role summary output ([df0419f](https://github.com/jsmithpkp21/resume-builder/commit/df0419f2bb6fbb162a847f825367442d1b034cf0))
* **templates:** remove dead .headline CSS from ModernTemplate ([874ea44](https://github.com/jsmithpkp21/resume-builder/commit/874ea448f816c041bd53e858e9b420ec44e5a38b))
* **templates:** update name to Jonathan J Smith and modernize layout ([930931b](https://github.com/jsmithpkp21/resume-builder/commit/930931b4469bf0b840bbf1a66b3f83be78999181))
* **templates:** wrap contact lines in .contact div in both templates ([3e7039f](https://github.com/jsmithpkp21/resume-builder/commit/3e7039f05ba4ee6f0e30b0327b553d96c9ba044c))
* **test:** add deterministic prefix-kern boundary guard ([115607f](https://github.com/jsmithpkp21/resume-builder/commit/115607fb0de90cf1493a8ec310e464685586694e))
* **test:** assert non-empty summary in fragment regression ([620e2f3](https://github.com/jsmithpkp21/resume-builder/commit/620e2f39e522a2bfeb250698a953e9ea02b7d514))
* **test:** close final review items for kerning wrap behavior ([c18eb66](https://github.com/jsmithpkp21/resume-builder/commit/c18eb66129df57d5300aa0643831b2767b2e95e4))
* **test:** make sensitivity test font-agnostic for CI fallback fonts ([2565d90](https://github.com/jsmithpkp21/resume-builder/commit/2565d904ae08830086505cc9e362361de52624e9))
* **test:** remove always-true kern assertion in prefix guard ([c311778](https://github.com/jsmithpkp21/resume-builder/commit/c31177842bd41a405ab41973bf36bad5a389bf24))
* **test:** stabilize width boundary check and drop redundant import ([ef20ba5](https://github.com/jsmithpkp21/resume-builder/commit/ef20ba5dc4a1777604afb1a38c81bfad5e76fc95))
* **test:** tighten skills duplicate contract assertions ([cad2f71](https://github.com/jsmithpkp21/resume-builder/commit/cad2f713f0516273aa4b8e4dfd31c088bd5d960b))
* **test:** use token-summing for removing-skill width boundary ([ffe0fbf](https://github.com/jsmithpkp21/resume-builder/commit/ffe0fbf5d4a8db2ae0467d19e5ad14586fde6988))
* **typing:** address strict narrowing and redirect override compatibility ([6e24fbf](https://github.com/jsmithpkp21/resume-builder/commit/6e24fbf1ebda41243b351b42c238e86c2f03bfe0))


### Documentation

* **agent:** codify PR-thread response boundaries ([1645867](https://github.com/jsmithpkp21/resume-builder/commit/1645867e3ae41282ffd40420288c76fe1219d15c))
* **agents:** add WSL path handling rules to prevent UNC path write failures ([065e23e](https://github.com/jsmithpkp21/resume-builder/commit/065e23ec145fea665fdfc361165e19870827c081))
* **design:** add final-pass action word diversity rule ([fd626ab](https://github.com/jsmithpkp21/resume-builder/commit/fd626ab9013d3fdcc9482a486e6f28ea62782be3))
* **design:** add inference-first adaptation policy and remove role_audience field ([14eb168](https://github.com/jsmithpkp21/resume-builder/commit/14eb168e5e0b086e3c6f95ddd7a7970bc170d9df))
* **design:** add skill/category detection design and update improvements backlog ([449b216](https://github.com/jsmithpkp21/resume-builder/commit/449b216b9fedc281ec33dce4324e74bb62602583))
* **design:** clarify future layout overflow pass ([32bc2f9](https://github.com/jsmithpkp21/resume-builder/commit/32bc2f9a1f405b9e315e3a0911ddc840c6924bc2))
* **font:** align strict precedence and sensitivity wording ([0976f92](https://github.com/jsmithpkp21/resume-builder/commit/0976f92cc14cd071201411a4b2bfa56d59a3a142))
* **guidance:** add application guidance checklist for issue 61 ([b113ac4](https://github.com/jsmithpkp21/resume-builder/commit/b113ac4e160ed8620c7bc3f6a99cd52a74dfee28)), closes [#61](https://github.com/jsmithpkp21/resume-builder/issues/61)
* **guidance:** resolve PR 74 review feedback ([f816374](https://github.com/jsmithpkp21/resume-builder/commit/f816374070d7b9e4f8616c8a5cff3e95db433a2b))
* initial design ([d5edd10](https://github.com/jsmithpkp21/resume-builder/commit/d5edd10dd512bb84682a348190f6d232a844f3fb))
* **process:** capture workflow decisions and issue backlog ([1f14666](https://github.com/jsmithpkp21/resume-builder/commit/1f1466636b3a0e3108ab930c5dbc46e218ff29c4))
* **qa:** add pre-submit QA checklist for issue [#63](https://github.com/jsmithpkp21/resume-builder/issues/63) ([0ae934b](https://github.com/jsmithpkp21/resume-builder/commit/0ae934b5d69666539b3aeb079972ef15e214dc5d))
* **qa:** address PR [#76](https://github.com/jsmithpkp21/resume-builder/issues/76) wording review notes ([ee9f6ad](https://github.com/jsmithpkp21/resume-builder/commit/ee9f6adb6a1d688a4de19e36d1df144323c2d42e))
* **qa:** clarify canonical experience_db path ([0056f21](https://github.com/jsmithpkp21/resume-builder/commit/0056f212d2b552b7a69cd4cb6613ddd429ca21c7))
* **selection:** add inference-first adaptation and review updates ([5f32389](https://github.com/jsmithpkp21/resume-builder/commit/5f3238962ad24f5044bf8a81ad6b6126fe289de9))
* **selection:** add inference-first adaptation design and issue template ([1bc0239](https://github.com/jsmithpkp21/resume-builder/commit/1bc0239c858009dc7f7bd7c4d6ce37e8670de06c))
* **spike:** clarify default output path and --output-dir override in skills measurement docstring ([48cb507](https://github.com/jsmithpkp21/resume-builder/commit/48cb5072b43f9e783ae6ff83e11a7d6b2735f61e))

## [0.8.1](https://github.com/jsmithpkp21/resume-builder/compare/v0.8.0...v0.8.1) (2026-04-12)


### Bug Fixes

* **skills:** resolve PR [#82](https://github.com/jsmithpkp21/resume-builder/issues/82) follow-up review comments ([1dc0cb0](https://github.com/jsmithpkp21/resume-builder/commit/1dc0cb0eeb17d169004b44b074d51c626dbccbe4))
* **skills:** resolve PR [#82](https://github.com/jsmithpkp21/resume-builder/issues/82) review comments ([261845b](https://github.com/jsmithpkp21/resume-builder/commit/261845b9f52f936f710e22ba752d194ed46c3b19))

## [0.8.0](https://github.com/jsmithpkp21/resume-builder/compare/v0.7.3...v0.8.0) (2026-04-12)


### Features

* **font:** add RESUME_FONT_STRICT env var and --strict-font CLI flag ([1cda260](https://github.com/jsmithpkp21/resume-builder/commit/1cda260296ff2ba69b4bb29995a98d586538276f)), closes [#45](https://github.com/jsmithpkp21/resume-builder/issues/45)


### Bug Fixes

* **font:** enforce Calibri in strict mode for explicit paths ([4b9a981](https://github.com/jsmithpkp21/resume-builder/commit/4b9a9811ddb68dbc74fb41485164f22dd950eb94))


### Documentation

* **font:** align strict precedence and sensitivity wording ([0976f92](https://github.com/jsmithpkp21/resume-builder/commit/0976f92cc14cd071201411a4b2bfa56d59a3a142))

## [0.7.3](https://github.com/jsmithpkp21/resume-builder/compare/v0.7.2...v0.7.3) (2026-04-12)


### Bug Fixes

* **skills:** remove redundant industry hint normalization ([02e5e40](https://github.com/jsmithpkp21/resume-builder/commit/02e5e4059bb510df5c14f135ba09b1aa2707f26f))
* **skills:** resolve PR [#78](https://github.com/jsmithpkp21/resume-builder/issues/78) review comments ([d66ce0e](https://github.com/jsmithpkp21/resume-builder/commit/d66ce0e024846fbafb1657c1609ca7b37e921849))

## [0.7.2](https://github.com/jsmithpkp21/resume-builder/compare/v0.7.1...v0.7.2) (2026-04-12)


### Features

* **skills:** add hybrid industry relevance signal to category ranking (Issue [#48](https://github.com/jsmithpkp21/resume-builder/issues/48))


### Documentation

* **qa:** add pre-submit QA checklist for issue [#63](https://github.com/jsmithpkp21/resume-builder/issues/63) ([0ae934b](https://github.com/jsmithpkp21/resume-builder/commit/0ae934b5d69666539b3aeb079972ef15e214dc5d))
* **qa:** address PR [#76](https://github.com/jsmithpkp21/resume-builder/issues/76) wording review notes ([ee9f6ad](https://github.com/jsmithpkp21/resume-builder/commit/ee9f6adb6a1d688a4de19e36d1df144323c2d42e))
* **qa:** clarify canonical experience_db path ([0056f21](https://github.com/jsmithpkp21/resume-builder/commit/0056f212d2b552b7a69cd4cb6613ddd429ca21c7))

## [0.7.1](https://github.com/jsmithpkp21/resume-builder/compare/v0.7.0...v0.7.1) (2026-04-12)


### Bug Fixes

* **skills:** order categories by role relevance ([49f1af1](https://github.com/jsmithpkp21/resume-builder/commit/49f1af1e770cdc78af87fb595de3e7ca90fe1cbf))


### Documentation

* **guidance:** add application guidance checklist for issue 61 ([b113ac4](https://github.com/jsmithpkp21/resume-builder/commit/b113ac4e160ed8620c7bc3f6a99cd52a74dfee28)), closes [#61](https://github.com/jsmithpkp21/resume-builder/issues/61)
* **guidance:** resolve PR 74 review feedback ([f816374](https://github.com/jsmithpkp21/resume-builder/commit/f816374070d7b9e4f8616c8a5cff3e95db433a2b))

## [0.7.0](https://github.com/jsmithpkp21/resume-builder/compare/v0.6.0...v0.7.0) (2026-04-12)


### Features

* **resume:** improve processed summary readability ([d34ecd6](https://github.com/jsmithpkp21/resume-builder/commit/d34ecd64c1385c9c941923f7506cfdfa6616673c))


### Bug Fixes

* **resume:** address summary review follow-ups ([092d5a7](https://github.com/jsmithpkp21/resume-builder/commit/092d5a777d6adc23b9a1895c4ff7925de66118d7))

## [0.6.0](https://github.com/jsmithpkp21/resume-builder/compare/v0.5.3...v0.6.0) (2026-04-11)


### Features

* **resume:** add source-backed SDET bullets and data-driven summaries ([47b64f2](https://github.com/jsmithpkp21/resume-builder/commit/47b64f282fc9e875eb0a5c002177e2e755bef8ce))


### Bug Fixes

* **summary:** address PR review findings on role summaries ([1990ec9](https://github.com/jsmithpkp21/resume-builder/commit/1990ec920e68f72b30c85baa8a0fad0adc0429fb))

## [0.5.3](https://github.com/jsmithpkp21/resume-builder/compare/v0.5.2...v0.5.3) (2026-04-11)


### Bug Fixes

* **scope:** align ownership wording with actual authority ([a4d9f94](https://github.com/jsmithpkp21/resume-builder/commit/a4d9f94ba00bbcce66ce06b57c88247e26406f19))

## [0.5.2](https://github.com/jsmithpkp21/resume-builder/compare/v0.5.1...v0.5.2) (2026-04-11)


### Bug Fixes

* **skills:** deduplicate category entries and enforce casing ([2986ddb](https://github.com/jsmithpkp21/resume-builder/commit/2986ddb2a159702d6d8bbf776496841247bc4347))
* **test:** tighten skills duplicate contract assertions ([cad2f71](https://github.com/jsmithpkp21/resume-builder/commit/cad2f713f0516273aa4b8e4dfd31c088bd5d960b))

## [0.5.1](https://github.com/jsmithpkp21/resume-builder/compare/v0.5.0...v0.5.1) (2026-04-11)


### Bug Fixes

* **summary:** address review feedback and restore check ([3927da5](https://github.com/jsmithpkp21/resume-builder/commit/3927da5d607e56f2f377ff8b7cccb3e793ee67ad))
* **summary:** prevent fragmented role summary output ([df0419f](https://github.com/jsmithpkp21/resume-builder/commit/df0419f2bb6fbb162a847f825367442d1b034cf0))
* **test:** assert non-empty summary in fragment regression ([620e2f3](https://github.com/jsmithpkp21/resume-builder/commit/620e2f39e522a2bfeb250698a953e9ea02b7d514))

## [0.5.0](https://github.com/jsmithpkp21/resume-builder/compare/v0.4.0...v0.5.0) (2026-04-11)


### Features

* **resume:** add company output aliases and sandbox-first run guidance ([#55](https://github.com/jsmithpkp21/resume-builder/issues/55)) ([4f2f293](https://github.com/jsmithpkp21/resume-builder/commit/4f2f293833774b5985d905c663d7632d37b74a24))

## [0.4.0](https://github.com/jsmithpkp21/resume-builder/compare/v0.3.1...v0.4.0) (2026-04-11)


### Features

* **resume:** calibrate profile summary word cap from sandbox resumes ([#53](https://github.com/jsmithpkp21/resume-builder/issues/53)) ([ec1f441](https://github.com/jsmithpkp21/resume-builder/commit/ec1f4413698a72119dd16b4cd0b74b4e0e2d4147))

## [0.3.1](https://github.com/jsmithpkp21/resume-builder/compare/v0.3.0...v0.3.1) (2026-04-10)


### Bug Fixes

* **templates:** remove dead .headline CSS from ModernTemplate ([874ea44](https://github.com/jsmithpkp21/resume-builder/commit/874ea448f816c041bd53e858e9b420ec44e5a38b))
* **templates:** update name to Jonathan J Smith and modernize layout ([930931b](https://github.com/jsmithpkp21/resume-builder/commit/930931b4469bf0b840bbf1a66b3f83be78999181))
* **templates:** wrap contact lines in .contact div in both templates ([3e7039f](https://github.com/jsmithpkp21/resume-builder/commit/3e7039f05ba4ee6f0e30b0327b553d96c9ba044c))

## [0.3.0](https://github.com/jsmithpkp21/resume-builder/compare/v0.2.0...v0.3.0) (2026-04-09)


### Features

* **resume:** pack skills into unified categories and standardize output filenames ([989d041](https://github.com/jsmithpkp21/resume-builder/commit/989d041063a737340a19136e24aca7b9f60ea202))
* **resume:** refine experience layout and headers ([0e6309f](https://github.com/jsmithpkp21/resume-builder/commit/0e6309f5092cad965541d4268d4154208ef30b5a))
* **resume:** unify template contract and add generated resume title ([9b3d085](https://github.com/jsmithpkp21/resume-builder/commit/9b3d08503c60dfea675cb412ea22c13416883869))
* **resume:** unify template section contract and add generated title block ([36deca6](https://github.com/jsmithpkp21/resume-builder/commit/36deca6084dd8ccf79cd49a2d14d8551b8c6df6b))
* **skills:** implement deterministic 11-13 line skills packing ([#42](https://github.com/jsmithpkp21/resume-builder/issues/42)) ([8478e99](https://github.com/jsmithpkp21/resume-builder/commit/8478e99b3c64645d70738ba08e4456b027b1910b))
* **skills:** prioritize category reduction in packing ([01d6d18](https://github.com/jsmithpkp21/resume-builder/commit/01d6d18a1c77d1f91fe8523e5419671a9b706640))


### Bug Fixes

* **cli:** clarify secondary template help and harden related_skills contract test ([14644f2](https://github.com/jsmithpkp21/resume-builder/commit/14644f25d57999d18c7b9677802b5d0fcddef50f))
* **render:** tighten skills category spacing in HTML output ([#42](https://github.com/jsmithpkp21/resume-builder/issues/42)) ([26cd794](https://github.com/jsmithpkp21/resume-builder/commit/26cd7945827e7cbb30dd967ec92c11b04eb70793))
* **render:** tighten skills category spacing in HTML output ([#42](https://github.com/jsmithpkp21/resume-builder/issues/42)) ([6d7be66](https://github.com/jsmithpkp21/resume-builder/commit/6d7be66186bd51c903d925d4c1aece8bae5aee51))
* **review:** address pr 49 follow-up comments ([b3f6080](https://github.com/jsmithpkp21/resume-builder/commit/b3f6080336fb487f66e6cba5312bc579dc16ce5c))
* **review:** address remaining pr 49 comments ([852fcdd](https://github.com/jsmithpkp21/resume-builder/commit/852fcdd4a5714d49366cec2a8a63ab71c25f525b))
* **review:** align template docs and output naming ([477b7a7](https://github.com/jsmithpkp21/resume-builder/commit/477b7a7bd17861c9453e3361eefceef7fa0f65e8))
* **review:** sync baseline output docs and artifacts ([9e2143b](https://github.com/jsmithpkp21/resume-builder/commit/9e2143b768c4d50cd65b2905ec51daf75a029ed9))
* **skills:** address review feedback ([cbc2182](https://github.com/jsmithpkp21/resume-builder/commit/cbc2182fce04a1236360247d8f305546861cf297))

## [0.2.0](https://github.com/jsmithpkp21/resume-builder/compare/v0.1.0...v0.2.0) (2026-04-07)


### Features

* **data:** add starter data layout for ai inputs ([288d291](https://github.com/jsmithpkp21/resume-builder/commit/288d2915526ddc478cb09f09c5761adece44e9c6)), closes [#7](https://github.com/jsmithpkp21/resume-builder/issues/7)
* **data:** define skill-category contract and seed master experience data ([f2b4322](https://github.com/jsmithpkp21/resume-builder/commit/f2b4322322571d8091cd9f5f7b30a809bc4c470b))
* **data:** establish starter data layout for AI resume inputs ([d2b0681](https://github.com/jsmithpkp21/resume-builder/commit/d2b0681d0d3e2475eb65d7d72818c201db119e7c))
* **data:** reconcile resume experience inventory ([924ccb8](https://github.com/jsmithpkp21/resume-builder/commit/924ccb839be0e70697fe6f516f01da6168dd3266))
* **output:** add baseline resume generation pipeline ([#34](https://github.com/jsmithpkp21/resume-builder/issues/34)) ([35d69ed](https://github.com/jsmithpkp21/resume-builder/commit/35d69ed2417f7a2d5e8910d5635fc4870f9af674))
* **output:** add dynamic headline and profile bottom sections ([#34](https://github.com/jsmithpkp21/resume-builder/issues/34)) ([2e180c8](https://github.com/jsmithpkp21/resume-builder/commit/2e180c8997dc086a603d81392e0d989f66191b9e))
* **output:** auto-build social URLs from handles ([#34](https://github.com/jsmithpkp21/resume-builder/issues/34)) ([339c1f1](https://github.com/jsmithpkp21/resume-builder/commit/339c1f1b5043a7d8c73c4dc1ec682a3196609ea6))
* **output:** dynamic headline and bottom profile sections ([0186571](https://github.com/jsmithpkp21/resume-builder/commit/0186571595e8bbb7686c15a73d03763e35b67756))
* **output:** dynamic headline and bottom profile sections ([57ba628](https://github.com/jsmithpkp21/resume-builder/commit/57ba628dde307a7aa27a2432a2e6d56c3f5e6209))
* **output:** ingest job URL with deterministic company context ([#34](https://github.com/jsmithpkp21/resume-builder/issues/34)) ([e29e677](https://github.com/jsmithpkp21/resume-builder/commit/e29e677b5383a60fec6438fe23e1598134ae6435))
* **resume:** add diff-friendly text snapshot artifact ([c21ae47](https://github.com/jsmithpkp21/resume-builder/commit/c21ae472e69daaa8499395f09b5ef1a791037094))
* **resume:** implement enrich and rule-based trimming ([9d409e2](https://github.com/jsmithpkp21/resume-builder/commit/9d409e2f30c9907c412f98aade96f32018bc61f3))
* **resume:** issue [#39](https://github.com/jsmithpkp21/resume-builder/issues/39) umbrella - LLM-driven resume adaptation ([b6d918f](https://github.com/jsmithpkp21/resume-builder/commit/b6d918f58727e6f675af0b02dbc183e4684beaf2))
* **resume:** raise total bullet cap to 20 ([181ae25](https://github.com/jsmithpkp21/resume-builder/commit/181ae256cf06106e32cbb83d8d3c8fa8e544e5f3))
* **resume:** support job text file and company-site URL fallback ([d9e8fd2](https://github.com/jsmithpkp21/resume-builder/commit/d9e8fd207791bf8f1f7930004b277edcba2a7416))
* **scripts:** enforce canonical-only runtime inputs ([#20](https://github.com/jsmithpkp21/resume-builder/issues/20)) ([03ad6b9](https://github.com/jsmithpkp21/resume-builder/commit/03ad6b9853fc19c41a0c4767fbdc2af53203ef22))
* **scripts:** enforce canonical-only runtime inputs ([#20](https://github.com/jsmithpkp21/resume-builder/issues/20)) ([210a67e](https://github.com/jsmithpkp21/resume-builder/commit/210a67ebd23a87fe57d2973754e9cbaa9d68c1a3))
* **spike:** add report artifact and tests for skills line measurement ([8e6995b](https://github.com/jsmithpkp21/resume-builder/commit/8e6995b0f7dcf80a3c1c2e853f4fedcef1a968a2))
* **spike:** start pdf-first skills line measurement loop for wrap-aware packing ([2790213](https://github.com/jsmithpkp21/resume-builder/commit/2790213200449102f92db08b17bd60248f99139d))
* **transform:** add rewrite guardrails for tone drift ([34d9aee](https://github.com/jsmithpkp21/resume-builder/commit/34d9aee343e07bea8458c6d47f460b8ce900fd75))
* **trim:** log score maps before bullet ranking ([40254b8](https://github.com/jsmithpkp21/resume-builder/commit/40254b8f94ba345f970b0bec1028833b9f75f26e))


### Bug Fixes

* **artifact:** align baseline JSON target_lines_max to 12 per DESIGN.md ([d995ff2](https://github.com/jsmithpkp21/resume-builder/commit/d995ff2db20f9b55be1e9bc513dddb4ebca7dbc8))
* **data:** add debugging time reduction to audio error-handling bullet ([f35fa12](https://github.com/jsmithpkp21/resume-builder/commit/f35fa123fa7773c027f2455cb8a45ee067b306c4))
* **data:** clarify Android-based embedded UI testing in b01 bullet ([610a78f](https://github.com/jsmithpkp21/resume-builder/commit/610a78f801a20d9d4fe2b1499a1a3f80a5b98140))
* **data:** combine headset lab action and quantified outcome ([71ff2cb](https://github.com/jsmithpkp21/resume-builder/commit/71ff2cbd24e0b1ae283ef869186762f8332e6213))
* **data:** commit experience_db and reviewer_notes changes from WS:13 session ([083db9d](https://github.com/jsmithpkp21/resume-builder/commit/083db9d2cba22db45df6fe6a338d6dd79d17787b))
* **data:** move remote logging bullet to correct 2008-2015 role ([1c7da96](https://github.com/jsmithpkp21/resume-builder/commit/1c7da968a6c07dd5887df2477ac7529ffb3bdace))
* **data:** resolve AMD WS:13 CT_SCOPE conflict for Lead Framework Designer role ([85f97ff](https://github.com/jsmithpkp21/resume-builder/commit/85f97ff87163c8706fea2b8713656bf4e3cd4af6))
* **data:** resolve type hints in experience validation script ([80fda09](https://github.com/jsmithpkp21/resume-builder/commit/80fda097b62caf135fa6db4dc76a2ca9f96efc80))
* **data:** split reviewer notes into valid CSV rows ([968b526](https://github.com/jsmithpkp21/resume-builder/commit/968b526f678bddcd4118790cadd6ef3fd2481d86))
* **data:** tighten quantified bullet wording in experience db ([470f860](https://github.com/jsmithpkp21/resume-builder/commit/470f8602500cf38ce40d6b7b2847307a99e274b6))
* **e2e:** make fixture harness portable and deterministic ([a9261f8](https://github.com/jsmithpkp21/resume-builder/commit/a9261f821fb32ef9b24ec12aeadef17eba499b93))
* **pipeline:** f-string placeholders, NaN/inf guard, and live-mode cache path ([841f724](https://github.com/jsmithpkp21/resume-builder/commit/841f7241f969e621ac1b1a92d0cbc667a42ccdfe))
* regenerate pyproject.toml and remove create_issues.sh ([0b58d74](https://github.com/jsmithpkp21/resume-builder/commit/0b58d7486fe5c6492c1f1ee7786058c8d06612a9))
* **resume:** address PR [#40](https://github.com/jsmithpkp21/resume-builder/issues/40) review comments ([fca79e5](https://github.com/jsmithpkp21/resume-builder/commit/fca79e5c3b9b3a6ab3739901a31b0ada1ab8ea33))
* **resume:** harden input validation and review workflow policy ([e59a784](https://github.com/jsmithpkp21/resume-builder/commit/e59a784d88fa68a1de0941b9bd0ccdd2121eb347))
* **resume:** make job-url tests offline and harden ingest ([6a90a6e](https://github.com/jsmithpkp21/resume-builder/commit/6a90a6ee7f19110d6501c5d5801a00ccea46f1f5))
* **resume:** raise min bullets to 3 and fix trim ordering ([8839c82](https://github.com/jsmithpkp21/resume-builder/commit/8839c826d378d3f7ca3961cb69ac9cd38b8a8140))
* **resume:** resolve remaining PR [#35](https://github.com/jsmithpkp21/resume-builder/issues/35) review threads ([7954f48](https://github.com/jsmithpkp21/resume-builder/commit/7954f483069ae314a98d5b80b470892f6102e5a1))
* **review:** resolve AMD architect scope conflict with source-faithful split ([db58c18](https://github.com/jsmithpkp21/resume-builder/commit/db58c18067a1506e1091b44392da954da24deda2))
* **scripts:** align [#20](https://github.com/jsmithpkp21/resume-builder/issues/20) tests/messages with PR [#33](https://github.com/jsmithpkp21/resume-builder/issues/33) feedback ([712fd8f](https://github.com/jsmithpkp21/resume-builder/commit/712fd8f09d3a2b89acc264fc9c59c54d21fb334c))
* **scripts:** avoid sys.path mutation for shared runtime guard imports ([abb10d8](https://github.com/jsmithpkp21/resume-builder/commit/abb10d885c4c24aab0171b7084b4fb6ad6928df4))
* **scripts:** read skills matrix csv with utf-8 newline handling ([83cdd48](https://github.com/jsmithpkp21/resume-builder/commit/83cdd486d707eadffc851d10137b69824f58710d))
* **scripts:** resolve remaining PR [#33](https://github.com/jsmithpkp21/resume-builder/issues/33) review comments ([10af5ee](https://github.com/jsmithpkp21/resume-builder/commit/10af5eeab4f505f6395f64e1313b3e57b176b581))
* **security:** close remaining PR [#35](https://github.com/jsmithpkp21/resume-builder/issues/35) review threads ([d1ada9f](https://github.com/jsmithpkp21/resume-builder/commit/d1ada9ff376ece9df5713a6a766b089ce9cb6d82))
* **security:** harden job-url metadata fetch guards ([01691bd](https://github.com/jsmithpkp21/resume-builder/commit/01691bd93c19215f8b2288804464bd480d047d57))
* **security:** harden URL validation and social slug normalization ([016d9b4](https://github.com/jsmithpkp21/resume-builder/commit/016d9b483f7fa75ea2d5be540b9e86fe9aac8195))
* **skills:** make wrap triggers actionable and harden prefix-kern test ([a99f371](https://github.com/jsmithpkp21/resume-builder/commit/a99f3711421c654c145f9ee3cbb3f7a5be1c5627))
* **spike:** address PR [#44](https://github.com/jsmithpkp21/resume-builder/issues/44) review findings for skills measurement ([e8c0f39](https://github.com/jsmithpkp21/resume-builder/commit/e8c0f39418112384d17fc32557e282cf51348e8c))
* **spike:** address remaining kerning wrap review findings ([7f3ef7a](https://github.com/jsmithpkp21/resume-builder/commit/7f3ef7a725a4d21e50b82734646266c6edac049c))
* **spike:** align budget and font labeling with review feedback ([8bcd15f](https://github.com/jsmithpkp21/resume-builder/commit/8bcd15fc11cdc5a0d7292e427f3e5b8eed6e0f98))
* **spike:** align skills spike docs and artifact schema ([8f61b64](https://github.com/jsmithpkp21/resume-builder/commit/8f61b64ca29c303c9026133a88eb64eea592d498))
* **spike:** avoid applying Regular kern table to bold prefix widths ([083a2c0](https://github.com/jsmithpkp21/resume-builder/commit/083a2c013c00aba86770afc717bb37edf6eb7787))
* **spike:** gate --kern on Calibri and align test kern loading ([ec7d607](https://github.com/jsmithpkp21/resume-builder/commit/ec7d60747ee2735e13b17f311d36db09aa754a0d))
* **spike:** harden font fallback loading and clarify kerning docs ([52bfea5](https://github.com/jsmithpkp21/resume-builder/commit/52bfea5da850a9ef0d5dcceea753931d02d1ac37))
* **spike:** temporarily allow fallback fonts for CI stability ([e7eed0a](https://github.com/jsmithpkp21/resume-builder/commit/e7eed0a488c317a867c14edc3c2fe2e74db85346))
* **test:** add deterministic prefix-kern boundary guard ([115607f](https://github.com/jsmithpkp21/resume-builder/commit/115607fb0de90cf1493a8ec310e464685586694e))
* **test:** close final review items for kerning wrap behavior ([c18eb66](https://github.com/jsmithpkp21/resume-builder/commit/c18eb66129df57d5300aa0643831b2767b2e95e4))
* **test:** make sensitivity test font-agnostic for CI fallback fonts ([2565d90](https://github.com/jsmithpkp21/resume-builder/commit/2565d904ae08830086505cc9e362361de52624e9))
* **test:** remove always-true kern assertion in prefix guard ([c311778](https://github.com/jsmithpkp21/resume-builder/commit/c31177842bd41a405ab41973bf36bad5a389bf24))
* **test:** stabilize width boundary check and drop redundant import ([ef20ba5](https://github.com/jsmithpkp21/resume-builder/commit/ef20ba5dc4a1777604afb1a38c81bfad5e76fc95))
* **test:** use token-summing for removing-skill width boundary ([ffe0fbf](https://github.com/jsmithpkp21/resume-builder/commit/ffe0fbf5d4a8db2ae0467d19e5ad14586fde6988))
* **typing:** address strict narrowing and redirect override compatibility ([6e24fbf](https://github.com/jsmithpkp21/resume-builder/commit/6e24fbf1ebda41243b351b42c238e86c2f03bfe0))


### Documentation

* **agent:** codify PR-thread response boundaries ([1645867](https://github.com/jsmithpkp21/resume-builder/commit/1645867e3ae41282ffd40420288c76fe1219d15c))
* **agents:** add WSL path handling rules to prevent UNC path write failures ([065e23e](https://github.com/jsmithpkp21/resume-builder/commit/065e23ec145fea665fdfc361165e19870827c081))
* **design:** add final-pass action word diversity rule ([fd626ab](https://github.com/jsmithpkp21/resume-builder/commit/fd626ab9013d3fdcc9482a486e6f28ea62782be3))
* **design:** add inference-first adaptation policy and remove role_audience field ([14eb168](https://github.com/jsmithpkp21/resume-builder/commit/14eb168e5e0b086e3c6f95ddd7a7970bc170d9df))
* **design:** add skill/category detection design and update improvements backlog ([449b216](https://github.com/jsmithpkp21/resume-builder/commit/449b216b9fedc281ec33dce4324e74bb62602583))
* **design:** clarify future layout overflow pass ([32bc2f9](https://github.com/jsmithpkp21/resume-builder/commit/32bc2f9a1f405b9e315e3a0911ddc840c6924bc2))
* initial design ([d5edd10](https://github.com/jsmithpkp21/resume-builder/commit/d5edd10dd512bb84682a348190f6d232a844f3fb))
* **process:** capture workflow decisions and issue backlog ([1f14666](https://github.com/jsmithpkp21/resume-builder/commit/1f1466636b3a0e3108ab930c5dbc46e218ff29c4))
* **selection:** add inference-first adaptation and review updates ([5f32389](https://github.com/jsmithpkp21/resume-builder/commit/5f3238962ad24f5044bf8a81ad6b6126fe289de9))
* **selection:** add inference-first adaptation design and issue template ([1bc0239](https://github.com/jsmithpkp21/resume-builder/commit/1bc0239c858009dc7f7bd7c4d6ce37e8670de06c))
* **spike:** clarify default output path and --output-dir override in skills measurement docstring ([48cb507](https://github.com/jsmithpkp21/resume-builder/commit/48cb5072b43f9e783ae6ff83e11a7d6b2735f61e))
