#ifndef ActionInitialization_h
#define ActionInitialization_h 1

#include "G4VUserActionInitialization.hh"
#include <string>

class ActionInitialization : public G4VUserActionInitialization
{
public:
    ActionInitialization(const std::string& outputDir);
    virtual ~ActionInitialization();

    virtual void BuildForMaster() const;
    virtual void Build() const;

private:
    std::string fOutputDir;
};

#endif
