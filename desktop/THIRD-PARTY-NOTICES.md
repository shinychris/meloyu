# Third-Party Notices

Meloyu Desktop（© 2026 Meloyu）包含两个随包分发的运行时，其第三方组件许可如下。
本文件由 `npm run notices` 生成（2026-11-01），随安装包分发并位于安装目录 resources/ 下；
完整许可文本见各组件上游仓库（Repository 列）。

## 1. Electron 壳（Node.js 运行时依赖）

Electron/Chromium/Node.js 本体的许可随 Electron 发行版分发
（MIT 及 BSD 风格许可，全文见 electron npm 包内 LICENSE 文件）。

| 组件 | 版本 | 许可 | 上游 |
|---|---|---|---|
| argparse | 2.0.1 | Python-2.0 | https://github.com/nodeca/argparse |
| builder-util-runtime | 9.7.0 | MIT | https://github.com/electron-userland/electron-builder |
| debug | 4.4.3 | MIT | https://github.com/debug-js/debug |
| electron-updater | 6.8.9 | MIT | https://github.com/electron-userland/electron-builder |
| fs-extra | 10.1.0 | MIT | https://github.com/jprichardson/node-fs-extra |
| graceful-fs | 4.2.11 | ISC | https://github.com/isaacs/node-graceful-fs |
| js-yaml | 4.3.2 | MIT | https://github.com/nodeca/js-yaml |
| jsonfile | 6.2.1 | MIT | https://github.com/jprichardson/node-jsonfile |
| lazy-val | 1.0.5 | MIT | https://github.com/develar/lazy-val |
| lodash.escaperegexp | 4.1.2 | MIT | https://github.com/lodash/lodash |
| lodash.isequal | 4.5.0 | MIT | https://github.com/lodash/lodash |
| ms | 2.1.3 | MIT | https://github.com/vercel/ms |
| sax | 1.6.1 | BlueOak-1.0.0 | https://github.com/isaacs/sax-js |
| semver | 7.7.4 | ISC | https://github.com/npm/node-semver |
| tiny-typed-emitter | 2.1.0 | MIT | https://github.com/binier/tiny-typed-emitter |
| universalify | 2.0.1 | MIT | https://github.com/RyanZim/universalify |

## 2. 后端 sidecar（Python 运行时依赖，PyInstaller --onedir 打包）

可选本地组件（按需下载，不随本包分发）：MusicGen 权重（CC-BY-NC 4.0，产出非商用）、
ACE-Step v1.5（MIT，代码与权重）。云通道（OpenAI 兼容 API / Suno 兼容网关 /
Replicate）为用户自有 Key 的外部服务，不在分发范围内。

| 组件 | 版本 | 许可 | 上游 |
|---|---|---|---|
| accelerate | 1.14.0 | Apache Software License | https://github.com/huggingface/accelerate |
| annotated-doc | 0.0.5 | MIT | https://github.com/fastapi/annotated-doc |
| annotated-types | 0.8.0 | MIT | https://github.com/annotated-types/annotated-types |
| anyio | 4.14.2 | MIT | https://anyio.readthedocs.io/en/stable/versionhistory.html |
| bcrypt | 5.0.0 | Apache Software License | https://github.com/pyca/bcrypt/ |
| certifi | 2026.7.22 | Mozilla Public License 2.0 (MPL 2.0) | https://github.com/certifi/python-certifi |
| cffi | 2.1.1 | MIT-0 | https://cffi.readthedocs.io/en/latest/whatsnew.html |
| charset-normalizer | 3.5.1 | MIT | https://github.com/jawah/charset_normalizer/blob/master/CHANGELOG.md |
| click | 8.5.0 | BSD-3-Clause | https://github.com/pallets/click/ |
| colorama | 0.4.6 | BSD License | https://github.com/tartley/colorama |
| cryptography | 50.0.1 | Apache-2.0 OR BSD-3-Clause | https://github.com/pyca/cryptography |
| defusedxml | 0.7.1 | Python Software Foundation License | https://github.com/tiran/defusedxml |
| fastapi | 0.141.1 | MIT | https://github.com/fastapi/fastapi |
| filelock | 3.32.4 | MIT | https://github.com/tox-dev/py-filelock |
| fonttools | 4.63.0 | MIT | http://github.com/fonttools/fonttools |
| fpdf2 | 2.8.8 | LGPL-3.0-only | https://py-pdf.github.io/fpdf2/ |
| fsspec | 2026.7.0 | BSD-3-Clause | https://github.com/fsspec/filesystem_spec |
| greenlet | 3.5.5 | MIT AND PSF-2.0 | https://greenlet.readthedocs.io |
| h11 | 0.16.0 | MIT License | https://github.com/python-hyper/h11 |
| hf-xet | 1.6.0 | Apache-2.0 | https://github.com/huggingface/xet-core |
| httpcore | 1.0.9 | BSD-3-Clause | https://www.encode.io/httpcore/ |
| httptools | 0.8.0 | MIT | https://github.com/MagicStack/httptools |
| httpx | 0.28.1 | BSD License | https://github.com/encode/httpx |
| huggingface_hub | 1.29.0 | Apache Software License | https://github.com/huggingface/huggingface_hub |
| idna | 3.19 | BSD-3-Clause | https://github.com/kjd/idna |
| Jinja2 | 3.1.6 | BSD License | https://github.com/pallets/jinja/ |
| lameenc | 1.8.4 | LGPL-3.0-or-later | https://github.com/chrisstaite/lameenc |
| loguru | 0.7.3 | MIT License | https://github.com/Delgan/loguru |
| markdown-it-py | 4.2.0 | MIT License | https://github.com/executablebooks/markdown-it-py |
| MarkupSafe | 3.0.3 | BSD-3-Clause | https://github.com/pallets/markupsafe/ |
| mdurl | 0.1.2 | MIT License | https://github.com/executablebooks/mdurl |
| mido | 1.3.3 | MIT License | https://github.com/mido/mido |
| mpmath | 1.3.0 | BSD License | http://mpmath.org/ |
| networkx | 3.6.1 | BSD-3-Clause | https://networkx.org/ |
| numpy | 2.5.2 | BSD-3-Clause AND 0BSD AND MIT AND Zlib AND CC0-1.0 | https://numpy.org |
| packaging | 26.3 | Apache-2.0 OR BSD-2-Clause | https://github.com/pypa/packaging |
| psutil | 7.2.2 | BSD-3-Clause | https://github.com/giampaolo/psutil |
| psycopg2-binary | 2.9.13 | GNU Library or Lesser General Public License (LGPL) | https://psycopg.org/ |
| pycparser | 3.0 | BSD-3-Clause | https://github.com/eliben/pycparser |
| pydantic | 2.13.5 | MIT | https://github.com/pydantic/pydantic |
| pydantic_core | 2.46.5 | MIT | https://github.com/pydantic |
| pydantic-settings | 2.15.0 | MIT | https://github.com/pydantic/pydantic-settings |
| Pygments | 2.21.0 | BSD-2-Clause | https://pygments.org |
| pyinstaller-hooks-contrib | 2026.8 | Apache Software License; GNU General Public License v2 (GPLv2) | https://github.com/pyinstaller/pyinstaller-hooks-contrib |
| PyJWT | 2.13.0 | MIT | https://github.com/jpadilla/pyjwt |
| pypinyin | 0.55.0 | MIT License | https://github.com/mozillazg/python-pinyin |
| python-dotenv | 1.2.3 | BSD-3-Clause | https://github.com/theskumar/python-dotenv |
| PyYAML | 6.0.3 | MIT License | https://pyyaml.org/ |
| regex | 2026.8.31 | Apache-2.0 AND CNRI-Python | https://github.com/mrabarnett/mrab-regex |
| requests | 2.34.2 | Apache Software License | https://github.com/psf/requests |
| rich | 15.0.0 | MIT License | https://github.com/Textualize/rich |
| ruff | 0.16.5 | MIT | https://docs.astral.sh/ruff |
| safetensors | 0.8.0 | Apache Software License | https://github.com/huggingface/safetensors |
| sentry-sdk | 2.70.0 | MIT | https://github.com/getsentry/sentry-python |
| shellingham | 1.5.4 | ISC License (ISCL) | https://github.com/sarugaku/shellingham |
| soundfile | 0.14.0 | BSD License | https://github.com/bastibe/python-soundfile |
| SQLAlchemy | 2.0.52 | MIT | https://www.sqlalchemy.org |
| starlette | 1.6.0 | BSD-3-Clause | https://github.com/Kludex/starlette |
| stripe | 15.6.1 | MIT License | https://stripe.com/ |
| sympy | 1.14.0 | BSD License | https://sympy.org |
| tokenizers | 0.23.1 | Apache Software License | https://github.com/huggingface/tokenizers |
| torch | 2.13.0+cu130 | Apache-2.0 AND Apache-2.0 WITH LLVM-exception AND BSD-2-Clause AND BSD-3-Clause AND BSL-1.0 AND MIT | https://pytorch.org |
| tqdm | 4.70.0 | MPL-2.0 AND MIT | https://tqdm.github.io |
| transformers | 5.16.1 | Apache 2.0 License | https://github.com/huggingface/transformers |
| typer | 0.27.2 | MIT | https://github.com/fastapi/typer |
| typing_extensions | 4.16.0 | PSF-2.0 | https://github.com/python/typing_extensions |
| typing-inspection | 0.4.4 | MIT | https://github.com/pydantic/typing-inspection |
| urllib3 | 2.7.0 | MIT | https://github.com/urllib3/urllib3/blob/main/CHANGES.rst |
| uvicorn | 0.52.4 | BSD-3-Clause | https://uvicorn.dev/ |
| watchfiles | 1.2.0 | MIT License | https://github.com/samuelcolvin/watchfiles |
| websockets | 17.1 | BSD-3-Clause | https://github.com/python-websockets/websockets |
| win32_setctime | 1.2.0 | MIT License | https://github.com/Delgan/win32-setctime |

