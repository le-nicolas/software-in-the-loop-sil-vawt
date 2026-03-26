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
    }

    public class WindDecomposer : MonoBehaviour
    {
        [Header("Dependencies")]
        [SerializeField] private WindDataLoader dataLoader;

        [Header("Fixed Physics Defaults")]
        [SerializeField] private float rotorRadiusM = 0.75f;
        [SerializeField] private float sweptAreaM2 = 4.0f;
        [SerializeField] private float tsrOpt = 2.2f;
        [SerializeField] private float tsrSpread = 1.6f;
        [SerializeField] private float cpGeneric = 0.35f;
        [SerializeField] private float cutInMs = 2.5f;
        [SerializeField] private float rotorInertiaKgm2 = 12.0f;
        [SerializeField] private float drivetrainDampingNms = 0.08f;
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

            for (int i = 0; i < samples.Count; i++)
            {
                WindSample sample = samples[i];
                float uMean = sample.WindSpeed15mMs;
                float thetaDeg = Mathf.Repeat(sample.WindDirection10mDeg, 360f);
                float thetaRad = thetaDeg * Mathf.Deg2Rad;
                float sigmaU = 0.1f * uMean;
                float uPrime = sigmaU * NextGaussian(random);
                float omegaRadS = (tsrOpt * uMean) / Mathf.Max(rotorRadiusM, 0.0001f);
                float omegaCrossR = omegaRadS * rotorRadiusM;
                float tsr = uMean >= cutInMs ? (omegaRadS * rotorRadiusM) / Mathf.Max(uMean, 0.1f) : 0f;
                float cpEffective = 0f;

                if (uMean >= cutInMs)
                {
                    float ratio = (tsr - tsrOpt) / Mathf.Max(tsrSpread, 0.01f);
                    cpEffective = Mathf.Max(0f, cpGeneric * (1f - (ratio * ratio)));
                }

                float vRel = uMean + uPrime - omegaCrossR;

                frames[i] = new WindFrameData
                {
                    HourOfYear = sample.HourOfYear,
                    Season = sample.Season,
                    UMean = uMean,
                    WindDirectionDeg = thetaDeg,
                    ThetaRad = thetaRad,
                    AirDensity = sample.AirDensityKgm3,
                    SigmaU = sigmaU,
                    UPrime = uPrime,
                    OmegaRadS = omegaRadS,
                    OmegaCrossR = omegaCrossR,
                    Tsr = tsr,
                    CpEffective = cpEffective,
                    VRel = vRel,
                    VRelMagnitude = Mathf.Abs(vRel),
                };
            }

            DecompositionUpdated?.Invoke();
            Debug.Log($"WindDecomposer rebuilt {frames.Length} frame records.");
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
