#ifndef DetectorConstruction_h
#define DetectorConstruction_h 1

#include "G4VUserDetectorConstruction.hh"
#include "G4GDMLParser.hh"
#include <string>

class DetectorConstruction : public G4VUserDetectorConstruction
{
public:
    DetectorConstruction(const std::string& gdmlFile);
    virtual ~DetectorConstruction();

    virtual G4VPhysicalVolume* Construct();

private:
    std::string fGdmlFile;
    G4GDMLParser fParser;
};

#endif
