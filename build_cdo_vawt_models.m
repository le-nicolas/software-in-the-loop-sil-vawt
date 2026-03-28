function modelInfo = build_cdo_vawt_models()
%BUILD_CDO_VAWT_MODELS Create Simulink and Simscape baselines for the repo.

repoRoot = fileparts(mfilename("fullpath"));
constants = matlab_vawt_constants();
modelDir = fullfile(repoRoot, constants.modelFolder);
if ~exist(modelDir, "dir")
    mkdir(modelDir);
end

addpath(repoRoot);

modelInfo = struct();
modelInfo.repoRoot = repoRoot;
modelInfo.modelDir = modelDir;
modelInfo.silModelName = constants.silModelName;
modelInfo.simscapeModelName = constants.simscapeModelName;
modelInfo.silModelPath = fullfile(modelDir, constants.silModelName + ".slx");
modelInfo.simscapeModelPath = fullfile(modelDir, constants.simscapeModelName + ".slx");

buildSilModel(modelInfo.silModelPath);
buildSimscapeModel(constants, modelInfo.simscapeModelPath);

save(fullfile(modelDir, "cdo_vawt_model_info.mat"), "modelInfo");

disp("Built Simulink model: " + modelInfo.silModelPath);
disp("Built Simscape model: " + modelInfo.simscapeModelPath);

end


function buildSilModel(modelPath)
[modelDir, modelName] = fileparts(modelPath);
ensureModelClosed(modelName);
new_system(modelName);
open_system(modelName);

assignin("base", "wind_speed_ts", timeseries([0; 0], [0; 3600], "Name", "wind_speed_ms"));
assignin("base", "air_density_ts", timeseries([1.225; 1.225], [0; 3600], "Name", "air_density_kgm3"));

set_param(modelName, ...
    Solver="FixedStepDiscrete", ...
    FixedStep="3600", ...
    StartTime="0", ...
    StopTime="31532400", ...
    SaveFormat="Dataset");

add_block("simulink/Sources/From Workspace", modelName + "/WindSpeedTS", ...
    Position=[40 80 180 120], VariableName="wind_speed_ts");
add_block("simulink/Sources/From Workspace", modelName + "/AirDensityTS", ...
    Position=[40 160 180 200], VariableName="air_density_ts");

add_block("simulink/Discrete/Unit Delay", modelName + "/OmegaState", ...
    Position=[230 40 320 80], InitialCondition="0");
add_block("simulink/Discrete/Unit Delay", modelName + "/IntegralState", ...
    Position=[230 120 320 160], InitialCondition="0");
add_block("simulink/Discrete/Unit Delay", modelName + "/LastTorqueState", ...
    Position=[230 200 320 240], InitialCondition="0");

add_block("simulink/Signal Routing/Mux", modelName + "/StateMux", ...
    Position=[360 80 380 220], Inputs="5");
add_block("simulink/User-Defined Functions/MATLAB Fcn", modelName + "/SILCore", ...
    Position=[420 90 600 210], MATLABFcn="matlab_vawt_sil_hour_step_vector(u)");
add_block("simulink/Signal Routing/Demux", modelName + "/StateDemux", ...
    Position=[650 70 655 250], Outputs="10");

add_block("simulink/Sinks/To Workspace", modelName + "/OmegaOut", ...
    Position=[770 20 900 50], VariableName="omega_rad_s", SaveFormat="Structure With Time");
add_block("simulink/Sinks/To Workspace", modelName + "/TSROut", ...
    Position=[770 60 900 90], VariableName="tip_speed_ratio", SaveFormat="Structure With Time");
add_block("simulink/Sinks/To Workspace", modelName + "/CpOut", ...
    Position=[770 100 900 130], VariableName="cp_effective", SaveFormat="Structure With Time");
add_block("simulink/Sinks/To Workspace", modelName + "/AeroTorqueOut", ...
    Position=[770 140 900 170], VariableName="aero_torque_nm", SaveFormat="Structure With Time");
add_block("simulink/Sinks/To Workspace", modelName + "/PowerOut", ...
    Position=[770 180 900 210], VariableName="electrical_power_kw", SaveFormat="Structure With Time");
add_block("simulink/Sinks/To Workspace", modelName + "/ModeOut", ...
    Position=[770 220 900 250], VariableName="mode_id", SaveFormat="Structure With Time");

add_line(modelName, "WindSpeedTS/1", "StateMux/1", "autorouting", "on");
add_line(modelName, "AirDensityTS/1", "StateMux/2", "autorouting", "on");
add_line(modelName, "OmegaState/1", "StateMux/3", "autorouting", "on");
add_line(modelName, "IntegralState/1", "StateMux/4", "autorouting", "on");
add_line(modelName, "LastTorqueState/1", "StateMux/5", "autorouting", "on");

add_line(modelName, "StateMux/1", "SILCore/1", "autorouting", "on");
add_line(modelName, "SILCore/1", "StateDemux/1", "autorouting", "on");

add_line(modelName, "StateDemux/1", "OmegaState/1", "autorouting", "on");
add_line(modelName, "StateDemux/9", "IntegralState/1", "autorouting", "on");
add_line(modelName, "StateDemux/10", "LastTorqueState/1", "autorouting", "on");

add_line(modelName, "StateDemux/1", "OmegaOut/1", "autorouting", "on");
add_line(modelName, "StateDemux/2", "TSROut/1", "autorouting", "on");
add_line(modelName, "StateDemux/3", "CpOut/1", "autorouting", "on");
add_line(modelName, "StateDemux/4", "AeroTorqueOut/1", "autorouting", "on");
add_line(modelName, "StateDemux/7", "PowerOut/1", "autorouting", "on");
add_line(modelName, "StateDemux/8", "ModeOut/1", "autorouting", "on");

set_param(modelName, SimulationCommand="update");
save_system(modelName, modelPath);
close_system(modelName);

if ~exist(modelDir, "dir")
    mkdir(modelDir);
end
end


function buildSimscapeModel(constants, modelPath)
[~, modelName] = fileparts(modelPath);
ensureModelClosed(modelName);
new_system(modelName);
open_system(modelName);

set_param(modelName, Solver="ode23t", StopTime="60");

add_block("simulink/Sources/Step", modelName + "/AeroTorqueStep", ...
    Position=[40 70 100 100], Time="5", Before="0", After="6");
add_block("simulink/Sources/Step", modelName + "/LoadTorqueStep", ...
    Position=[40 150 100 180], Time="10", Before="0", After="2");
add_block("simulink/Math Operations/Gain", modelName + "/NegativeLoadGain", ...
    Position=[130 150 200 180], Gain="-1");

    add_block("nesl_utility/Solver Configuration", modelName + "/SolverConfig", ...
        Position=[70 300 130 360]);
    add_block("nesl_utility/Simulink-PS Converter", modelName + "/AeroTorquePS", ...
        Position=[150 60 220 110]);
    add_block("nesl_utility/Simulink-PS Converter", modelName + "/LoadTorquePS", ...
        Position=[230 140 300 190]);
    add_block("nesl_utility/PS-Simulink Converter", modelName + "/OmegaPS2SL", ...
        Position=[590 150 660 200]);

    add_block("fl_lib/Mechanical/Mechanical Sources/Ideal Torque Source", ...
        modelName + "/AeroTorqueSource", Position=[290 50 360 120]);
    add_block("fl_lib/Mechanical/Mechanical Sources/Ideal Torque Source", ...
        modelName + "/LoadTorqueSource", Position=[390 140 460 210]);
    add_block("fl_lib/Mechanical/Rotational Elements/Inertia", ...
        modelName + "/RotorInertia", Position=[500 70 570 140]);
    add_block("fl_lib/Mechanical/Rotational Elements/Rotational Damper", ...
        modelName + "/DrivetrainDamper", Position=[500 240 570 310]);
    add_block("fl_lib/Mechanical/Mechanical Sensors/Ideal Rotational Motion Sensor", ...
        modelName + "/MotionSensor", Position=[620 60 690 140]);
    add_block("fl_lib/Mechanical/Rotational Elements/Mechanical Rotational Reference", ...
        modelName + "/MechanicalRef", Position=[640 280 690 330]);

add_block("simulink/Sinks/To Workspace", modelName + "/ShaftOmegaOut", ...
    Position=[710 150 840 180], VariableName="simscape_omega_rad_s", SaveFormat="Structure With Time");

set_param(modelName + "/AeroTorquePS", "Unit", "N*m");
set_param(modelName + "/LoadTorquePS", "Unit", "N*m");
set_param(modelName + "/OmegaPS2SL", "Unit", "rad/s");
set_param(modelName + "/RotorInertia", "inertia", num2str(constants.rotorInertiaKgm2));
set_param(modelName + "/DrivetrainDamper", "D", num2str(constants.drivetrainDampingNms));

add_line(modelName, "AeroTorqueStep/1", "AeroTorquePS/1", "autorouting", "on");
add_line(modelName, "LoadTorqueStep/1", "NegativeLoadGain/1", "autorouting", "on");
add_line(modelName, "NegativeLoadGain/1", "LoadTorquePS/1", "autorouting", "on");
add_line(modelName, "OmegaPS2SL/1", "ShaftOmegaOut/1", "autorouting", "on");

connectPhysicalPorts(modelName + "/AeroTorquePS", "RConn1", modelName + "/AeroTorqueSource", "RConn1");
connectPhysicalPorts(modelName + "/LoadTorquePS", "RConn1", modelName + "/LoadTorqueSource", "RConn1");
connectPhysicalPorts(modelName + "/AeroTorqueSource", "LConn1", modelName + "/RotorInertia", "LConn1");
connectPhysicalPorts(modelName + "/LoadTorqueSource", "LConn1", modelName + "/RotorInertia", "LConn1");
connectPhysicalPorts(modelName + "/RotorInertia", "LConn1", modelName + "/MotionSensor", "LConn1");
connectPhysicalPorts(modelName + "/RotorInertia", "LConn1", modelName + "/DrivetrainDamper", "LConn1");
connectPhysicalPorts(modelName + "/AeroTorqueSource", "RConn2", modelName + "/MechanicalRef", "LConn1");
connectPhysicalPorts(modelName + "/LoadTorqueSource", "RConn2", modelName + "/MechanicalRef", "LConn1");
connectPhysicalPorts(modelName + "/DrivetrainDamper", "RConn1", modelName + "/MechanicalRef", "LConn1");
connectPhysicalPorts(modelName + "/MotionSensor", "RConn1", modelName + "/MechanicalRef", "LConn1");
connectPhysicalPorts(modelName + "/SolverConfig", "RConn1", modelName + "/MechanicalRef", "LConn1");
connectPhysicalPorts(modelName + "/MotionSensor", "RConn2", modelName + "/OmegaPS2SL", "LConn1");

set_param(modelName, SimulationCommand="update");
save_system(modelName, modelPath);
close_system(modelName);
end


function connectPhysicalPorts(sourceBlock, sourcePort, targetBlock, targetPort)
sourceHandle = resolvePortHandle(sourceBlock, sourcePort);
targetHandle = resolvePortHandle(targetBlock, targetPort);
add_line(bdroot(sourceBlock), sourceHandle, targetHandle, "autorouting", "on");
end


function handle = resolvePortHandle(blockPath, portToken)
portHandles = get_param(blockPath, "PortHandles");
portField = regexprep(portToken, "\d+$", "");
portIndexToken = regexp(portToken, "\d+$", "match", "once");
if isempty(portIndexToken)
    portIndex = 1;
else
    portIndex = str2double(portIndexToken);
end

handle = portHandles.(portField)(portIndex);
end


function ensureModelClosed(modelName)
if bdIsLoaded(modelName)
    close_system(modelName, 0);
end
end
