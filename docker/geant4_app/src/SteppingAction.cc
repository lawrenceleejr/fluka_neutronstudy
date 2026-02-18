#include "SteppingAction.hh"
#include "RunAction.hh"

#include "G4Step.hh"
#include "G4Track.hh"
#include "G4VPhysicalVolume.hh"
#include "G4SystemOfUnits.hh"
#include "G4ParticleDefinition.hh"

SteppingAction::SteppingAction(RunAction* runAction)
    : G4UserSteppingAction(),
      fRunAction(runAction)
{
}

SteppingAction::~SteppingAction()
{
}

void SteppingAction::UserSteppingAction(const G4Step* step)
{
    // Get energy deposition
    G4double edep = step->GetTotalEnergyDeposit();

    if (edep > 0) {
        G4ThreeVector pos = step->GetPreStepPoint()->GetPosition();
        G4int zBin = fRunAction->GetZBin(pos.z());
        fRunAction->AddEdep(zBin, edep);
    }

    // Check for neutron exiting geometry
    G4Track* track = step->GetTrack();
    G4ParticleDefinition* particle = track->GetDefinition();

    if (particle->GetParticleName() == "neutron") {
        G4StepPoint* postPoint = step->GetPostStepPoint();
        G4VPhysicalVolume* postVol = postPoint->GetPhysicalVolume();

        // If leaving world volume (postVol is null) or entering vacuum
        if (postVol == nullptr ||
            postVol->GetLogicalVolume()->GetMaterial()->GetName() == "G4_Galactic") {
            G4double energy = track->GetKineticEnergy();
            fRunAction->AddNeutronExit(energy);
        }
    }
}
