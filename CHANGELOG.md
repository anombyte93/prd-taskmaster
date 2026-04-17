# Changelog

## [4.1.0](https://github.com/anombyte93/prd-taskmaster/compare/v4.0.0...v4.1.0) (2026-04-17)


### Features

* **calc-tasks:** context-aware task count formula (team, scope, themes) ([bb269b5](https://github.com/anombyte93/prd-taskmaster/commit/bb269b5e3cf31b834a8229fca9033a3c697d142f))
* close ship-blockers [#4](https://github.com/anombyte93/prd-taskmaster/issues/4) (preflight state) and [#20](https://github.com/anombyte93/prd-taskmaster/issues/20) (uninstall.sh) ([cb4053d](https://github.com/anombyte93/prd-taskmaster/commit/cb4053d72325dcbafaf1caebd67ba232b9274a76))
* **debrief:** scaffold dogfood debriefs from deterministic artifacts ([f4b8896](https://github.com/anombyte93/prd-taskmaster/commit/f4b889636191afe86e180f8dabdaff337bef64cc))
* **orchestrator:** forge Atticus — first bearer of orchestrator soul template ([28ed75b](https://github.com/anombyte93/prd-taskmaster/commit/28ed75b90b4e119289317f4aaed86850ba2d676d))


### Bug Fixes

* **generate:** use task-master expand --all to avoid parallel write race ([332c147](https://github.com/anombyte93/prd-taskmaster/commit/332c14761769708010b5d450576ac2cc6abd72c9))
* **handoff:** enforce EnterPlanMode + AskUserQuestion dual-call, gate Atlas-Auto as coming-soon ([a0a3c28](https://github.com/anombyte93/prd-taskmaster/commit/a0a3c28235bae0694d8905a2969e5b929f1d5cab))
* **handoff:** safe-append CLAUDE.md via new subcommand (ship-blocker [#15](https://github.com/anombyte93/prd-taskmaster/issues/15)) ([f97e714](https://github.com/anombyte93/prd-taskmaster/commit/f97e714b2cd58a12001474b01a597e55ab0479e6))
* **setup:** detect existing provider config before mutating ([2271d55](https://github.com/anombyte93/prd-taskmaster/commit/2271d554dfd29b7bdadea3f794cd25c3d6aa18aa))
* **tests:** align gen-test-tasks assertions with v4.1 calc-tasks floor ([bf191d9](https://github.com/anombyte93/prd-taskmaster/commit/bf191d98e134c0c8464b74d7793c20ff01d0c193))


### Documentation

* add missing dogfood debrief for 2026-04-13 atlas-shade run ([5ea1354](https://github.com/anombyte93/prd-taskmaster/commit/5ea1354bb2e0f8582b8fce0cf548a85695ce4178))
* **atticus:** expand soul lineage section — forging conversation + transcript pointer ([ae392c4](https://github.com/anombyte93/prd-taskmaster/commit/ae392c471e92e9b4324f60c89b1171ca0431eb45))
* **CLAUDE.md:** refresh architecture notes and remove drift ([851a8c1](https://github.com/anombyte93/prd-taskmaster/commit/851a8c1b247fef97f8aa8ecaa98083103e4c365f))
* clean up and reorganize documentation ([b950d70](https://github.com/anombyte93/prd-taskmaster/commit/b950d709eb4ddfeb91c79f27274a00adf092b4ce))
* focused re-audit of ship-blockers [#1](https://github.com/anombyte93/prd-taskmaster/issues/1)-10 with execution evidence ([a0edff8](https://github.com/anombyte93/prd-taskmaster/commit/a0edff81ae326592d8af8a62a692a94336439480))
* **handoff:** auto-scaffold dogfood debrief as final HANDOFF step ([870dbc0](https://github.com/anombyte93/prd-taskmaster/commit/870dbc024a4c0e5a05b39d6d899631bba8b6201d))
* pin atlas-ralph-loop (patched fork) as canonical over base ralph-loop ([cb3f13e](https://github.com/anombyte93/prd-taskmaster/commit/cb3f13e9576a9b7695f8cbe69dcdb6871f265680))
* plugin design spec + implementation plan + Post-Audit §14b revisions ([c9d3e23](https://github.com/anombyte93/prd-taskmaster/commit/c9d3e239b929ad2aed6bf3ed946d876e3aad43c8))


### Miscellaneous Chores

* add release-please versioning for v4.1 cadence ([712f616](https://github.com/anombyte93/prd-taskmaster/commit/712f61640cd077249c5513a1efa3ae11bf84a18d))
