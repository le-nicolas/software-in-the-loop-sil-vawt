function outputs = run_cdo_vawt_matlab_pipeline()
%RUN_CDO_VAWT_MATLAB_PIPELINE Build and validate MATLAB/Simulink repo assets.

repoRoot = fileparts(mfilename("fullpath"));
outputDir = fullfile(repoRoot, "matlab_design_outputs");
if ~exist(outputDir, "dir")
    mkdir(outputDir);
end

foundationResults = matlab_design_foundation_benchmark();
modelInfo = build_cdo_vawt_models();
load_system(modelInfo.silModelPath);
load_system(modelInfo.simscapeModelPath);

constants = matlab_vawt_constants();
raw = readtable(fullfile(repoRoot, "CDO_wind_2023_hourly.csv"), TextType="string", VariableNamingRule="preserve");
timeHours = (0:height(raw)-1)';
timeSeconds = timeHours .* constants.secondsPerHour;

wind_speed_ts = timeseries(raw.wind_speed_15m_ms, timeSeconds, "Name", "wind_speed_ms");
air_density_ts = timeseries(raw.air_density_kgm3, timeSeconds, "Name", "air_density_kgm3");

assignin("base", "wind_speed_ts", wind_speed_ts);
assignin("base", "air_density_ts", air_density_ts);

silSimOut = sim(modelInfo.silModelName, "StopTime", num2str(timeSeconds(end)));
omegaStruct = silSimOut.get("omega_rad_s");
tsrStruct = silSimOut.get("tip_speed_ratio");
cpStruct = silSimOut.get("cp_effective");
aeroStruct = silSimOut.get("aero_torque_nm");
powerStruct = silSimOut.get("electrical_power_kw");
modeStruct = silSimOut.get("mode_id");

omegaSeries = unpackLoggedSignal(omegaStruct, height(raw));
tsrSeries = unpackLoggedSignal(tsrStruct, height(raw));
cpSeries = unpackLoggedSignal(cpStruct, height(raw));
aeroSeries = unpackLoggedSignal(aeroStruct, height(raw));
powerSeries = unpackLoggedSignal(powerStruct, height(raw));
modeSeries = unpackLoggedSignal(modeStruct, height(raw));

hourlyTable = table( ...
    raw.hour_of_year, ...
    raw.datetime, ...
    raw.wind_speed_15m_ms, ...
    raw.air_density_kgm3, ...
    omegaSeries, ...
    omegaSeries .* 60.0 ./ (2.0 * pi), ...
    tsrSeries, ...
    cpSeries, ...
    aeroSeries, ...
    powerSeries, ...
    modeSeries, ...
    'VariableNames', [ ...
        "hour_of_year", "datetime", "wind_speed_15m_ms", "air_density_kgm3", ...
        "omega_rad_s", "rotor_rpm", "tsr", "cp_effective", ...
        "aero_torque_nm", "electrical_power_kw", "mode_id"]);

hourlyCsvPath = fullfile(outputDir, "matlab_sil_hourly.csv");
writetable(hourlyTable, hourlyCsvPath);

annualYieldKwh = sum(powerSeries);
dailyAverageWh = annualYieldKwh * 1000.0 / 365.0;
modeCounts = histcounts(modeSeries, 0.5:1.0:4.5);

simscapeOut = sim(modelInfo.simscapeModelName, "StopTime", "60");
simscapeOmega = unpackLoggedSignal(simscapeOut.get("simscape_omega_rad_s"), []);

summaryPath = fullfile(outputDir, "matlab_sil_summary.txt");
fid = fopen(summaryPath, "w");
cleanup = onCleanup(@() fclose(fid));
fprintf(fid, "=== MATLAB / SIMULINK / SIMSCAPE STATUS ===\n");
fprintf(fid, "SIL model: %s\n", modelInfo.silModelPath);
fprintf(fid, "Simscape model: %s\n", modelInfo.simscapeModelPath);
fprintf(fid, "Annual yield (MATLAB SIL): %.6f kWh/yr\n", annualYieldKwh);
fprintf(fid, "Daily average (MATLAB SIL): %.6f Wh/day\n", dailyAverageWh);
fprintf(fid, "Mode counts [idle startup adaptive_mppt brake]: %d %d %d %d\n", modeCounts);
fprintf(fid, "Peak hourly electrical power: %.6f kW\n", max(powerSeries));
fprintf(fid, "Peak hourly TSR: %.6f\n", max(tsrSeries));
fprintf(fid, "Simscape final omega: %.6f rad/s\n", simscapeOmega(end));

outputs = struct();
outputs.foundationResults = foundationResults;
outputs.modelInfo = modelInfo;
outputs.hourlyTable = hourlyTable;
outputs.annualYieldKwh = annualYieldKwh;
outputs.dailyAverageWh = dailyAverageWh;
outputs.summaryPath = summaryPath;
outputs.hourlyCsvPath = hourlyCsvPath;
outputs.simscapeFinalOmega = simscapeOmega(end);

disp("MATLAB pipeline complete.");
disp("Saved hourly SIL CSV to: " + hourlyCsvPath);
disp("Saved MATLAB SIL summary to: " + summaryPath);

end


function values = unpackLoggedSignal(signalStruct, expectedLength)
if isa(signalStruct, "timeseries")
    values = reshape(signalStruct.Data, [], 1);
elseif isstruct(signalStruct)
    if isfield(signalStruct, "signals") && isfield(signalStruct.signals, "values")
        values = reshape(signalStruct.signals.values, [], 1);
    elseif isfield(signalStruct, "Data")
        values = reshape(signalStruct.Data, [], 1);
    else
        values = reshape(struct2array(signalStruct), [], 1);
    end
else
    values = reshape(signalStruct, [], 1);
end

if ~isempty(expectedLength) && numel(values) > expectedLength
    values = values(1:expectedLength);
end
end
