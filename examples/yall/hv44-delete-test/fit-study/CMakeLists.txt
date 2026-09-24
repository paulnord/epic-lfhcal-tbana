cmake_minimum_required(VERSION 3.12)
project(lfhcal_cell903_fit_study LANGUAGES CXX)

set(CMAKE_CXX_STANDARD 17)
set(CMAKE_CXX_STANDARD_REQUIRED ON)
set(CMAKE_CXX_EXTENSIONS OFF)

find_package(ROOT REQUIRED COMPONENTS Core RIO Hist MathCore Minuit2)
include(${ROOT_USE_FILE})

add_executable(fit_cell903 fit_cell903.cc)
target_link_libraries(fit_cell903 PRIVATE ${ROOT_LIBRARIES})

# Pure C++ controls for the shared evaluator and post-fit checks.
enable_testing()
add_executable(test_fixed_width_numerics test_fixed_width_numerics.cc)
add_test(NAME fixed_width_numerics COMMAND test_fixed_width_numerics)
add_executable(test_adaptive_refit_support test_adaptive_refit_support.cc)
add_test(NAME adaptive_refit_numerics COMMAND test_adaptive_refit_support)

# Test the actual ROOT-linked argument parser and setup; no minimization.
add_executable(test_gsigma_override test_gsigma_override.cc)
target_link_libraries(test_gsigma_override PRIVATE ${ROOT_LIBRARIES})
add_test(NAME gsigma_override_setup COMMAND test_gsigma_override)

add_executable(test_start_controls test_start_controls.cc)
target_link_libraries(test_start_controls PRIVATE ${ROOT_LIBRARIES})
add_test(NAME start_controls_setup COMMAND test_start_controls)

add_executable(test_export_cell_examples test_export_cell_examples.cc)
target_link_libraries(test_export_cell_examples PRIVATE ${ROOT_LIBRARIES})
add_test(NAME export_cell_examples COMMAND test_export_cell_examples)

find_package(Python3 REQUIRED COMPONENTS Interpreter)
add_test(NAME adaptive_runner
  COMMAND ${Python3_EXECUTABLE} ${CMAKE_CURRENT_SOURCE_DIR}/test_adaptive_runner.py)
set_tests_properties(adaptive_runner PROPERTIES ENVIRONMENT "PYTHONDONTWRITEBYTECODE=1")

add_test(NAME fit_stability_runner
  COMMAND ${Python3_EXECUTABLE} ${CMAKE_CURRENT_SOURCE_DIR}/test_fit_stability_runner.py)
set_tests_properties(fit_stability_runner PROPERTIES ENVIRONMENT "PYTHONDONTWRITEBYTECODE=1")

add_test(NAME collect_hv_histograms
  COMMAND ${Python3_EXECUTABLE} ${CMAKE_CURRENT_SOURCE_DIR}/test_collect_hv_histograms.py)
set_tests_properties(collect_hv_histograms PROPERTIES ENVIRONMENT "PYTHONDONTWRITEBYTECODE=1")

# Observational ROOT-file analysis is optional on machines without PyROOT.
# The standalone C++ fitter and its tests still work with a C++-only ROOT build.
execute_process(COMMAND ${Python3_EXECUTABLE} -c "import ROOT"
  RESULT_VARIABLE HV_STUDY_PYROOT_STATUS OUTPUT_QUIET ERROR_QUIET)
if(HV_STUDY_PYROOT_STATUS EQUAL 0)
  add_test(NAME analyze_hv_histograms
    COMMAND ${Python3_EXECUTABLE} ${CMAKE_CURRENT_SOURCE_DIR}/test_analyze_hv_histograms.py)
  set_tests_properties(analyze_hv_histograms PROPERTIES ENVIRONMENT "PYTHONDONTWRITEBYTECODE=1")
else()
  message(STATUS "PyROOT unavailable: skipping optional all-cell histogram analysis tests")
endif()
