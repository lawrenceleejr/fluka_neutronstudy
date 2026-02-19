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
    // Accumulate energy deposition
    G4double edep = step->GetTotalEnergyDeposit();
    if (edep > 0) {
        G4ThreeVector pos = step->GetPreStepPoint()->GetPosition();
        G4int zBin = fRunAction->GetZBin(pos.z());
        fRunAction->AddEdep(zBin, edep);
    }

    // Detect neutrons exiting the geometry (postStep volume is null = leaving world)
    G4Track* track = step->GetTrack();
    if (track->GetDefinition()->GetParticleName() == "neutron") {
        G4StepPoint* post = step->GetPostStepPoint();
        // postVolume is nullptr when the track exits the world volume
        if (post->GetPhysicalVolume() == nullptr) {
            fRunAction->AddNeutronExit(track->GetKineticEnergy());
        }
    }
}
