cmake_minimum_required(VERSION 3.16)
project(ComparisonApp)

# Find Geant4
find_package(Geant4 REQUIRED gdml)
include(${Geant4_USE_FILE})

# Include directories
include_directories(${PROJECT_SOURCE_DIR}/include)

# Source files
file(GLOB sources ${PROJECT_SOURCE_DIR}/src/*.cc)
file(GLOB headers ${PROJECT_SOURCE_DIR}/include/*.hh)

# Executable
add_executable(comparison_app ${sources} ${headers})
target_link_libraries(comparison_app ${Geant4_LIBRARIES})

# Install
install(TARGETS comparison_app DESTINATION bin)
