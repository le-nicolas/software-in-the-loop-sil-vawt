function outputs = run_cdo_vawt_matlab_pipeline()
%RUN_CDO_VAWT_MATLAB_PIPELINE Build and validate MATLAB/Simulink repo assets.

repoRoot = fileparts(mfilename("fullpath"));
outputDir = fullfile(repoRoot, "matlab_design_outputs");
if ~exist(outputDir, "dir")
    mkdir(outputDir);
end

pythonHourlyPath = fullfile(repoRoot, "CDO_sil_run_2023_hourly.csv");
pythonSummaryPath = fullfile(repoRoot, "CDO_sil_run_2023_summary.txt");
uncertaintyPath = fullfile(repoRoot, "yield_uncertainty_results.json");
validationReportPath = fullfile(repoRoot, "validation_report.txt");

requiredPythonInputs = [ ...
    string(pythonHourlyPath), ...
    string(pythonSummaryPath), ...
    string(uncertaintyPath), ...
    string(validationReportPath)];
for i = 1:numel(requiredPythonInputs)
    if ~isfile(requiredPythonInputs(i))
        error("Required Python output not found: %s", requiredPythonInputs(i));
    end
end

pythonHourly = readtable(pythonHourlyPath, TextType="string", VariableNamingRule="preserve");
pythonSummaryText = fileread(pythonSummaryPath);
pythonSummaryAnnualYieldKwh = localReadSummaryScalar(pythonSummaryText, "Final annual kWh");
pythonUncertainty = jsondecode(fileread(uncertaintyPath));
pythonValidationReportText = fileread(validationReportPath);

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

pythonAnnualYieldKwh = sum(pythonHourly.hourly_energy_kwh);
pythonDailyP50Wh = pythonUncertainty.summary.daily_p50_wh;
pythonCpPeak = max(double(pythonHourly.mean_cp_effective));
[~, pythonCpPeakIdx] = max(double(pythonHourly.mean_cp_effective));
pythonTsrOpt = double(pythonHourly.mean_tip_speed_ratio(pythonCpPeakIdx));

[~, matlabCpPeakIdx] = max(cpSeries);
matlabCpPeak = max(cpSeries);
matlabTsrOpt = tsrSeries(matlabCpPeakIdx);

matlabValidationSummary = table( ...
    ["annual_yield_kwh"; "daily_p50_wh"; "cp_peak"; "tsr_opt"], ...
    [pythonAnnualYieldKwh; pythonDailyP50Wh; pythonCpPeak; pythonTsrOpt], ...
    [annualYieldKwh; dailyAverageWh; matlabCpPeak; matlabTsrOpt], ...
    [ ...
        localDeltaPct(annualYieldKwh, pythonAnnualYieldKwh); ...
        localDeltaPct(dailyAverageWh, pythonDailyP50Wh); ...
        localDeltaPct(matlabCpPeak, pythonCpPeak); ...
        localDeltaPct(matlabTsrOpt, pythonTsrOpt)], ...
    'VariableNames', ["metric", "python_value", "matlab_value", "delta_pct"]);

pythonLookup = readPythonLookupTable(fullfile(repoRoot, "CDO_project_constants.py"), "TSR_CP_LOOKUP_DMST");
matlabLookup = constants.tsrCpLookup;
comparisonGrid = unique([pythonLookup(:, 1); matlabLookup(:, 1)]);
cpDmst = interp1(pythonLookup(:, 1), pythonLookup(:, 2), comparisonGrid, "linear", 0.0);
cpMatlab = interp1(matlabLookup(:, 1), matlabLookup(:, 2), comparisonGrid, "linear", 0.0);
matlabCpTsrComparison = table( ...
    comparisonGrid, cpDmst, cpMatlab, cpDmst - cpMatlab, ...
    'VariableNames', ["tsr", "cp_dmst", "cp_matlab", "cp_delta"]);

validationSummaryPath = fullfile(repoRoot, "matlab_validation_summary.csv");
cpComparisonPath = fullfile(repoRoot, "matlab_cp_tsr_comparison.csv");
summaryMatPath = fullfile(repoRoot, "matlab_sil_summary.mat");

writetable(matlabValidationSummary, validationSummaryPath);
writetable(matlabCpTsrComparison, cpComparisonPath);

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
outputs.pythonContext = struct( ...
    "hourlyPath", pythonHourlyPath, ...
    "summaryPath", pythonSummaryPath, ...
    "uncertaintyPath", uncertaintyPath, ...
    "validationReportPath", validationReportPath, ...
    "annualYieldKwh", pythonAnnualYieldKwh, ...
    "summaryAnnualYieldKwh", pythonSummaryAnnualYieldKwh, ...
    "dailyP50Wh", pythonDailyP50Wh, ...
    "cpPeak", pythonCpPeak, ...
    "tsrOpt", pythonTsrOpt, ...
    "validationReportText", pythonValidationReportText);
outputs.validationSummaryPath = validationSummaryPath;
outputs.cpComparisonPath = cpComparisonPath;
outputs.summaryMatPath = summaryMatPath;
outputs.matlabValidationSummary = matlabValidationSummary;
outputs.matlabCpTsrComparison = matlabCpTsrComparison;

save( ...
    summaryMatPath, ...
    "outputs", ...
    "pythonHourly", ...
    "pythonSummaryText", ...
    "pythonSummaryAnnualYieldKwh", ...
    "pythonUncertainty", ...
    "pythonValidationReportText", ...
    "matlabValidationSummary", ...
    "matlabCpTsrComparison", ...
    "hourlyTable", ...
    "annualYieldKwh", ...
    "dailyAverageWh", ...
    "modeCounts", ...
    "cpSeries", ...
    "tsrSeries", ...
    "-v7");

disp("MATLAB pipeline complete.");
disp("Saved hourly SIL CSV to: " + hourlyCsvPath);
disp("Saved MATLAB SIL summary to: " + summaryPath);
fprintf("MATLAB validation complete. Delta annual yield: %.2f%%\n", ...
    localDeltaPct(annualYieldKwh, pythonAnnualYieldKwh));

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


function value = localReadSummaryScalar(summaryText, label)
escapedLabel = regexptranslate("escape", label);
tokens = regexp(summaryText, escapedLabel + ":\s*([0-9.+eE-]+)", "tokens", "once");
if isempty(tokens)
    error("Could not parse %s from Python summary.", label);
end
value = str2double(tokens{1});
end


function lookup = readPythonLookupTable(filePath, constantName)
lines = readlines(filePath);
startIdx = find(contains(lines, constantName + " = ["), 1, "first");
if isempty(startIdx)
    error("Could not find %s in %s.", constantName, filePath);
end

endIdx = find(contains(lines(startIdx + 1:end), "]"), 1, "first");
if isempty(endIdx)
    error("Could not find end of %s in %s.", constantName, filePath);
end
endIdx = startIdx + endIdx;

blockLines = lines(startIdx + 1:endIdx - 1);
lookup = zeros(0, 2);
for i = 1:numel(blockLines)
    tokens = regexp(blockLines(i), '\(\s*([0-9.]+)\s*,\s*([0-9.]+)\s*\)', "tokens", "once");
    if isempty(tokens)
        continue;
    end
    lookup(end + 1, 1) = str2double(tokens{1}); %#ok<AGROW>
    lookup(end, 2) = str2double(tokens{2}); %#ok<AGROW>
end

if isempty(lookup)
    error("No lookup entries were parsed from %s.", filePath);
end
end


function deltaPct = localDeltaPct(matlabValue, pythonValue)
denominator = max(abs(double(pythonValue)), 1.0e-9);
deltaPct = 100.0 * (double(matlabValue) - double(pythonValue)) / denominator;
end
