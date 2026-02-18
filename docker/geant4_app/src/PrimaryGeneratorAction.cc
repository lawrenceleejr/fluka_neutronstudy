#include "PrimaryGeneratorAction.hh"

#include "G4LogicalVolumeStore.hh"
#include "G4LogicalVolume.hh"
#include "G4Box.hh"
#include "G4RunManager.hh"
#include "G4ParticleGun.hh"
#include "G4ParticleTable.hh"
#include "G4ParticleDefinition.hh"
#include "G4SystemOfUnits.hh"
#include "Randomize.hh"

PrimaryGeneratorAction::PrimaryGeneratorAction()
    : G4VUserPrimaryGeneratorAction(),
      fParticleGun(0)
{
    G4int n_particle = 1;
    fParticleGun = new G4ParticleGun(n_particle);

    // Default particle: neutron
    G4ParticleTable* particleTable = G4ParticleTable::GetParticleTable();
    G4ParticleDefinition* particle = particleTable->FindParticle("neutron");
    fParticleGun->SetParticleDefinition(particle);
    fParticleGun->SetParticleMomentumDirection(G4ThreeVector(0., 0., 1.));
    fParticleGun->SetParticleEnergy(1.*MeV);
    fParticleGun->SetParticlePosition(G4ThreeVector(0., 0., -1.*cm));
}

PrimaryGeneratorAction::~PrimaryGeneratorAction()
{
    delete fParticleGun;
}

void PrimaryGeneratorAction::GeneratePrimaries(G4Event* anEvent)
{
    fParticleGun->GeneratePrimaryVertex(anEvent);
}
