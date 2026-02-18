#include "DetectorConstruction.hh"

#include "G4VPhysicalVolume.hh"
#include "G4LogicalVolume.hh"
#include "G4NistManager.hh"

#include <iostream>

DetectorConstruction::DetectorConstruction(const std::string& gdmlFile)
    : G4VUserDetectorConstruction(),
      fGdmlFile(gdmlFile)
{
}

DetectorConstruction::~DetectorConstruction()
{
}

G4VPhysicalVolume* DetectorConstruction::Construct()
{
    std::cout << "Loading GDML geometry from: " << fGdmlFile << std::endl;

    fParser.Read(fGdmlFile);
    G4VPhysicalVolume* worldPV = fParser.GetWorldVolume();

    if (!worldPV) {
        std::cerr << "Error: Failed to load GDML geometry" << std::endl;
        return nullptr;
    }

    // Print geometry info
    G4LogicalVolume* worldLV = worldPV->GetLogicalVolume();
    std::cout << "World volume: " << worldPV->GetName() << std::endl;
    std::cout << "Number of daughters: " << worldLV->GetNoDaughters() << std::endl;

    for (int i = 0; i < worldLV->GetNoDaughters(); ++i) {
        G4VPhysicalVolume* daughter = worldLV->GetDaughter(i);
        std::cout << "  Daughter " << i << ": " << daughter->GetName()
                  << " (" << daughter->GetLogicalVolume()->GetMaterial()->GetName() << ")"
                  << std::endl;
    }

    return worldPV;
}
