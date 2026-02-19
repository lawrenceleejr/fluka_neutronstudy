#include "G4RunManagerFactory.hh"
#include "G4UImanager.hh"
#include "G4VModularPhysicsList.hh"
#include "G4PhysListFactory.hh"
#include "DetectorConstruction.hh"
#include "ActionInitialization.hh"
#include "G4SystemOfUnits.hh"

#include <getopt.h>
#include <iostream>
#include <string>

void PrintUsage() {
    std::cerr << "Usage: comparison_app [options]\n"
              << "Options:\n"
              << "  -g, --geometry FILE    GDML geometry file\n"
              << "  -p, --physics LIST     Physics list name (e.g., FTFP_BERT_HP)\n"
              << "  -m, --macro FILE       Macro file to execute\n"
              << "  -o, --output DIR       Output directory\n"
              << "  -h, --help             Print this help\n";
}

int main(int argc, char** argv) {
    std::string geometryFile;
    std::string physicsList = "FTFP_BERT_HP";
    std::string macroFile;
    std::string outputDir = ".";

    static struct option long_options[] = {
        {"geometry", required_argument, 0, 'g'},
        {"physics",  required_argument, 0, 'p'},
        {"macro",    required_argument, 0, 'm'},
        {"output",   required_argument, 0, 'o'},
        {"help",     no_argument,       0, 'h'},
        {0, 0, 0, 0}
    };

    int opt;
    while ((opt = getopt_long(argc, argv, "g:p:m:o:h", long_options, nullptr)) != -1) {
        switch (opt) {
            case 'g': geometryFile = optarg; break;
            case 'p': physicsList = optarg; break;
            case 'm': macroFile = optarg; break;
            case 'o': outputDir = optarg; break;
            case 'h':
                PrintUsage();
                return 0;
            default:
                PrintUsage();
                return 1;
        }
    }

    if (geometryFile.empty()) {
        std::cerr << "Error: Geometry file is required\n";
        PrintUsage();
        return 1;
    }

    // Create run manager
    auto* runManager = G4RunManagerFactory::CreateRunManager(G4RunManagerType::Default);

    // Detector construction reads GDML and returns world volume
    runManager->SetUserInitialization(new DetectorConstruction(geometryFile));

    // Set up physics list
    G4PhysListFactory factory;
    G4VModularPhysicsList* physics = factory.GetReferencePhysList(physicsList);
    if (!physics) {
        std::cerr << "Error: Unknown physics list: " << physicsList << "\n";
        std::cerr << "Available lists:\n";
        for (const auto& name : factory.AvailablePhysLists()) {
            std::cerr << "  " << name << "\n";
        }
        delete runManager;
        return 1;
    }
    runManager->SetUserInitialization(physics);

    // Set user action initialization
    runManager->SetUserInitialization(new ActionInitialization(outputDir));

    // Initialize
    runManager->Initialize();

    // Execute macro if provided
    G4UImanager* UImanager = G4UImanager::GetUIpointer();
    if (!macroFile.empty()) {
        UImanager->ApplyCommand("/control/execute " + macroFile);
    }

    delete runManager;
    return 0;
}
