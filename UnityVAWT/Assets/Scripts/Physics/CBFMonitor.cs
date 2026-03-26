using System;
using System.Collections.Generic;
using UnityEngine;

namespace CDO.VAWT.Unity
{
    [Serializable]
    public struct CaptureFrameData
    {
        public float ParticleDensity;
        public float H;
        public float DhDt;
        public bool Alert;
        public int InnerCount;
        public int OuterCount;
    }

    public class CBFMonitor : MonoBehaviour
    {
        [SerializeField] private WindDecomposer decomposer;
        [SerializeField] private float alpha = 0.3f;
        [SerializeField] private float dtDataSeconds = 3600f;
        [SerializeField] private float dtVizSeconds = 0.5f;
        [SerializeField] private int particleCount = 80;
        [SerializeField] private int particleSeed = 314;

        private CaptureFrameData[] captureFrames = Array.Empty<CaptureFrameData>();
        private int dominantSectorStart;
        private int dominantSectorEnd;

        public event Action CaptureUpdated;

        public IReadOnlyList<CaptureFrameData> CaptureFrames => captureFrames;
        public int AlertHours { get; private set; }
        public int SavoniusActivationHours { get; private set; }
        public int DarrieusPrimeHours { get; private set; }
        public float MeanCp { get; private set; }
        public float MeanVRel { get; private set; }
        public float AnnualEnergyMWh { get; private set; }
        public string DominantSectorLabel => $"{dominantSectorStart}-{dominantSectorEnd}°";

        private void Reset()
        {
            decomposer = FindObjectOfType<WindDecomposer>();
        }

        private void OnEnable()
        {
            if (decomposer == null)
            {
                decomposer = FindObjectOfType<WindDecomposer>();
            }

            if (decomposer != null)
            {
                decomposer.DecompositionUpdated += HandleDecompositionUpdated;
                if (decomposer.FrameCount > 0)
                {
                    RebuildCapture();
                }
            }
        }

        private void OnDisable()
        {
            if (decomposer != null)
            {
                decomposer.DecompositionUpdated -= HandleDecompositionUpdated;
            }
        }

        public void SetAlpha(float newAlpha)
        {
            alpha = Mathf.Max(0.001f, newAlpha);
            if (decomposer != null && decomposer.FrameCount > 0)
            {
                RebuildCapture();
            }
        }

        public CaptureFrameData GetFrame(int index)
        {
            if (captureFrames.Length == 0)
            {
                return default;
            }

            int safeIndex = Mathf.Clamp(index, 0, captureFrames.Length - 1);
            return captureFrames[safeIndex];
        }

        private void HandleDecompositionUpdated()
        {
            RebuildCapture();
        }

        private void RebuildCapture()
        {
            IReadOnlyList<WindFrameData> frames = decomposer.Frames;
            int count = frames.Count;
            if (count == 0)
            {
                captureFrames = Array.Empty<CaptureFrameData>();
                CaptureUpdated?.Invoke();
                return;
            }

            captureFrames = new CaptureFrameData[count];

            Vector3[] particles = new Vector3[particleCount];
            System.Random random = new System.Random(particleSeed);
            InitializeParticles(frames[0].ThetaRad, particles, random, decomposer.RotorRadiusM);

            float previousH = 0f;
            for (int i = 0; i < count; i++)
            {
                WindFrameData frame = frames[i];

                if (i > 0)
                {
                    StepParticles(frame, particles, random, decomposer.RotorRadiusM);
                }

                int outerCount = 0;
                int innerCount = 0;
                float outerRadius = decomposer.RotorRadiusM;
                float innerRadius = outerRadius * 0.5f;

                for (int p = 0; p < particles.Length; p++)
                {
                    float radius = particles[p].magnitude;
                    if (radius <= outerRadius)
                    {
                        outerCount++;
                    }

                    if (radius <= innerRadius)
                    {
                        innerCount++;
                    }
                }

                float particleDensity = outerCount / Mathf.Max(1f, particleCount);
                float h = particleDensity * frame.CpEffective;
                float dhDt = i == 0 ? 0f : (h - previousH) / dtDataSeconds;
                bool alert = (dhDt + alpha * h) < 0f;

                captureFrames[i] = new CaptureFrameData
                {
                    ParticleDensity = particleDensity,
                    H = h,
                    DhDt = dhDt,
                    Alert = alert,
                    InnerCount = innerCount,
                    OuterCount = outerCount,
                };

                previousH = h;
            }

            ComputeSummary(frames);
            CaptureUpdated?.Invoke();
            Debug.Log($"CBFMonitor rebuilt {captureFrames.Length} capture states.");
        }

        private void ComputeSummary(IReadOnlyList<WindFrameData> frames)
        {
            float powerSumW = 0f;
            float cpSum = 0f;
            float vRelSum = 0f;
            AlertHours = 0;
            SavoniusActivationHours = 0;
            DarrieusPrimeHours = 0;

            float[] cpSumByBin = new float[36];
            float[] uSumByBin = new float[36];
            int[] countByBin = new int[36];

            for (int i = 0; i < frames.Count; i++)
            {
                WindFrameData frame = frames[i];
                CaptureFrameData capture = captureFrames[i];

                cpSum += frame.CpEffective;
                vRelSum += frame.VRelMagnitude;
                powerSumW += 0.5f * frame.AirDensity * decomposer.SweptAreaM2 * frame.UMean * frame.UMean * frame.UMean * frame.CpEffective;

                if (capture.Alert)
                {
                    AlertHours++;
                }

                bool savoniusCondition = capture.Alert || frame.VRelMagnitude < Mathf.Max(frame.UMean * 0.8f, 0.5f);
                if (savoniusCondition)
                {
                    SavoniusActivationHours++;
                }
                else if (frame.VRelMagnitude > frame.UMean * 0.8f)
                {
                    DarrieusPrimeHours++;
                }

                int bin = Mathf.FloorToInt(Mathf.Repeat(frame.WindDirectionDeg, 360f) / 10f) % 36;
                cpSumByBin[bin] += frame.CpEffective;
                uSumByBin[bin] += frame.UMean;
                countByBin[bin]++;
            }

            MeanCp = cpSum / Mathf.Max(1, frames.Count);
            MeanVRel = vRelSum / Mathf.Max(1, frames.Count);
            AnnualEnergyMWh = powerSumW / 1_000_000f;

            float bestScore = float.MinValue;
            int dominantBin = 0;
            for (int i = 0; i < 36; i++)
            {
                if (countByBin[i] == 0)
                {
                    continue;
                }

                float meanCp = cpSumByBin[i] / countByBin[i];
                float meanU = uSumByBin[i] / countByBin[i];
                float score = meanCp + 0.001f * meanU;
                if (score > bestScore)
                {
                    bestScore = score;
                    dominantBin = i;
                }
            }

            dominantSectorStart = dominantBin * 10;
            dominantSectorEnd = dominantSectorStart + 10;
        }

        private void InitializeParticles(float thetaRad, Vector3[] particles, System.Random random, float rotorRadius)
        {
            for (int i = 0; i < particles.Length; i++)
            {
                particles[i] = MakeParticle(thetaRad, random, rotorRadius);
            }
        }

        private void StepParticles(WindFrameData frame, Vector3[] particles, System.Random random, float rotorRadius)
        {
            Vector3 velocity = new Vector3(
                (frame.UMean + frame.UPrime) * Mathf.Cos(frame.ThetaRad),
                (frame.UMean + frame.UPrime) * Mathf.Sin(frame.ThetaRad),
                0.1f * frame.UPrime
            );

            for (int i = 0; i < particles.Length; i++)
            {
                particles[i] += velocity * dtVizSeconds;

                if (particles[i].magnitude > 2.5f * rotorRadius)
                {
                    particles[i] = MakeParticle(frame.ThetaRad, random, rotorRadius);
                }
            }
        }

        private static Vector3 MakeParticle(float thetaRad, System.Random random, float rotorRadius)
        {
            Vector3 particle = new Vector3(
                -3f * rotorRadius * Mathf.Cos(thetaRad),
                -3f * rotorRadius * Mathf.Sin(thetaRad),
                RandomRange(random, -0.8f * rotorRadius, 0.8f * rotorRadius)
            );

            Vector3 crosswind = new Vector3(-Mathf.Sin(thetaRad), Mathf.Cos(thetaRad), 0f);
            float lateral = RandomRange(random, -0.5f * rotorRadius, 0.5f * rotorRadius);
            particle += crosswind * lateral;
            return particle;
        }

        private static float RandomRange(System.Random random, float min, float max)
        {
            return min + ((float)random.NextDouble() * (max - min));
        }
    }
}
