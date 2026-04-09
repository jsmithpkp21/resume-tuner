# Changelog

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
