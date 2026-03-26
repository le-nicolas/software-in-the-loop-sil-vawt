using System;
using UnityEngine;

namespace CDO.VAWT.Unity
{
    [RequireComponent(typeof(ParticleSystem))]
    public class VAWTParticles : MonoBehaviour
    {
        [SerializeField] private WindDecomposer decomposer;
        [SerializeField] private TimelineSlider timelineSlider;
        [SerializeField] private ParticleSystem particleSystemComponent;
        [SerializeField] private LineRenderer windArrow;
        [SerializeField] private int particleCount = 80;
        [SerializeField] private float dtVizSeconds = 0.5f;
        [SerializeField] private int particleSeed = 314;

        private ParticleSystem.Particle[] particles;
        private Vector3[,] framePositions = new Vector3[0, 0];
        private int[] innerCounts = Array.Empty<int>();
        private int[] outerCounts = Array.Empty<int>();
        private float[] densities = Array.Empty<float>();
        private int lastFrameIndex = -1;
        private float maxVRel = 1f;

        public int CurrentInnerCount { get; private set; }
        public int CurrentOuterCount { get; private set; }
        public float CurrentParticleDensity { get; private set; }

        private void Reset()
        {
            decomposer = FindObjectOfType<WindDecomposer>();
            timelineSlider = FindObjectOfType<TimelineSlider>();
            particleSystemComponent = GetComponent<ParticleSystem>();
        }

        private void Awake()
        {
            if (particleSystemComponent == null)
            {
                particleSystemComponent = GetComponent<ParticleSystem>();
            }

            ConfigureParticleSystem();
            EnsureWindArrow();
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
                    RebuildParticleFrames();
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

        private void Update()
        {
            if (framePositions.Length == 0)
            {
                return;
            }

            int frameIndex = timelineSlider != null ? timelineSlider.CurrentFrameIndex : 0;
            frameIndex = Mathf.Clamp(frameIndex, 0, framePositions.GetLength(0) - 1);

            if (frameIndex != lastFrameIndex)
            {
                DisplayFrame(frameIndex);
                lastFrameIndex = frameIndex;
            }
        }

        public int GetInnerCount(int frameIndex)
        {
            if (innerCounts.Length == 0)
            {
                return 0;
            }

            return innerCounts[Mathf.Clamp(frameIndex, 0, innerCounts.Length - 1)];
        }

        public int GetOuterCount(int frameIndex)
        {
            if (outerCounts.Length == 0)
            {
                return 0;
            }

            return outerCounts[Mathf.Clamp(frameIndex, 0, outerCounts.Length - 1)];
        }

        public float GetDensity(int frameIndex)
        {
            if (densities.Length == 0)
            {
                return 0f;
            }

            return densities[Mathf.Clamp(frameIndex, 0, densities.Length - 1)];
        }

        private void HandleDecompositionUpdated()
        {
            RebuildParticleFrames();
            lastFrameIndex = -1;
        }

        private void RebuildParticleFrames()
        {
            int frameCount = decomposer.AnimatedFrameCount;
            if (frameCount <= 0)
            {
                framePositions = new Vector3[0, 0];
                innerCounts = Array.Empty<int>();
                outerCounts = Array.Empty<int>();
                densities = Array.Empty<float>();
                return;
            }

            framePositions = new Vector3[frameCount, particleCount];
            innerCounts = new int[frameCount];
            outerCounts = new int[frameCount];
            densities = new float[frameCount];
            particles = new ParticleSystem.Particle[particleCount];

            for (int i = 0; i < particleCount; i++)
            {
                particles[i].remainingLifetime = 9999f;
                particles[i].startLifetime = 9999f;
            }

            System.Random random = new System.Random(particleSeed);
            Vector3[] working = new Vector3[particleCount];
            float radius = decomposer.RotorRadiusM;

            WindFrameData firstFrame = decomposer.GetFrame(0);
            for (int i = 0; i < particleCount; i++)
            {
                working[i] = MakeParticle(firstFrame.ThetaRad, random, radius);
            }

            maxVRel = 1f;
            for (int f = 0; f < frameCount; f++)
            {
                WindFrameData frame = decomposer.GetFrame(f);
                maxVRel = Mathf.Max(maxVRel, frame.VRelMagnitude);

                if (f > 0)
                {
                    Vector3 velocity = new Vector3(
                        (frame.UMean + frame.UPrime) * Mathf.Cos(frame.ThetaRad),
                        (frame.UMean + frame.UPrime) * Mathf.Sin(frame.ThetaRad),
                        0.1f * frame.UPrime
                    );

                    for (int i = 0; i < particleCount; i++)
                    {
                        working[i] += velocity * dtVizSeconds;
                        if (working[i].magnitude > 2.5f * radius)
                        {
                            working[i] = MakeParticle(frame.ThetaRad, random, radius);
                        }
                    }
                }

                int inner = 0;
                int outer = 0;
                for (int i = 0; i < particleCount; i++)
                {
                    framePositions[f, i] = working[i];
                    float particleRadius = working[i].magnitude;
                    if (particleRadius <= radius)
                    {
                        outer++;
                    }

                    if (particleRadius <= radius * 0.5f)
                    {
                        inner++;
                    }
                }

                innerCounts[f] = inner;
                outerCounts[f] = outer;
                densities[f] = outer / Mathf.Max(1f, particleCount);
            }
        }

        private void DisplayFrame(int frameIndex)
        {
            WindFrameData frame = decomposer.GetFrame(frameIndex);
            float normalized = Mathf.Clamp01(frame.VRelMagnitude / Mathf.Max(maxVRel, 0.001f));
            Color particleColor = EvaluateParticleColor(normalized);
            float particleSize = Mathf.Lerp(0.06f, 0.16f, normalized);

            for (int i = 0; i < particleCount; i++)
            {
                particles[i].position = framePositions[frameIndex, i];
                particles[i].startColor = particleColor;
                particles[i].startSize = particleSize;
            }

            particleSystemComponent.SetParticles(particles, particleCount);
            UpdateArrow(frame);

            CurrentInnerCount = innerCounts[frameIndex];
            CurrentOuterCount = outerCounts[frameIndex];
            CurrentParticleDensity = densities[frameIndex];
        }

        private void ConfigureParticleSystem()
        {
            ParticleSystem.MainModule main = particleSystemComponent.main;
            main.maxParticles = particleCount;
            main.startLifetime = 9999f;
            main.loop = false;
            main.playOnAwake = false;
            main.simulationSpace = ParticleSystemSimulationSpace.Local;
            main.startSpeed = 0f;

            ParticleSystem.EmissionModule emission = particleSystemComponent.emission;
            emission.enabled = false;

            ParticleSystem.ShapeModule shape = particleSystemComponent.shape;
            shape.enabled = false;
        }

        private void EnsureWindArrow()
        {
            if (windArrow != null)
            {
                return;
            }

            GameObject arrowObject = new GameObject("WindArrow");
            arrowObject.transform.SetParent(transform, false);
            windArrow = arrowObject.AddComponent<LineRenderer>();
            windArrow.positionCount = 2;
            windArrow.useWorldSpace = false;
            windArrow.widthMultiplier = 0.03f;
            windArrow.material = new Material(Shader.Find("Sprites/Default"));
            windArrow.startColor = Color.black;
            windArrow.endColor = Color.black;
        }

        private void UpdateArrow(WindFrameData frame)
        {
            Vector3 start = new Vector3(
                -2f * decomposer.RotorRadiusM * Mathf.Cos(frame.ThetaRad),
                0f,
                -2f * decomposer.RotorRadiusM * Mathf.Sin(frame.ThetaRad)
            );
            Vector3 end = start + new Vector3(
                0.6f * (frame.UMean + frame.UPrime) * Mathf.Cos(frame.ThetaRad),
                0f,
                0.6f * (frame.UMean + frame.UPrime) * Mathf.Sin(frame.ThetaRad)
            );

            windArrow.SetPosition(0, start);
            windArrow.SetPosition(1, end);
        }

        private static Vector3 MakeParticle(float thetaRad, System.Random random, float rotorRadius)
        {
            Vector3 particle = new Vector3(
                -3f * rotorRadius * Mathf.Cos(thetaRad),
                RandomRange(random, -0.8f * rotorRadius, 0.8f * rotorRadius),
                -3f * rotorRadius * Mathf.Sin(thetaRad)
            );

            Vector3 crosswind = new Vector3(-Mathf.Sin(thetaRad), 0f, Mathf.Cos(thetaRad));
            float lateral = RandomRange(random, -0.5f * rotorRadius, 0.5f * rotorRadius);
            particle += crosswind * lateral;
            return particle;
        }

        private static float RandomRange(System.Random random, float min, float max)
        {
            return min + ((float)random.NextDouble() * (max - min));
        }

        private static Color EvaluateParticleColor(float t)
        {
            if (t < 0.33f)
            {
                return Color.Lerp(new Color(0f, 0f, 0.5f), Color.cyan, t / 0.33f);
            }

            if (t < 0.66f)
            {
                return Color.Lerp(Color.cyan, Color.yellow, (t - 0.33f) / 0.33f);
            }

            return Color.Lerp(Color.yellow, Color.red, (t - 0.66f) / 0.34f);
        }
    }
}
