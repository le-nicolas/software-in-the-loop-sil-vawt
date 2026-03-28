using System;
using System.Collections.Generic;
using UnityEngine;

namespace CDO.VAWT.Unity
{
    [Serializable]
    public struct WindFrameData
    {
        public int HourOfYear;
        public string Season;
        public float UMean;
        public float WindDirectionDeg;
        public float ThetaRad;
        public float AirDensity;
        public float SigmaU;
        public float UPrime;
        public float OmegaRadS;
        public float OmegaCrossR;
        public float Tsr;
        public float CpEffective;
        public float VRel;
        public float VRelMagnitude;
        public float RotorRpm;
        public float AerodynamicTorqueNm;
        public float GeneratorTorqueNm;
        public float BrakeTorqueNm;
        public float ElectricalPowerKw;
        public float RatedPowerKw;
        public bool AtRatedCap;
        public string ControlMode;
    }

    public class WindDecomposer : MonoBehaviour
    {
        private const float BaseTsrOpt = 2.5f;
        private const float BaseTsrSpread = 1.85f;
        private const float BaseCpGeneric = 0.33f;

        private static readonly Vector2[] TsrCpLookup =
        {
            new Vector2(0.0f, 0.00f),
            new Vector2(0.1f, 0.03f),
            new Vector2(0.3f, 0.05f),
            new Vector2(0.5f, 0.07f),
            new Vector2(0.8f, 0.12f),
            new Vector2(1.0f, 0.16f),
            new Vector2(1.5f, 0.20f),
            new Vector2(2.0f, 0.28f),
            new Vector2(2.5f, 0.33f),
            new Vector2(3.0f, 0.28f),
            new Vector2(3.5f, 0.15f),
            new Vector2(4.0f, 0.00f),
        };

        [Header("Dependencies")]
        [SerializeField] private WindDataLoader dataLoader;

        [Header("Fixed Physics Defaults")]
        [SerializeField] private float rotorRadiusM = 0.75f;
        [SerializeField] private float sweptAreaM2 = 4.0f;
        [SerializeField] private float tsrOpt = 2.5f;
        [SerializeField] private float tsrSpread = 1.85f;
        [SerializeField] private float cpGeneric = 0.33f;
        [SerializeField] private float cutInMs = 2.5f;
        [SerializeField] private float cutOutMs = 25.0f;
        [SerializeField] private float rotorInertiaKgm2 = 12.0f;
        [SerializeField] private float drivetrainDampingNms = 0.08f;
        [SerializeField] private float generatorEfficiency = 0.9f;
        [SerializeField] private float ratedPowerKw = 0.38f;
        [SerializeField] private float maxRotorRpm = 220.0f;
        [SerializeField] private float startupTorqueCoeff = 0.12f;
        [SerializeField] private float brakeTorqueNm = 18.0f;
        [SerializeField] private float startupRpmHandoff = 8.0f;
        [SerializeField] private float startupTsrHandoff = 0.25f;
        [SerializeField] private float startupCpFloor = 0.02f;
        [SerializeField] private float secondsPerSubstep = 60.0f;
        [SerializeField] private float standardAirDensity = 1.225f;
        [SerializeField] private int turbulenceSeed = 42;

        private WindFrameData[] frames = Array.Empty<WindFrameData>();

        public event Action DecompositionUpdated;

        public IReadOnlyList<WindFrameData> Frames => frames;
        public int FrameCount => frames.Length;
        public int AnimatedFrameCount => Mathf.Min(720, FrameCount);

        public float RotorRadiusM => rotorRadiusM;
        public float SweptAreaM2 => sweptAreaM2;
        public float RotorInertiaKgm2 => rotorInertiaKgm2;
        public float DrivetrainDampingNms => drivetrainDampingNms;
        public float StandardAirDensity => standardAirDensity;
        public float TsrOpt => tsrOpt;
        public float TsrSpread => tsrSpread;
        public float CpGeneric => cpGeneric;
        public float CutInMs => cutInMs;
        public float RatedPowerKw => ratedPowerKw;

        private void Reset()
        {
            dataLoader = FindObjectOfType<WindDataLoader>();
        }

        private void OnEnable()
        {
            if (dataLoader == null)
            {
                dataLoader = FindObjectOfType<WindDataLoader>();
            }

            if (dataLoader != null)
            {
                dataLoader.DataLoaded += HandleDataLoaded;
                if (dataLoader.IsLoaded)
                {
                    RebuildFromSamples(dataLoader.Samples);
                }
            }
        }

        private void OnDisable()
        {
            if (dataLoader != null)
            {
                dataLoader.DataLoaded -= HandleDataLoaded;
            }
        }

        public WindFrameData GetFrame(int index)
        {
            if (frames.Length == 0)
            {
                return default;
            }

            int safeIndex = Mathf.Clamp(index, 0, frames.Length - 1);
            return frames[safeIndex];
        }

        public void SetVisualizationParameters(float newTsrOpt, float newTsrSpread, float newCpGeneric)
        {
            tsrOpt = newTsrOpt;
            tsrSpread = Mathf.Max(0.01f, newTsrSpread);
            cpGeneric = Mathf.Max(0.0f, newCpGeneric);

            if (dataLoader != null && dataLoader.IsLoaded)
            {
                RebuildFromSamples(dataLoader.Samples);
            }
        }

        private void HandleDataLoaded(IReadOnlyList<WindSample> samples)
        {
            RebuildFromSamples(samples);
        }

        private void RebuildFromSamples(IReadOnlyList<WindSample> samples)
        {
            if (samples == null || samples.Count == 0)
            {
                frames = Array.Empty<WindFrameData>();
                DecompositionUpdated?.Invoke();
                return;
            }

            frames = new WindFrameData[samples.Count];
            System.Random random = new System.Random(turbulenceSeed);
            float omega = 0f;
            float previousTipSpeedRatio = 0f;
            float previousCpEffective = 0f;
            float previousAerodynamicTorqueNm = 0f;
            float tsrErrorIntegral = 0f;
            float lastGeneratorTorqueNm = 0f;
            float omegaLimit = maxRotorRpm * 2f * Mathf.PI / 60f;
            int substepsPerHour = Mathf.Max(1, Mathf.RoundToInt(3600f / Mathf.Max(1f, secondsPerSubstep)));

            for (int i = 0; i < samples.Count; i++)
            {
                WindSample sample = samples[i];
                float uMean = sample.WindSpeed15mMs;
                float thetaDeg = Mathf.Repeat(sample.WindDirection10mDeg, 360f);
                float thetaRad = thetaDeg * Mathf.Deg2Rad;
                float sigmaU = 0.1f * uMean;
                float uPrime = sigmaU * NextGaussian(random);
                float airDensity = sample.AirDensityKgm3 > 0f ? sample.AirDensityKgm3 : standardAirDensity;

                float hourlyEnergyKwh = 0f;
                float cpSum = 0f;
                float tsrSum = 0f;
                float aerodynamicTorqueSum = 0f;
                float generatorTorqueSum = 0f;
                float brakeTorqueSum = 0f;
                float peakElectricalPowerKw = 0f;
                Dictionary<string, int> modeCounts = new Dictionary<string, int>(StringComparer.Ordinal);

                for (int step = 0; step < substepsPerHour; step++)
                {
                    float rotorRpm = omega * 60f / (2f * Mathf.PI);
                    float windSpeed = Mathf.Max(uMean, 0.1f);
                    float tsrMeasured = Mathf.Max(0f, previousTipSpeedRatio);
                    float cpMeasured = Mathf.Max(0f, previousCpEffective);
                    float aerodynamicTorqueMeasured = Mathf.Max(0f, previousAerodynamicTorqueNm);

                    float generatorTorqueNm = 0f;
                    float brakeCommandNm = 0f;
                    string mode;

                    if (uMean < cutInMs)
                    {
                        tsrErrorIntegral = 0f;
                        lastGeneratorTorqueNm = 0f;
                        mode = "idle";
                    }
                    else if (uMean >= cutOutMs || (rotorRpm >= maxRotorRpm && tsrMeasured >= Mathf.Max(tsrOpt + 0.75f, 3.25f)))
                    {
                        tsrErrorIntegral = 0f;
                        lastGeneratorTorqueNm = 0f;
                        brakeCommandNm = brakeTorqueNm;
                        mode = "brake";
                    }
                    else
                    {
                        float targetOmega = tsrOpt * windSpeed / Mathf.Max(rotorRadiusM, 0.0001f);
                        float targetTsr = targetOmega * rotorRadiusM / Mathf.Max(windSpeed, 0.1f);
                        float tsrError = tsrMeasured - targetTsr;
                        tsrErrorIntegral = Mathf.Clamp(tsrErrorIntegral + (tsrError * 60f), -200f, 200f);

                        float cpFeedback = Mathf.Max(cpMeasured, 0.12f * cpGeneric);
                        float availablePowerW = 0.5f * airDensity * sweptAreaM2 * cpFeedback * windSpeed * windSpeed * windSpeed;
                        float referenceOmega = Mathf.Max(targetOmega, 0.35f);
                        float torqueFromCp = availablePowerW / referenceOmega;
                        float baseTorque = aerodynamicTorqueMeasured > 0f
                            ? (0.55f * torqueFromCp) + (0.45f * aerodynamicTorqueMeasured)
                            : torqueFromCp;

                        float torqueFeedback = (0.85f * tsrError) + (0.012f * tsrErrorIntegral);
                        generatorTorqueNm = Mathf.Max(0f, baseTorque + torqueFeedback);

                        if (omega > 0.1f)
                        {
                            float ratedTorque = (ratedPowerKw * 1000f) / Mathf.Max(omega * generatorEfficiency, 0.000001f);
                            generatorTorqueNm = Mathf.Min(generatorTorqueNm, ratedTorque);
                        }

                        if (rotorRpm < startupRpmHandoff && tsrMeasured < startupTsrHandoff && cpMeasured < startupCpFloor)
                        {
                            generatorTorqueNm = 0f;
                            mode = "startup";
                        }
                        else
                        {
                            generatorTorqueNm = (0.65f * lastGeneratorTorqueNm) + (0.35f * generatorTorqueNm);
                            mode = "adaptive_mppt";
                        }

                        lastGeneratorTorqueNm = generatorTorqueNm;
                    }

                    float currentTsr = windSpeed > 0f ? (omega * rotorRadiusM) / windSpeed : 0f;
                    float currentCp = uMean >= cutInMs ? EvaluateCpCurve(currentTsr) : 0f;
                    float aerodynamicPowerW = 0.5f * airDensity * sweptAreaM2 * currentCp * windSpeed * windSpeed * windSpeed;
                    float startupTorqueNm = 0.5f * airDensity * sweptAreaM2 * startupTorqueCoeff * windSpeed * windSpeed * rotorRadiusM;
                    float omegaAero = Mathf.Max(omega, Mathf.Max(0.3f, 0.25f * tsrOpt * windSpeed / Mathf.Max(rotorRadiusM, 0.0001f)));
                    float aerodynamicTorqueNm = Mathf.Max(aerodynamicPowerW / Mathf.Max(omegaAero, 0.0001f), startupTorqueNm);

                    float netTorqueNm =
                        aerodynamicTorqueNm
                        - generatorTorqueNm
                        - brakeCommandNm
                        - (drivetrainDampingNms * omega);

                    omega = Mathf.Clamp(omega + ((netTorqueNm / Mathf.Max(rotorInertiaKgm2, 0.0001f)) * secondsPerSubstep), 0f, omegaLimit);

                    float electricalPowerKw = Mathf.Min(
                        ratedPowerKw,
                        Mathf.Max(0f, generatorTorqueNm * omega * generatorEfficiency / 1000f)
                    );

                    previousTipSpeedRatio = windSpeed > 0f ? (omega * rotorRadiusM) / windSpeed : 0f;
                    previousCpEffective = uMean >= cutInMs ? EvaluateCpCurve(previousTipSpeedRatio) : 0f;
                    previousAerodynamicTorqueNm = aerodynamicTorqueNm;

                    hourlyEnergyKwh += electricalPowerKw * (secondsPerSubstep / 3600f);
                    cpSum += previousCpEffective;
                    tsrSum += previousTipSpeedRatio;
                    aerodynamicTorqueSum += aerodynamicTorqueNm;
                    generatorTorqueSum += generatorTorqueNm;
                    brakeTorqueSum += brakeCommandNm;
                    peakElectricalPowerKw = Mathf.Max(peakElectricalPowerKw, electricalPowerKw);

                    if (!modeCounts.ContainsKey(mode))
                    {
                        modeCounts[mode] = 0;
                    }

                    modeCounts[mode]++;
                }

                float meanCpEffective = cpSum / substepsPerHour;
                float meanTsr = tsrSum / substepsPerHour;
                float meanAerodynamicTorqueNm = aerodynamicTorqueSum / substepsPerHour;
                float meanGeneratorTorqueNm = generatorTorqueSum / substepsPerHour;
                float meanBrakeTorqueNm = brakeTorqueSum / substepsPerHour;
                float meanElectricalPowerKw = hourlyEnergyKwh;
                float omegaRadS = omega;
                float omegaCrossR = omegaRadS * rotorRadiusM;
                float vRel = uMean + uPrime - omegaCrossR;
                string dominantMode = SelectDominantMode(modeCounts);

                frames[i] = new WindFrameData
                {
                    HourOfYear = sample.HourOfYear,
                    Season = sample.Season,
                    UMean = uMean,
                    WindDirectionDeg = thetaDeg,
                    ThetaRad = thetaRad,
                    AirDensity = airDensity,
                    SigmaU = sigmaU,
                    UPrime = uPrime,
                    OmegaRadS = omegaRadS,
                    OmegaCrossR = omegaCrossR,
                    Tsr = meanTsr,
                    CpEffective = meanCpEffective,
                    VRel = vRel,
                    VRelMagnitude = Mathf.Abs(vRel),
                    RotorRpm = omegaRadS * 60f / (2f * Mathf.PI),
                    AerodynamicTorqueNm = meanAerodynamicTorqueNm,
                    GeneratorTorqueNm = meanGeneratorTorqueNm,
                    BrakeTorqueNm = meanBrakeTorqueNm,
                    ElectricalPowerKw = meanElectricalPowerKw,
                    RatedPowerKw = ratedPowerKw,
                    AtRatedCap = peakElectricalPowerKw >= (ratedPowerKw - 0.0005f),
                    ControlMode = dominantMode,
                };
            }

            DecompositionUpdated?.Invoke();
            Debug.Log($"WindDecomposer rebuilt {frames.Length} frame records.");
        }

        private float EvaluateCpCurve(float tsr)
        {
            if (tsr <= 0f)
            {
                return 0f;
            }

            float widthScale = Mathf.Max(0.01f, tsrSpread / BaseTsrSpread);
            float shiftedTsr = BaseTsrOpt + ((tsr - tsrOpt) / widthScale);
            float cp = InterpolateLookup(shiftedTsr);
            return Mathf.Max(0f, cp * (cpGeneric / Mathf.Max(BaseCpGeneric, 0.0001f)));
        }

        private static float InterpolateLookup(float tsr)
        {
            if (tsr <= TsrCpLookup[0].x || tsr >= TsrCpLookup[TsrCpLookup.Length - 1].x)
            {
                return 0f;
            }

            for (int i = 1; i < TsrCpLookup.Length; i++)
            {
                Vector2 right = TsrCpLookup[i];
                if (tsr > right.x)
                {
                    continue;
                }

                Vector2 left = TsrCpLookup[i - 1];
                float t = Mathf.InverseLerp(left.x, right.x, tsr);
                return Mathf.Lerp(left.y, right.y, t);
            }

            return 0f;
        }

        private static string SelectDominantMode(Dictionary<string, int> modeCounts)
        {
            string dominantMode = "idle";
            int dominantCount = -1;
            foreach (KeyValuePair<string, int> pair in modeCounts)
            {
                if (pair.Value <= dominantCount)
                {
                    continue;
                }

                dominantMode = pair.Key;
                dominantCount = pair.Value;
            }

            return dominantMode;
        }

        private static float NextGaussian(System.Random random)
        {
            float u1 = 1f - (float)random.NextDouble();
            float u2 = 1f - (float)random.NextDouble();
            float radius = Mathf.Sqrt(-2f * Mathf.Log(u1));
            float theta = 2f * Mathf.PI * u2;
            return radius * Mathf.Cos(theta);
        }
    }
}
