#include "RunAction.hh"

#include "G4Run.hh"
#include "G4RunManager.hh"
#include "G4SystemOfUnits.hh"

#include <fstream>
#include <cmath>

RunAction::RunAction(const std::string& outputDir)
    : G4UserRunAction(),
      fOutputDir(outputDir),
      fZBins(100),
      fZMin(0.0),
      fZMax(2.0*cm),
      fEnergyBins(100),
      fEMin(1e-11*GeV),
      fEMax(10*GeV)
{
}

RunAction::~RunAction()
{
}

void RunAction::BeginOfRunAction(const G4Run*)
{
    fEdepHist.assign(fZBins, 0.0);
    fNeutronSpectrum.assign(fEnergyBins, 0.0);
}

void RunAction::EndOfRunAction(const G4Run* run)
{
    G4int nofEvents = run->GetNumberOfEvent();
    if (nofEvents == 0) return;

    if (IsMaster()) {
        WriteResults();
    }
}

void RunAction::AddEdep(G4int zBin, G4double edep)
{
    if (zBin >= 0 && zBin < fZBins) {
        std::lock_guard<std::mutex> lock(fMutex);
        fEdepHist[zBin] += edep;
    }
}

void RunAction::AddNeutronExit(G4double energy)
{
    G4int bin = GetEnergyBin(energy);
    if (bin >= 0 && bin < fEnergyBins) {
        std::lock_guard<std::mutex> lock(fMutex);
        fNeutronSpectrum[bin] += 1.0;
    }
}

G4int RunAction::GetZBin(G4double z) const
{
    if (z < fZMin || z >= fZMax) return -1;
    return static_cast<G4int>((z - fZMin) / (fZMax - fZMin) * fZBins);
}

G4int RunAction::GetEnergyBin(G4double e) const
{
    if (e <= 0 || e < fEMin || e >= fEMax) return -1;
    // Logarithmic binning
    G4double logMin = std::log10(fEMin);
    G4double logMax = std::log10(fEMax);
    G4double logE = std::log10(e);
    return static_cast<G4int>((logE - logMin) / (logMax - logMin) * fEnergyBins);
}

void RunAction::WriteResults()
{
    // Write energy deposition profile
    std::string edepFile = fOutputDir + "/edep_profile.dat";
    std::ofstream edepOut(edepFile);
    if (edepOut.is_open()) {
        edepOut << "# z_cm edep_GeV\n";
        G4double dz = (fZMax - fZMin) / fZBins;
        for (G4int i = 0; i < fZBins; ++i) {
            G4double z = fZMin + (i + 0.5) * dz;
            edepOut << z/cm << " " << fEdepHist[i]/GeV << "\n";
        }
        edepOut.close();
    }

    // Write neutron exit spectrum
    std::string specFile = fOutputDir + "/neutron_spectrum.dat";
    std::ofstream specOut(specFile);
    if (specOut.is_open()) {
        specOut << "# energy_GeV count\n";
        G4double logMin = std::log10(fEMin/GeV);
        G4double logMax = std::log10(fEMax/GeV);
        G4double dLogE = (logMax - logMin) / fEnergyBins;
        for (G4int i = 0; i < fEnergyBins; ++i) {
            G4double logE = logMin + (i + 0.5) * dLogE;
            G4double e = std::pow(10.0, logE);
            specOut << e << " " << fNeutronSpectrum[i] << "\n";
        }
        specOut.close();
    }
}
