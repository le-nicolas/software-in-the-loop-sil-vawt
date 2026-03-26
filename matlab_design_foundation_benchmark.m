function results = matlab_design_foundation_benchmark()
% MATLAB design benchmark for CDO VAWT Fusion360 foundation numbers.
% Reads the repo dataset plus sphere/benchmark CSV outputs and produces:
%   - MATLAB-native design parameter tables
%   - seasonal and load-case summaries
%   - optional toolbox-enhanced fits/models
%   - saved .mat workspace for downstream Simulink/Simscape work
%
% Run from the repo root:
%   >> matlab_design_foundation_benchmark

repoRoot = fileparts(mfilename("fullpath"));
outputDir = fullfile(repoRoot, "matlab_design_outputs");
if ~exist(outputDir, "dir")
    mkdir(outputDir);
end

toolboxInfo = detectOptionalToolboxes();

rawCsv = fullfile(repoRoot, "CDO_wind_2023_hourly.csv");
viz10HourlyCsv = fullfile(repoRoot, "CDO_wind_visualizations_2023", "viz10_sphere_hourly_metrics.csv");
viz10AzimuthCsv = fullfile(repoRoot, "CDO_wind_visualizations_2023", "viz10_blade_azimuth_month1.csv");
viz10ParticleCsv = fullfile(repoRoot, "CDO_wind_visualizations_2023", "viz10_particle_capture_month1.csv");
fusionParamsCsv = fullfile(repoRoot, "design_benchmarks", "fusion360_design_parameters.csv");
fusionLoadCasesCsv = fullfile(repoRoot, "design_benchmarks", "fusion360_load_cases.csv");

raw = readtable(rawCsv, TextType="string", VariableNamingRule="preserve");
hourly = readtable(viz10HourlyCsv, TextType="string", VariableNamingRule="preserve");
azimuth = readtable(viz10AzimuthCsv, TextType="string", VariableNamingRule="preserve");
particle = readtable(viz10ParticleCsv, TextType="string", VariableNamingRule="preserve");
fusionParams = readtable(fusionParamsCsv, TextType="string", VariableNamingRule="preserve");
fusionLoadCases = readtable(fusionLoadCasesCsv, TextType="string", VariableNamingRule="preserve");

operatingMask = hourly.u_total_ms >= scalarNumeric(fusionParams.value(fusionParams.parameter == "cut_in_ms"));

foundationTable = buildFoundationTable(raw, hourly, fusionParams, operatingMask);
seasonalTable = buildSeasonalTable(raw, hourly);
loadCaseTable = enrichLoadCases(fusionLoadCases, hourly);
toolboxTable = buildToolboxTable(toolboxInfo);
extras = buildToolboxExtras(hourly, azimuth, particle, toolboxInfo);

saveFoundationTables(outputDir, foundationTable, seasonalTable, loadCaseTable, toolboxTable);
saveSummaryText(outputDir, foundationTable, seasonalTable, loadCaseTable, toolboxTable, extras);
savePlots(outputDir, raw, hourly, azimuth, particle, foundationTable, seasonalTable, extras);
results = saveWorkspace(outputDir, foundationTable, seasonalTable, loadCaseTable, toolboxTable, extras, toolboxInfo);

disp("=== MATLAB CDO VAWT DESIGN FOUNDATION ===");
disp(foundationTable(:, ["parameter", "value", "units", "basis"]));
disp("Saved MATLAB design outputs to: " + outputDir);

end


function toolboxInfo = detectOptionalToolboxes()
names = string({ver().Name});
toolboxInfo = struct();
toolboxInfo.curveFitting = any(names == "Curve Fitting Toolbox");
toolboxInfo.signalProcessing = any(names == "Signal Processing Toolbox");
toolboxInfo.dsp = any(names == "DSP System Toolbox");
toolboxInfo.control = any(names == "Control System Toolbox");
toolboxInfo.systemIdentification = any(names == "System Identification Toolbox");
toolboxInfo.simulink = any(names == "Simulink");
toolboxInfo.simscape = any(names == "Simscape");
toolboxInfo.reportGenerator = any(names == "MATLAB Report Generator");
toolboxInfo.simulink3d = any(names == "Simulink 3D Animation");
end


function tableOut = buildFoundationTable(raw, hourly, fusionParams, operatingMask)
paramValue = @(key) scalarNumeric(fusionParams.value(fusionParams.parameter == key));

uOp = hourly.u_total_ms(operatingMask);
rpmOp = hourly.rotor_rpm(operatingMask);
omegaOp = hourly.omega_rad_s(operatingMask);
torqueOp = hourly.aero_torque_nm(operatingMask);
cpOp = hourly.cp_effective(operatingMask);
captureOp = hourly.particle_capture_fraction(operatingMask);
meanHOp = hourly.particle_mean_h(operatingMask);

rows = {
    "rotor_radius_m", paramValue("rotor_radius_m"), "m", "Imported from Python Fusion360 benchmark";
    "rotor_diameter_m", paramValue("rotor_diameter_m"), "m", "Imported from Python Fusion360 benchmark";
    "rotor_height_m", paramValue("rotor_height_m"), "m", "Swept-area equivalent height";
    "operating_hours_2023", nnz(operatingMask), "hours", "MATLAB recomputed from viz10 hourly export";
    "wind_operating_p50_ms", prctile(uOp, 50), "m/s", "MATLAB percentile";
    "wind_operating_p75_ms", prctile(uOp, 75), "m/s", "MATLAB percentile";
    "wind_operating_p90_ms", prctile(uOp, 90), "m/s", "MATLAB percentile";
    "rotor_rpm_p50", prctile(rpmOp, 50), "rpm", "MATLAB percentile";
    "rotor_rpm_p75", prctile(rpmOp, 75), "rpm", "MATLAB percentile";
    "rotor_rpm_p90", prctile(rpmOp, 90), "rpm", "MATLAB percentile";
    "omega_rad_s_p50", prctile(omegaOp, 50), "rad/s", "MATLAB percentile";
    "omega_rad_s_p90", prctile(omegaOp, 90), "rad/s", "MATLAB percentile";
    "aero_torque_nm_p50", prctile(torqueOp, 50), "N*m", "MATLAB percentile";
    "aero_torque_nm_p90", prctile(torqueOp, 90), "N*m", "Design structural load case";
    "aero_torque_nm_p95", prctile(torqueOp, 95), "N*m", "Peak structural load case";
    "cp_operating_p50", prctile(cpOp, 50), "-", "MATLAB percentile";
    "cp_operating_p90", prctile(cpOp, 90), "-", "MATLAB percentile";
    "capture_fraction_p10", prctile(captureOp, 10), "-", "Lower-tail capture robustness";
    "capture_fraction_p50", prctile(captureOp, 50), "-", "Median capture robustness";
    "capture_fraction_p90", prctile(captureOp, 90), "-", "Upper-tail capture robustness";
    "mean_h_p10", prctile(meanHOp, 10), "-", "Lower-tail DPCBF mean h";
    "mean_h_p50", prctile(meanHOp, 50), "-", "Median DPCBF mean h";
    "mean_h_p90", prctile(meanHOp, 90), "-", "Upper-tail DPCBF mean h";
    "dominant_peak_sector_deg", paramValue("dominant_peak_sector_deg"), "deg", "Imported annual azimuth benchmark";
    "design_tip_speed_p90_ms", prctile(omegaOp, 90) * paramValue("rotor_radius_m"), "m/s", "MATLAB percentile";
    "design_tip_speed_p95_ms", prctile(omegaOp, 95) * paramValue("rotor_radius_m"), "m/s", "MATLAB percentile";
    "recommended_nominal_rpm", paramValue("recommended_nominal_rpm"), "rpm", "Imported Fusion360 baseline";
    "recommended_design_torque_nm", paramValue("recommended_design_torque_nm"), "N*m", "Imported Fusion360 baseline";
    "recommended_peak_torque_nm", paramValue("recommended_peak_torque_nm"), "N*m", "Imported Fusion360 baseline";
    "mean_air_density_kgm3", mean(raw.air_density_kgm3), "kg/m^3", "Raw 2023 dataset mean";
    "mean_wind_15m_ms", mean(raw.wind_speed_15m_ms), "m/s", "Raw 2023 dataset mean";
    "peak_hourly_wind_15m_ms", max(raw.wind_speed_15m_ms), "m/s", "Raw 2023 dataset max";
    };

tableOut = cell2table(rows, VariableNames=["parameter", "value", "units", "basis"]);
end


function seasonalTable = buildSeasonalTable(raw, hourly)
seasonNames = unique(raw.season, "stable");
rows = cell(numel(seasonNames), 7);
for i = 1:numel(seasonNames)
    maskRaw = raw.season == seasonNames(i);
    maskHourly = hourly.season == seasonNames(i);
    rows(i, :) = {
        seasonNames(i), ...
        mean(raw.wind_speed_15m_ms(maskRaw)), ...
        prctile(raw.wind_speed_15m_ms(maskRaw), 90), ...
        mean(hourly.rotor_rpm(maskHourly)), ...
        mean(hourly.aero_torque_nm(maskHourly)), ...
        mean(hourly.particle_capture_fraction(maskHourly)), ...
        mean(hourly.particle_mean_h(maskHourly))
    };
end

seasonalTable = cell2table(rows, VariableNames=[ ...
    "season", ...
    "mean_wind_15m_ms", ...
    "p90_wind_15m_ms", ...
    "mean_rotor_rpm", ...
    "mean_aero_torque_nm", ...
    "mean_capture_fraction", ...
    "mean_h"]);
end


function loadCaseTable = enrichLoadCases(fusionLoadCases, hourly)
loadCaseTable = fusionLoadCases;

extraFields = ["domega_dt", "particle_capture_fraction", "particle_mean_h"];
for i = 1:numel(extraFields)
    loadCaseTable.(extraFields(i)) = zeros(height(loadCaseTable), 1);
end

for i = 1:height(loadCaseTable)
    idx = find(hourly.hour_of_year == loadCaseTable.hour_of_year(i), 1, "first");
    if isempty(idx)
        continue;
    end
    loadCaseTable.domega_dt(i) = hourly.domega_dt(idx);
    loadCaseTable.particle_capture_fraction(i) = hourly.particle_capture_fraction(idx);
    loadCaseTable.particle_mean_h(i) = hourly.particle_mean_h(idx);
end
end


function toolboxTable = buildToolboxTable(toolboxInfo)
names = string(fieldnames(toolboxInfo));
used = cell2mat(struct2cell(toolboxInfo));
toolboxTable = table(names, used, VariableNames=["toolbox", "available"]);
end


function extras = buildToolboxExtras(hourly, azimuth, particle, toolboxInfo)
extras = struct();
extras.notes = strings(0, 1);

operatingMask = hourly.u_total_ms >= 2.5;
uOp = hourly.u_total_ms(operatingMask);
omegaOp = hourly.omega_rad_s(operatingMask);
tsrOp = hourly.tsr(operatingMask);
cpOp = hourly.cp_effective(operatingMask);

if toolboxInfo.curveFitting
    try
        fitObj = fit(tsrOp, cpOp, "smoothingspline");
        fitValues = feval(fitObj, tsrOp);
        extras.cpCurveFit = struct( ...
            "fitType", "smoothingspline", ...
            "rmse", sqrt(mean((fitValues - cpOp).^2)), ...
            "tsrGrid", linspace(min(tsrOp), max(tsrOp), 200)', ...
            "cpGrid", feval(fitObj, linspace(min(tsrOp), max(tsrOp), 200)') ...
            );
        extras.notes(end+1) = "Curve Fitting Toolbox used for cp(tsr) spline benchmark.";
    catch ME
        extras.cpCurveFitError = string(ME.message);
    end
end

if toolboxInfo.signalProcessing
    try
        uPrime = hourly.u_total_ms - hourly.u_mean_ms;
        [pxx, f] = pwelch(uPrime, [], [], [], 1);
        [~, idx] = max(pxx);
        dominantFrequency = f(idx);
        dominantPeriodHours = 1 / max(dominantFrequency, eps);
        extras.turbulenceSpectrum = struct( ...
            "frequency_cph", f, ...
            "psd", pxx, ...
            "dominantPeriodHours", dominantPeriodHours);
        extras.notes(end+1) = "Signal Processing Toolbox used for turbulence PSD via pwelch.";
    catch ME
        extras.turbulenceSpectrumError = string(ME.message);
    end
end

if toolboxInfo.systemIdentification
    try
        idObj = iddata(omegaOp, uOp, 1.0);
        sys1 = tfest(idObj, 1);
        extras.identifiedRotorModel = sys1;
        extras.notes(end+1) = "System Identification Toolbox used for first-order wind-to-omega tfest model.";
    catch ME
        extras.identifiedRotorModelError = string(ME.message);
    end
end

if toolboxInfo.control
    try
        if isfield(extras, "identifiedRotorModel")
            sys = extras.identifiedRotorModel;
        else
            gain = mean(omegaOp) / max(mean(uOp), eps);
            tau = max(0.1, median(hourly.omega_rad_s(operatingMask)) / max(median(hourly.domega_dt(operatingMask & abs(hourly.domega_dt) > 0)), eps));
            sys = tf(gain, [tau 1]);
        end
        extras.controlModel = sys;
        extras.controlMargins = struct( ...
            "dcgain", dcgain(sys), ...
            "bandwidth", bandwidth(sys));
        extras.notes(end+1) = "Control System Toolbox used for nominal rotor-response transfer benchmark.";
    catch ME
        extras.controlModelError = string(ME.message);
    end
end

if toolboxInfo.simulink
    try
        extras.simulinkParameters = struct( ...
            "RotorRadius", Simulink.Parameter(0.75), ...
            "RotorHeight", Simulink.Parameter(2.6666666667), ...
            "NominalRPM", Simulink.Parameter(prctile(hourly.rotor_rpm(operatingMask), 50)), ...
            "DesignTorqueNm", Simulink.Parameter(prctile(hourly.aero_torque_nm(operatingMask), 90)));
        extras.notes(end+1) = "Simulink Parameter objects created for downstream model wiring.";
    catch ME
        extras.simulinkParametersError = string(ME.message);
    end
end

if toolboxInfo.simscape
    try
        extras.simscapeValues = struct( ...
            "RotorRadius", simscape.Value(0.75, "m"), ...
            "RotorHeight", simscape.Value(2.6666666667, "m"), ...
            "DesignTorque", simscape.Value(prctile(hourly.aero_torque_nm(operatingMask), 90), "N*m"));
        extras.notes(end+1) = "Simscape unit-aware values created for physical-model follow-on work.";
    catch ME
        extras.simscapeValuesError = string(ME.message);
    end
end

extras.azimuthSummary = groupsummary(azimuth, "phi_deg", "mean", ["v_rel_mag_ms", "h_tip"]);
extras.particleSummary = table( ...
    mean(particle.h_particle), ...
    prctile(particle.h_particle, 10), ...
    prctile(particle.h_particle, 50), ...
    prctile(particle.h_particle, 90), ...
    'VariableNames', ["mean_h_particle", "p10_h_particle", "p50_h_particle", "p90_h_particle"]);
end


function saveFoundationTables(outputDir, foundationTable, seasonalTable, loadCaseTable, toolboxTable)
writetable(foundationTable, fullfile(outputDir, "matlab_foundation_parameters.csv"));
writetable(seasonalTable, fullfile(outputDir, "matlab_seasonal_summary.csv"));
writetable(loadCaseTable, fullfile(outputDir, "matlab_foundation_load_cases.csv"));
writetable(toolboxTable, fullfile(outputDir, "matlab_toolbox_inventory.csv"));
end


function saveSummaryText(outputDir, foundationTable, seasonalTable, loadCaseTable, toolboxTable, extras)
fid = fopen(fullfile(outputDir, "matlab_foundation_summary.txt"), "w");
cleanup = onCleanup(@() fclose(fid));

fprintf(fid, "=== MATLAB CDO VAWT DESIGN FOUNDATION ===\n");
for i = 1:height(foundationTable)
    fprintf(fid, "%s: %.6f %s | %s\n", foundationTable.parameter(i), foundationTable.value(i), foundationTable.units(i), foundationTable.basis(i));
end

fprintf(fid, "\n=== Seasonal Summary ===\n");
for i = 1:height(seasonalTable)
    fprintf(fid, "%s | mean wind %.3f m/s | mean rpm %.3f | mean torque %.3f N*m | capture %.3f | mean h %.3f\n", ...
        seasonalTable.season(i), ...
        seasonalTable.mean_wind_15m_ms(i), ...
        seasonalTable.mean_rotor_rpm(i), ...
        seasonalTable.mean_aero_torque_nm(i), ...
        seasonalTable.mean_capture_fraction(i), ...
        seasonalTable.mean_h(i));
end

fprintf(fid, "\n=== Load Cases ===\n");
for i = 1:height(loadCaseTable)
    fprintf(fid, "%s | hour %d | U=%.3f m/s | rpm=%.3f | torque=%.3f N*m | capture=%.3f | mean h=%.3f\n", ...
        loadCaseTable.("case")(i), ...
        loadCaseTable.hour_of_year(i), ...
        loadCaseTable.u_total_ms(i), ...
        loadCaseTable.rotor_rpm(i), ...
        loadCaseTable.aero_torque_nm(i), ...
        loadCaseTable.particle_capture_fraction(i), ...
        loadCaseTable.particle_mean_h(i));
end

fprintf(fid, "\n=== Toolbox Inventory ===\n");
for i = 1:height(toolboxTable)
    fprintf(fid, "%s: %d\n", toolboxTable.toolbox(i), toolboxTable.available(i));
end

if isfield(extras, "notes") && ~isempty(extras.notes)
    fprintf(fid, "\n=== Toolbox Notes ===\n");
    for i = 1:numel(extras.notes)
        fprintf(fid, "%s\n", extras.notes(i));
    end
end
end


function savePlots(outputDir, raw, hourly, azimuth, ~, ~, seasonalTable, extras)
fig = figure("Visible", "off", "Position", [100 100 1400 900], "Color", "w");
tiledlayout(2, 2, "Padding", "compact", "TileSpacing", "compact");

nexttile;
histogram(raw.wind_speed_15m_ms, 30, FaceColor=[0.15 0.4 0.85], EdgeColor="none");
title("Raw 15m Wind Speed Distribution");
xlabel("Wind speed (m/s)");
ylabel("Count");

nexttile;
scatter(hourly.tsr, hourly.cp_effective, 8, hourly.particle_capture_fraction, "filled");
title("Cp vs TSR colored by capture fraction");
xlabel("TSR");
ylabel("Cp");
colorbar;

nexttile;
polarplot(deg2rad(azimuth.phi_deg), azimuth.v_rel_mag_ms, ".");
title("Month-1 Azimuthal v_{rel}");

nexttile;
bar(categorical(seasonalTable.season), seasonalTable.mean_aero_torque_nm, FaceColor=[0.85 0.42 0.12]);
title("Seasonal mean aero torque");
ylabel("Torque (N*m)");

exportgraphics(fig, fullfile(outputDir, "matlab_foundation_dashboard.png"), Resolution=180);
savefig(fig, fullfile(outputDir, "matlab_foundation_dashboard.fig"));
close(fig);

if isfield(extras, "cpCurveFit")
    fig2 = figure("Visible", "off", "Position", [150 150 900 500], "Color", "w");
    plot(extras.cpCurveFit.tsrGrid, extras.cpCurveFit.cpGrid, "LineWidth", 2);
    hold on;
    scatter(hourly.tsr, hourly.cp_effective, 8, ".", MarkerEdgeAlpha=0.15);
    grid on;
    title("Curve Fitting Toolbox: cp(tsr) spline");
    xlabel("TSR");
    ylabel("Cp");
    exportgraphics(fig2, fullfile(outputDir, "matlab_cp_curve_fit.png"), Resolution=180);
    close(fig2);
end
end


function results = saveWorkspace(outputDir, foundationTable, seasonalTable, loadCaseTable, toolboxTable, extras, toolboxInfo)
results = struct();
results.foundationTable = foundationTable;
results.seasonalTable = seasonalTable;
results.loadCaseTable = loadCaseTable;
results.toolboxTable = toolboxTable;
results.extras = extras;
results.toolboxInfo = toolboxInfo;

save(fullfile(outputDir, "matlab_foundation_workspace.mat"), "results");
end


function value = scalarNumeric(inputValue)
if isnumeric(inputValue)
    if isempty(inputValue)
        value = NaN;
    else
        value = double(inputValue(1));
    end
    return;
end

if iscell(inputValue)
    if isempty(inputValue)
        value = NaN;
    else
        value = scalarNumeric(inputValue{1});
    end
    return;
end

if isstring(inputValue) || ischar(inputValue)
    converted = str2double(string(inputValue));
    if isempty(converted)
        value = NaN;
    else
        value = converted(1);
    end
    return;
end

value = NaN;
end
