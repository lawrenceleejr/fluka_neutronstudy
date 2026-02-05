// Simple GDML geometry loader for FLUGG
// Reads GDML file and makes it available to FLUKA via FLUGG interface

#include "G4GDMLParser.hh"
#include "G4VPhysicalVolume.hh"
#include "G4LogicalVolume.hh"
#include <cstdlib>
#include <iostream>

G4VPhysicalVolume* gdml_world = nullptr;

extern "C" {
    // Called by FLUGG to get the world volume
    G4VPhysicalVolume* get_flugg_world() {
        if (gdml_world) return gdml_world;

        const char* gdml_file = getenv("FLUGG_GDML");
        if (!gdml_file) {
            std::cerr << "ERROR: FLUGG_GDML environment variable not set" << std::endl;
            return nullptr;
        }

        std::cout << "FLUGG: Loading GDML geometry from: " << gdml_file << std::endl;

        G4GDMLParser parser;
        parser.Read(gdml_file);
        gdml_world = parser.GetWorldVolume();

        if (gdml_world) {
            std::cout << "FLUGG: Geometry loaded successfully" << std::endl;
            std::cout << "FLUGG: World volume: " << gdml_world->GetName() << std::endl;
        }

        return gdml_world;
    }
}
