using UnityEngine;
using UnityEngine.UI;

namespace CDO.VAWT.Unity
{
    public class DirectionHistogram : MonoBehaviour
    {
        [SerializeField] private WindDecomposer decomposer;
        [SerializeField] private RawImage histogramImage;
        [SerializeField] private Text dominantSectorText;

        private Texture2D histogramTexture;

        private void Reset()
        {
            decomposer = FindObjectOfType<WindDecomposer>();
        }

        private void OnEnable()
        {
            if (decomposer != null)
            {
                decomposer.DecompositionUpdated += RebuildHistogram;
                if (decomposer.FrameCount > 0)
                {
                    RebuildHistogram();
                }
            }
        }

        private void OnDisable()
        {
            if (decomposer != null)
            {
                decomposer.DecompositionUpdated -= RebuildHistogram;
            }
        }

        private void OnDestroy()
        {
            if (histogramTexture != null)
            {
                Destroy(histogramTexture);
            }
        }

        private void RebuildHistogram()
        {
            if (decomposer == null || decomposer.FrameCount == 0)
            {
                return;
            }

            EnsureTexture();
            Clear(histogramTexture, new Color(0.96f, 0.97f, 0.98f, 1f));

            float[] cpSum = new float[36];
            float[] uSum = new float[36];
            int[] counts = new int[36];

            for (int i = 0; i < decomposer.FrameCount; i++)
            {
                WindFrameData frame = decomposer.GetFrame(i);
                int bin = Mathf.FloorToInt(Mathf.Repeat(frame.WindDirectionDeg, 360f) / 10f) % 36;
                cpSum[bin] += frame.CpEffective;
                uSum[bin] += frame.UMean;
                counts[bin]++;
            }

            float[] meanCp = new float[36];
            float[] meanU = new float[36];
            float bestScore = float.MinValue;
            int dominantBin = 0;

            for (int i = 0; i < 36; i++)
            {
                if (counts[i] <= 0)
                {
                    continue;
                }

                meanCp[i] = cpSum[i] / counts[i];
                meanU[i] = uSum[i] / counts[i];
                float score = meanCp[i] + 0.001f * meanU[i];
                if (score > bestScore)
                {
                    bestScore = score;
                    dominantBin = i;
                }
            }

            int[] top3 = Top3Indices(meanCp, meanU);
            DrawPolarHistogram(meanCp, meanU, top3);

            if (dominantSectorText != null)
            {
                dominantSectorText.text = $"Primary wind sector: {dominantBin * 10}-{dominantBin * 10 + 10}°";
            }

            histogramTexture.Apply();
        }

        private void DrawPolarHistogram(float[] meanCp, float[] meanU, int[] top3)
        {
            Vector2 center = new Vector2(histogramTexture.width * 0.5f, histogramTexture.height * 0.5f);
            float maxRadius = histogramTexture.width * 0.36f;
            float maxCp = 0.4f;

            for (int ring = 1; ring <= 4; ring++)
            {
                DrawCircle(center, maxRadius * ring / 4f, new Color(0.83f, 0.86f, 0.9f, 1f));
            }

            for (int bin = 0; bin < 36; bin++)
            {
                float angleDeg = 90f - (bin * 10f + 5f);
                float angleRad = angleDeg * Mathf.Deg2Rad;
                float length = Mathf.Lerp(8f, maxRadius, Mathf.Clamp01(meanCp[bin] / maxCp));
                float ux = Mathf.Cos(angleRad);
                float uy = Mathf.Sin(angleRad);

                Color barColor = Viridis(Mathf.Clamp01(meanU[bin] / 8f));
                DrawRadialBar(center, ux, uy, 14f, length, barColor);
            }

            for (int i = 0; i < top3.Length; i++)
            {
                int bin = top3[i];
                float angleDeg = 90f - (bin * 10f + 5f);
                float angleRad = angleDeg * Mathf.Deg2Rad;
                float length = Mathf.Lerp(8f, maxRadius, Mathf.Clamp01(meanCp[bin] / maxCp));
                Vector2 point = center + new Vector2(Mathf.Cos(angleRad), Mathf.Sin(angleRad)) * (length + 12f);
                DrawCircle(point, 4f, new Color(0.96f, 0.73f, 0.12f, 1f));
            }
        }

        private void DrawRadialBar(Vector2 center, float ux, float uy, float innerRadius, float outerRadius, Color color)
        {
            for (float r = innerRadius; r <= outerRadius; r += 1f)
            {
                Vector2 point = center + new Vector2(ux, uy) * r;
                SetPixelSafe(Mathf.RoundToInt(point.x), Mathf.RoundToInt(point.y), color);
            }
        }

        private void DrawCircle(Vector2 center, float radius, Color color)
        {
            int steps = Mathf.CeilToInt(radius * 6f);
            for (int i = 0; i < steps; i++)
            {
                float angle = (i / (float)steps) * Mathf.PI * 2f;
                int x = Mathf.RoundToInt(center.x + Mathf.Cos(angle) * radius);
                int y = Mathf.RoundToInt(center.y + Mathf.Sin(angle) * radius);
                SetPixelSafe(x, y, color);
            }
        }

        private static int[] Top3Indices(float[] meanCp, float[] meanU)
        {
            int[] top3 = { 0, 1, 2 };
            float[] scores = new float[36];
            for (int i = 0; i < 36; i++)
            {
                scores[i] = meanCp[i] + 0.001f * meanU[i];
            }

            for (int rank = 0; rank < 3; rank++)
            {
                float best = float.MinValue;
                int bestIndex = rank;
                for (int i = 0; i < 36; i++)
                {
                    bool alreadyChosen = false;
                    for (int j = 0; j < rank; j++)
                    {
                        if (top3[j] == i)
                        {
                            alreadyChosen = true;
                            break;
                        }
                    }

                    if (!alreadyChosen && scores[i] > best)
                    {
                        best = scores[i];
                        bestIndex = i;
                    }
                }

                top3[rank] = bestIndex;
            }

            return top3;
        }

        private void EnsureTexture()
        {
            if (histogramTexture != null)
            {
                return;
            }

            histogramTexture = new Texture2D(420, 420, TextureFormat.RGBA32, false)
            {
                wrapMode = TextureWrapMode.Clamp,
                filterMode = FilterMode.Bilinear
            };

            if (histogramImage != null)
            {
                histogramImage.texture = histogramTexture;
            }
        }

        private static void Clear(Texture2D texture, Color color)
        {
            Color[] pixels = texture.GetPixels();
            for (int i = 0; i < pixels.Length; i++)
            {
                pixels[i] = color;
            }

            texture.SetPixels(pixels);
        }

        private void SetPixelSafe(int x, int y, Color color)
        {
            if (x < 0 || y < 0 || x >= histogramTexture.width || y >= histogramTexture.height)
            {
                return;
            }

            histogramTexture.SetPixel(x, y, color);
        }

        private static Color Viridis(float t)
        {
            if (t < 0.33f)
            {
                return Color.Lerp(new Color(0.27f, 0.0f, 0.33f, 1f), new Color(0.13f, 0.57f, 0.55f, 1f), t / 0.33f);
            }

            if (t < 0.66f)
            {
                return Color.Lerp(new Color(0.13f, 0.57f, 0.55f, 1f), new Color(0.49f, 0.82f, 0.32f, 1f), (t - 0.33f) / 0.33f);
            }

            return Color.Lerp(new Color(0.49f, 0.82f, 0.32f, 1f), new Color(0.99f, 0.91f, 0.14f, 1f), (t - 0.66f) / 0.34f);
        }
    }
}
