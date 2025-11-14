# Changelog

## [0.7.1](https://github.com/runpod-workers/worker-tetra/compare/v0.7.0...v0.7.1) (2025-11-14)


### Features

* configure release-please to include refactor commits ([#37](https://github.com/runpod-workers/worker-tetra/issues/37)) ([b8c59a0](https://github.com/runpod-workers/worker-tetra/commit/b8c59a0eef5f876a9cbbf524f48f2ce984b2b013))
* **executor:** add async function and method execution support ([#42](https://github.com/runpod-workers/worker-tetra/issues/42)) ([6b19ce6](https://github.com/runpod-workers/worker-tetra/commit/6b19ce678f091979b387657ec657959768861d4c))

## [0.7.0](https://github.com/runpod-workers/worker-tetra/compare/v0.6.0...v0.7.0) (2025-10-10)


### Features

* Endpoint Persistence using Network Volume (phase 1) ([#25](https://github.com/runpod-workers/worker-tetra/issues/25)) ([f59bec2](https://github.com/runpod-workers/worker-tetra/commit/f59bec228a93f075a4009bf0b17a3002d496df6e))
* Endpoint Persistence using Network Volume (phase 2) ([#31](https://github.com/runpod-workers/worker-tetra/issues/31)) ([657e89a](https://github.com/runpod-workers/worker-tetra/commit/657e89a91c9e36432d8720d8464179996b4f1e60))

## [0.6.0](https://github.com/runpod-workers/worker-tetra/compare/v0.5.0...v0.6.0) (2025-09-25)


### Features

* AE-1146 upgrade PyTorch base image to 2.8.0 with CUDA 12.8. ([#28](https://github.com/runpod-workers/worker-tetra/issues/28)) ([32b2561](https://github.com/runpod-workers/worker-tetra/commit/32b256182eccafa526dd8a45d1d3a8b2668dc08b))
* AE-962 streaming logs from remote to local ([#24](https://github.com/runpod-workers/worker-tetra/issues/24)) ([b1c9a47](https://github.com/runpod-workers/worker-tetra/commit/b1c9a4743ebf687559ca6542137913c4926f8ce9))


### Bug Fixes

* access built-in system Python instead of using venv for runtime ([#30](https://github.com/runpod-workers/worker-tetra/issues/30)) ([d11a7fb](https://github.com/runpod-workers/worker-tetra/commit/d11a7fba53d8336dd229b34954ca5cee9ec0ce9b))

## [0.5.0](https://github.com/runpod-workers/worker-tetra/compare/v0.4.1...v0.5.0) (2025-08-27)


### Features

* Add download acceleration for dependencies & hugging face ([#22](https://github.com/runpod-workers/worker-tetra/issues/22)) ([f17e013](https://github.com/runpod-workers/worker-tetra/commit/f17e013263605758f17360abe684fa3de8c2f89e))

## [0.4.1](https://github.com/runpod-workers/worker-tetra/compare/v0.4.0...v0.4.1) (2025-08-06)


### Bug Fixes

* CI-built docker images were broken ([317dc4e](https://github.com/runpod-workers/worker-tetra/commit/317dc4ec505f6e6cd59f61974342471a20b46467))
* last cleanup pr tag from docker did not work ([#19](https://github.com/runpod-workers/worker-tetra/issues/19)) ([d317991](https://github.com/runpod-workers/worker-tetra/commit/d3179910dd9febba149afaae3362011b859ee206))
* PR builds and tests input json files only ([#20](https://github.com/runpod-workers/worker-tetra/issues/20)) ([d6b61d7](https://github.com/runpod-workers/worker-tetra/commit/d6b61d7a0c5bd4da546f37757dec4166679fa631))
* production Docker builds and GPU/CPU tag consistency ([#17](https://github.com/runpod-workers/worker-tetra/issues/17)) ([9d65fde](https://github.com/runpod-workers/worker-tetra/commit/9d65fdeb1d4e373cea009cfe09d7d69d60407497))

## [0.4.0](https://github.com/runpod-workers/worker-tetra/compare/v0.3.1...v0.4.0) (2025-08-05)


### Features

* Workspace environment persisted in the network volume  ([#10](https://github.com/runpod-workers/worker-tetra/issues/10)) ([6675ec1](https://github.com/runpod-workers/worker-tetra/commit/6675ec1c52cc453be450684ce49ba4bea0d8ea2b))

## [0.3.1](https://github.com/runpod-workers/worker-tetra/compare/v0.3.0...v0.3.1) (2025-07-23)


### Bug Fixes

* broken ci ([#13](https://github.com/runpod-workers/worker-tetra/issues/13)) ([b25d822](https://github.com/runpod-workers/worker-tetra/commit/b25d8220ef0389dea6a83fd9a4450be459e79244))

## [0.3.0](https://github.com/runpod-workers/worker-tetra/compare/v0.2.0...v0.3.0) (2025-07-23)


### Features

* AE-835 Add class based execution [Runtime] ([#8](https://github.com/runpod-workers/worker-tetra/issues/8)) ([6d6505e](https://github.com/runpod-workers/worker-tetra/commit/6d6505ebdd749dff45dd52cb18b93da9330fe5ab))
* CI/CD pipeline workflows with testing, linting, valiation and docker builds ([#9](https://github.com/runpod-workers/worker-tetra/issues/9)) ([9d3d696](https://github.com/runpod-workers/worker-tetra/commit/9d3d69698238718ab64675b335630caf3c186526))


### Bug Fixes

* update Dockerfile to reference only existing files ([#12](https://github.com/runpod-workers/worker-tetra/issues/12)) ([93df475](https://github.com/runpod-workers/worker-tetra/commit/93df4756bea1c60adae9063cd2426ea230f3b7d5))

## [0.2.0](https://github.com/runpod-workers/worker-tetra/compare/v0.1.1...v0.2.0) (2025-06-26)


### Features

* AE-518 CPU Live Serverless ([#1](https://github.com/runpod-workers/worker-tetra/issues/1)) ([ddae70b](https://github.com/runpod-workers/worker-tetra/commit/ddae70b52e3ba261d2986e6485df6ec6307db368))


### Bug Fixes

* forgot these ([4048e97](https://github.com/runpod-workers/worker-tetra/commit/4048e977fffe46363cdd9baafaea18188b5d9e6f))
* release-please ([fb10504](https://github.com/runpod-workers/worker-tetra/commit/fb10504670459b272e12f49f8f77df23f3c0e8fe))

## [0.2.0](https://github.com/runpod-workers/worker-tetra/compare/v0.1.0...v0.2.0) (2025-06-26)


### Features

* AE-518 CPU Live Serverless ([#1](https://github.com/runpod-workers/worker-tetra/issues/1)) ([ddae70b](https://github.com/runpod-workers/worker-tetra/commit/ddae70b52e3ba261d2986e6485df6ec6307db368))


### Bug Fixes

* forgot these ([4048e97](https://github.com/runpod-workers/worker-tetra/commit/4048e977fffe46363cdd9baafaea18188b5d9e6f))

## 0.1.0 (2025-06-23)


### Bug Fixes

* forgot these ([4048e97](https://github.com/runpod-workers/worker-tetra/commit/4048e977fffe46363cdd9baafaea18188b5d9e6f))
