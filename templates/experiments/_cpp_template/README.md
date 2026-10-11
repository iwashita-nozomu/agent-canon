# <topic>

This is a C++-first experiment topic. The native executable owns the numerical
and data-processing implementation. `run.py` only launches that executable and
copies its standard output into the managed run's raw directory. It does not
build the executable or provide a Python calculation fallback.

The generated registry entry remains `draft`. `topic.cpp` defines the process
boundary and request/result types. The consumer supplies the definition of
`experiment::run(const experiment::Request&)` in that file; the selected CMake
target already includes it. That function owns native data decoding and experiment logic. The
linker requires this consumer definition, so package creation does not claim a
completed experiment or scientific result. The request contains only the config
path and optional case identity; the consumer owns config and result formats.

The selected CMake profile is `<cmake-profile>`:

- `consumer-local` generates this topic's `CMakeLists.txt` for the consumer's
  existing individual-manifest build route.
- `root-aggregate` generates `cmake-registration.cmake`, which the project
  CMake owner may include from the existing root manifest. The topic does not
  become a second project entrypoint.

Set `EXPERIMENT_EXECUTABLE` to the built target path, then run this topic through
the consumer's existing run command with `config.yaml`. The selected CMake owner
chooses the configure and build commands and binary directory.

The fixed single-case profile does not generate `cases.py`. Select
`--multi-case` only when this topic has real case inputs; that option adds a
case-input adapter that validates a non-empty `cases` list in `config.yaml` and
passes each case identity and the config path to the same native executable,
which owns case decoding and computation. It does not
provide a Python calculation worker or an example case.

`visualization.py` reads the raw native output files and can render them as a
static HTML file after a run. It does not launch the executable or select
configuration.
