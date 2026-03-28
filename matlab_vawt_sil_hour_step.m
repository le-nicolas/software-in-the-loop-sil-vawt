function [ ...
    omegaNext, ...
    tsrMean, ...
    cpMean, ...
    aeroTorqueMeanNm, ...
    generatorTorqueMeanNm, ...
    brakeTorqueMeanNm, ...
    electricalPowerMeanKw, ...
    modeId, ...
    tsrErrorIntegralNext, ...
    lastTorqueNext] = matlab_vawt_sil_hour_step( ...
    windSpeedMs, airDensityKgm3, omegaPrev, tsrErrorIntegralPrev, lastTorquePrev)
%MATLAB_VAWT_SIL_HOUR_STEP One-hour SIL advance matching the current Python baseline.

c = matlab_vawt_constants();

windSpeedMs = max(double(windSpeedMs), 0.0);
airDensityKgm3 = max(double(airDensityKgm3), 0.1);
omega = max(double(omegaPrev), 0.0);
tsrErrorIntegral = double(tsrErrorIntegralPrev);
lastTorque = max(double(lastTorquePrev), 0.0);

previousTipSpeedRatio = localTipSpeedRatio(omega, windSpeedMs, c.rotorRadiusM);
previousCpEffective = localEvaluateCpCurve(previousTipSpeedRatio, c);
previousAerodynamicTorqueNm = 0.0;

substepsPerHour = max(1, round(c.secondsPerHour / c.secondsPerSubstep));
omegaLimit = c.maxRotorRpm * 2.0 * pi / 60.0;

cpAccumulator = 0.0;
tsrAccumulator = 0.0;
aeroTorqueAccumulator = 0.0;
generatorTorqueAccumulator = 0.0;
brakeTorqueAccumulator = 0.0;
energyAccumulatorKwh = 0.0;
modeCounts = zeros(1, 4);

for k = 1:substepsPerHour
    rotorRpm = omega * 60.0 / (2.0 * pi);
    windSpeed = max(windSpeedMs, 0.1);
    tsrMeasured = max(previousTipSpeedRatio, 0.0);
    cpMeasured = max(previousCpEffective, 0.0);
    aeroTorqueMeasured = max(previousAerodynamicTorqueNm, 0.0);

    generatorTorqueNm = 0.0;
    brakeCommandNm = 0.0;
    if windSpeedMs < c.cutInMs
        tsrErrorIntegral = 0.0;
        lastTorque = 0.0;
        modeIndex = 1;
    elseif windSpeedMs >= c.cutOutMs || ...
            (rotorRpm >= c.maxRotorRpm && tsrMeasured >= max(c.tsrOpt + 0.75, 3.25))
        tsrErrorIntegral = 0.0;
        lastTorque = 0.0;
        brakeCommandNm = c.brakeTorqueNm;
        modeIndex = 4;
    else
        targetOmega = c.tsrOpt * windSpeed / max(c.rotorRadiusM, 1.0e-6);
        targetTsr = targetOmega * c.rotorRadiusM / max(windSpeed, 0.1);
        tsrError = tsrMeasured - targetTsr;
        tsrErrorIntegral = min(max(tsrErrorIntegral + tsrError * c.secondsPerSubstep, -200.0), 200.0);

        cpFeedback = max(cpMeasured, 0.12 * c.cpGeneric);
        availablePowerW = 0.5 * airDensityKgm3 * c.sweptAreaM2 * cpFeedback * windSpeed^3;
        referenceOmega = max(targetOmega, 0.35);
        torqueFromCp = availablePowerW / referenceOmega;

        if aeroTorqueMeasured > 0.0
            baseTorque = 0.55 * torqueFromCp + 0.45 * aeroTorqueMeasured;
        else
            baseTorque = torqueFromCp;
        end

        torqueFeedback = 0.85 * tsrError + 0.012 * tsrErrorIntegral;
        generatorTorqueNm = max(0.0, baseTorque + torqueFeedback);

        if omega > 0.1
            ratedTorque = (c.ratedPowerKw * 1000.0) / max(omega * c.generatorEfficiency, 1.0e-6);
            generatorTorqueNm = min(generatorTorqueNm, ratedTorque);
        end

        if rotorRpm < c.startupRpmHandoff && ...
                tsrMeasured < c.startupTsrHandoff && ...
                cpMeasured < c.startupCpFloor
            generatorTorqueNm = 0.0;
            modeIndex = 2;
        else
            generatorTorqueNm = 0.65 * lastTorque + 0.35 * generatorTorqueNm;
            modeIndex = 3;
        end

        lastTorque = generatorTorqueNm;
    end

    currentTsr = localTipSpeedRatio(omega, windSpeed, c.rotorRadiusM);
    currentCp = 0.0;
    if windSpeedMs >= c.cutInMs
        currentCp = localEvaluateCpCurve(currentTsr, c);
    end

    aerodynamicPowerW = 0.5 * airDensityKgm3 * c.sweptAreaM2 * currentCp * windSpeed^3;
    startupTorqueNm = 0.5 * airDensityKgm3 * c.sweptAreaM2 * c.startupTorqueCoeff * windSpeed^2 * c.rotorRadiusM;
    omegaAero = max([omega, 0.3, 0.25 * c.tsrOpt * windSpeed / max(c.rotorRadiusM, 1.0e-6)]);
    aerodynamicTorqueNm = max(aerodynamicPowerW / max(omegaAero, 1.0e-6), startupTorqueNm);

    netTorqueNm = aerodynamicTorqueNm - generatorTorqueNm - brakeCommandNm - c.drivetrainDampingNms * omega;
    omega = min(max(0.0, omega + (netTorqueNm / max(c.rotorInertiaKgm2, 1.0e-6)) * c.secondsPerSubstep), omegaLimit);

    electricalPowerKw = min( ...
        c.ratedPowerKw, ...
        max(0.0, generatorTorqueNm * omega * c.generatorEfficiency / 1000.0));

    previousTipSpeedRatio = localTipSpeedRatio(omega, windSpeed, c.rotorRadiusM);
    if windSpeedMs >= c.cutInMs
        previousCpEffective = localEvaluateCpCurve(previousTipSpeedRatio, c);
    else
        previousCpEffective = 0.0;
    end
    previousAerodynamicTorqueNm = aerodynamicTorqueNm;

    cpAccumulator = cpAccumulator + previousCpEffective;
    tsrAccumulator = tsrAccumulator + previousTipSpeedRatio;
    aeroTorqueAccumulator = aeroTorqueAccumulator + aerodynamicTorqueNm;
    generatorTorqueAccumulator = generatorTorqueAccumulator + generatorTorqueNm;
    brakeTorqueAccumulator = brakeTorqueAccumulator + brakeCommandNm;
    energyAccumulatorKwh = energyAccumulatorKwh + electricalPowerKw * (c.secondsPerSubstep / c.secondsPerHour);
    modeCounts(modeIndex) = modeCounts(modeIndex) + 1;
end

[~, modeId] = max(modeCounts);

omegaNext = omega;
tsrMean = tsrAccumulator / substepsPerHour;
cpMean = cpAccumulator / substepsPerHour;
aeroTorqueMeanNm = aeroTorqueAccumulator / substepsPerHour;
generatorTorqueMeanNm = generatorTorqueAccumulator / substepsPerHour;
brakeTorqueMeanNm = brakeTorqueAccumulator / substepsPerHour;
electricalPowerMeanKw = energyAccumulatorKwh;
tsrErrorIntegralNext = tsrErrorIntegral;
lastTorqueNext = lastTorque;

end


function tsr = localTipSpeedRatio(omega, windSpeed, rotorRadius)
if windSpeed <= 0.0
    tsr = 0.0;
else
    tsr = max(0.0, omega * rotorRadius / max(windSpeed, 0.1));
end
end


function cp = localEvaluateCpCurve(tsr, constants)
if tsr <= 0.0
    cp = 0.0;
    return;
end

widthScale = max(0.01, constants.tsrSpread / constants.baseTsrSpread);
shiftedTsr = constants.baseTsrOpt + ((tsr - constants.tsrOpt) / widthScale);
lookupCp = localLookupCp(shiftedTsr, constants.tsrCpLookup);
cp = max(0.0, lookupCp * (constants.cpGeneric / max(constants.baseCpGeneric, 1.0e-6)));
end


function cp = localLookupCp(tsr, lookup)
if tsr <= lookup(1, 1) || tsr >= lookup(end, 1)
    cp = 0.0;
    return;
end

cp = 0.0;
for i = 2:size(lookup, 1)
    if tsr > lookup(i, 1)
        continue;
    end

    x0 = lookup(i - 1, 1);
    x1 = lookup(i, 1);
    y0 = lookup(i - 1, 2);
    y1 = lookup(i, 2);
    t = (tsr - x0) / max(x1 - x0, 1.0e-6);
    cp = y0 + t * (y1 - y0);
    return;
end
end
