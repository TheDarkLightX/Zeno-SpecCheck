# Tau runtime used for the pilot

Tau is an optional external dependency. No source, wheel, or binary is distributed here. Consult [its license](https://github.com/IDNI/tau-lang/blob/31b5b3cfa546d1769cb27c882f131a2914452b55/LICENSE.md) before installation or redistribution.

## Exact observed environment

- Tau commit: `31b5b3cfa546d1769cb27c882f131a2914452b55`.
- Parser submodule: `8bd7388388435a7d7093af021edd678b76f615e4`.
- Both source trees were clean after building.
- Module SHA-256: `0da401031b9e39b1d6553aa38941b3be2ef70215998a0f978db451755589a32b`.
- Python 3.12.14; nanobind 3.0.1; CMake 4.4.3; Ninja 1.13.2; GCC 13.3.0.
- Ubuntu shared Boost 1.83.0, installed with `libboost-log-dev`.
- Pack: `sbf,tau`. No cvc5/bitvectors; no Spot `ltlsynt`.

The optional live tests in this repository passed against that runtime. Eight initial upstream-API probes also passed. The **full upstream Tau suite was not passed**: its decision test stopped on a Spot-dependent formula with explicit UNKNOWN. Tests in this repository do not constitute an audit of Tau.

## Reproducing the local build

These instructions describe the actual pilot build, including external CMake workarounds needed by this exact revision. They are not a general upstream installation guarantee. Run from a separate clean pinned Tau checkout with the system compiler and shared Boost development libraries available.

```bash
uv venv --python python3.12 /tmp/zeno-tau-runtime
uv pip install --python /tmp/zeno-tau-runtime/bin/python \
  cmake==4.4.3 ninja==1.13.2 nanobind==3.0.1
export PATH="/tmp/zeno-tau-runtime/bin:$PATH"
export TAU_PYTHON=/tmp/zeno-tau-runtime/bin/python
git submodule update --init external/parser
```

From `external/parser`:

```bash
./dev preset release \
  -DCMAKE_C_COMPILER=gcc -DCMAKE_CXX_COMPILER=g++ \
  -DTAU_PARSER_BUILD_TGF=ON -DTAU_PARSER_BUILD_STATIC_LIBRARY=ON \
  -DTAU_PARSER_BUILD_PIC=ON -DTAU_PARSER_LTO=OFF \
  -DTAU_PARSER_BUILD_SERVE=OFF -DTAU_PARSER_DONT_USE_FTXUI=ON \
  -DCMAKE_INSTALL_PREFIX=/tmp/zeno-tau-runtime/parser-sdk \
  -DTAU_BUILD_JOBS=2
cmake --install build/release
```

Create `/tmp/zeno-tau-runtime/import-parser.cmake` with:

```cmake
if(CMAKE_PROJECT_NAME STREQUAL "tau")
  set(Boost_USE_STATIC_LIBS OFF)
  find_package(Boost REQUIRED CONFIG COMPONENTS log)
  find_package(tauparser CONFIG REQUIRED
    PATHS "/tmp/zeno-tau-runtime/parser-sdk/cmake" NO_DEFAULT_PATH)
  if(NOT TARGET tauparser)
    add_library(tauparser ALIAS idni::tauparser_static)
  endif()
  cmake_language(DEFER CALL target_compile_definitions
    tau_nanobind PRIVATE TAU_PARSER_DEFS_INSTALLED)
endif()
```

From the Tau root:

```bash
./dev preset release-binding-python \
  -DTAU_BAS=sbf,tau -DTAU_DEPS_FROM_STORE=OFF \
  -DCMAKE_C_COMPILER=gcc -DCMAKE_CXX_COMPILER=g++ \
  -DTAU_LTO=OFF -DTAU_ARTIFACT_PREINST=OFF \
  -DTAU_DONT_USE_FTXUI=ON -DTAU_PARSER_DONT_USE_FTXUI=ON \
  -DTAU_BUILD_JOBS=1 \
  -DTAU_TGF_PACKAGE_PREFIX=/tmp/zeno-tau-runtime/parser-sdk \
  -DCMAKE_PROJECT_INCLUDE=/tmp/zeno-tau-runtime/import-parser.cmake \
  --target tau_nanobind
```

Point `--tau-module-dir` at the resulting `build/release/bindings/python/nanobind`. Keep the explicit flags on subsequent preset invocations because preset defaults can replace cached selections.

## Observed limits

Native Tau emits some buffered diagnostics to stdout as well as stderr. The Zeno worker writes structured results to a separate temporary file, records bounded logs, and checks the worker's return code.

The formula `(o1[t]:sbf = 0) U (o1[t]:sbf = 1)` produced no realizability verdict in the reduced runtime because `ltlsynt` was absent. The application reported UNKNOWN. A full installation may decide it; the missing-tool result is specific to this build.

For Boolean exports, use `--algebra sbf` with this reduced runtime. The exporter explicitly restricts each declared Boolean stream to the zero/unit values. No equivalence between finite bitvectors and atomless Boolean algebra is assumed.
