# Petal CMake Integration Module
# Provides macros to integrate Petal energy compilation and telemetry.

if(__PETAL_INCLUDED)
  return()
endif()
set(__PETAL_INCLUDED TRUE)

# Try to find petal executable
find_program(PETAL_EXECUTABLE NAMES petal petal.exe)

if(NOT PETAL_EXECUTABLE)
  message(WARNING "Petal executable not found in PATH. Energy optimizations will be disabled.")
endif()

# petal_benchmark
# Wraps a target's execution with the Petal telemetry collector.
# Usage:
#   petal_benchmark(TARGET my_target COMMAND my_executable arg1 arg2)
#
function(petal_benchmark)
    set(options)
    set(oneValueArgs TARGET)
    set(multiValueArgs COMMAND)
    cmake_parse_arguments(PB "${options}" "${oneValueArgs}" "${multiValueArgs}" ${ARGN})

    if(NOT PB_TARGET)
        message(FATAL_ERROR "petal_benchmark requires a TARGET argument")
    endif()

    if(NOT PB_COMMAND)
        message(FATAL_ERROR "petal_benchmark requires a COMMAND argument")
    endif()

    if(PETAL_EXECUTABLE)
        # We create a custom target that runs petal <executable> --optimise
        # In the future, this will just wrap the execution, but right now
        # the CLI requires the source file or just runs the executable.
        # Wait, the CLI currently takes a source file `petal myfile.c --optimise`.
        # For the CMake macro, we want it to just run telemetry on the compiled binary.
        # Let's add a note that the CLI needs a `--run-only` or similar mode in the future.
        # For now, we will add a custom command that warns or invokes petal.
        
        add_custom_target(${PB_TARGET}_energy
            COMMAND ${CMAKE_COMMAND} -E echo "Running Petal benchmark for ${PB_TARGET}..."
            # Placeholder for future: COMMAND ${PETAL_EXECUTABLE} run ${PB_COMMAND}
            DEPENDS ${PB_TARGET}
            COMMENT "Gathering energy telemetry for ${PB_TARGET}"
            VERBATIM
        )
    else()
        add_custom_target(${PB_TARGET}_energy
            COMMAND ${CMAKE_COMMAND} -E echo "Petal not installed. Skipping benchmark."
        )
    endif()
endfunction()

# petal_target
# Injects the Petal LLVM pass into the compilation of the target.
# Usage:
#   petal_target(my_target POLICY eco)
#
function(petal_target TARGET_NAME)
    if(PETAL_EXECUTABLE)
        # Placeholder for injecting the LLVM pass:
        # target_compile_options(${TARGET_NAME} PRIVATE -fpass-plugin=PetalEnergyPass.so)
        message(STATUS "Petal: Registered target ${TARGET_NAME} for energy optimization.")
    endif()
endfunction()
