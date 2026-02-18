#ifndef RunAction_h
#define RunAction_h 1

#include "G4UserRunAction.hh"
#include "globals.hh"
#include <vector>
#include <string>
#include <mutex>

class G4Run;

class RunAction : public G4UserRunAction
{
public:
    RunAction(const std::string& outputDir);
    virtual ~RunAction();

    virtual void BeginOfRunAction(const G4Run*);
    virtual void EndOfRunAction(const G4Run*);

    void AddEdep(G4int zBin, G4double edep);
    void AddNeutronExit(G4double energy);

    void SetZBins(G4int n) { fZBins = n; }
    void SetZRange(G4double zmin, G4double zmax) { fZMin = zmin; fZMax = zmax; }
    void SetEnergyBins(G4int n) { fEnergyBins = n; }
    void SetEnergyRange(G4double emin, G4double emax) { fEMin = emin; fEMax = emax; }

    G4int GetZBin(G4double z) const;
    G4int GetEnergyBin(G4double e) const;

private:
    std::string fOutputDir;
    G4int fZBins;
    G4double fZMin, fZMax;
    std::vector<G4double> fEdepHist;
    G4int fEnergyBins;
    G4double fEMin, fEMax;
    std::vector<G4double> fNeutronSpectrum;
    std::mutex fMutex;

    void WriteResults();
};

#endif
