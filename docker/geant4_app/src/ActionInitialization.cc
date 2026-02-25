#include "ActionInitialization.hh"
#include "PrimaryGeneratorAction.hh"
#include "RunAction.hh"
#include "EventAction.hh"
#include "SteppingAction.hh"

ActionInitialization::ActionInitialization(const std::string& outputDir)
    : G4VUserActionInitialization(),
      fOutputDir(outputDir)
{
}

ActionInitialization::~ActionInitialization()
{
}

void ActionInitialization::BuildForMaster() const
{
    SetUserAction(new RunAction(fOutputDir));
}

void ActionInitialization::Build() const
{
    SetUserAction(new PrimaryGeneratorAction());

    RunAction* runAction = new RunAction(fOutputDir);
    SetUserAction(runAction);

    SetUserAction(new EventAction(runAction));
    SetUserAction(new SteppingAction(runAction));
}
