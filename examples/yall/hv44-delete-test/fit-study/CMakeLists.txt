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
add_executable(test_adaptive_refit_support test_adaptive_refit_support.cc)
add_test(NAME adaptive_refit_numerics COMMAND test_adaptive_refit_support)

# Test the actual ROOT-linked argument parser and setup; no minimization.
add_executable(test_gsigma_override test_gsigma_override.cc)
target_link_libraries(test_gsigma_override PRIVATE ${ROOT_LIBRARIES})
add_test(NAME gsigma_override_setup COMMAND test_gsigma_override)
