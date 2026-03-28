function constants = matlab_vawt_constants()
%MATLAB_VAWT_CONSTANTS Current CDO hybrid VAWT SIL baseline for MATLAB work.

constants = struct();

constants.modelFolder = "matlab_models";
constants.silModelName = "cdo_vawt_sil";
constants.simscapeModelName = "cdo_vawt_simscape_plant";

constants.rotorRadiusM = 0.75;
constants.sweptAreaM2 = 4.0;
constants.rotorInertiaKgm2 = 12.0;
constants.drivetrainDampingNms = 0.08;
constants.generatorEfficiency = 0.90;
constants.ratedPowerKw = 0.38;
constants.cutInMs = 2.5;
constants.cutOutMs = 25.0;
constants.maxRotorRpm = 220.0;
constants.brakeTorqueNm = 18.0;
constants.startupTorqueCoeff = 0.12;
constants.startupRpmHandoff = 8.0;
constants.startupTsrHandoff = 0.25;
constants.startupCpFloor = 0.02;
constants.standardAirDensity = 1.225;

constants.cpGeneric = 0.33;
constants.tsrOpt = 2.5;
constants.tsrSpread = 1.85;
constants.baseCpGeneric = 0.33;
constants.baseTsrOpt = 2.5;
constants.baseTsrSpread = 1.85;

constants.secondsPerSubstep = 60.0;
constants.secondsPerHour = 3600.0;

constants.tsrCpLookup = [
    0.0, 0.00;
    0.1, 0.03;
    0.3, 0.05;
    0.5, 0.07;
    0.8, 0.12;
    1.0, 0.16;
    1.5, 0.20;
    2.0, 0.28;
    2.5, 0.33;
    3.0, 0.28;
    3.5, 0.15;
    4.0, 0.00;
];

constants.modeLabels = ["idle", "startup", "adaptive_mppt", "brake"];

end
