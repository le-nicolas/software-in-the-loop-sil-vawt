using UnityEngine;
using UnityEngine.UI;

namespace CDO.VAWT.Unity
{
    public class HUDController : MonoBehaviour
    {
        [Header("Dependencies")]
        [SerializeField] private WindDecomposer decomposer;
        [SerializeField] private CBFMonitor cbfMonitor;
        [SerializeField] private VAWTParticles particles;
        [SerializeField] private RotorPhysics rotorPhysics;
        [SerializeField] private TimelineSlider timelineSlider;

        [Header("UI References")]
        [SerializeField] private Text statusText;
        [SerializeField] private Text alertText;
        [SerializeField] private Image alertBadge;
        [SerializeField] private RawImage captureGraphImage;
        [SerializeField] private RawImage decompositionGraphImage;

        private Texture2D captureTexture;
        private Texture2D decompositionTexture;
        private int lastFrameIndex = -1;

        private static readonly Color BackgroundColor = new Color(0.96f, 0.97f, 0.98f, 1f);

        private void Reset()
        {
            decomposer = FindFirstObjectByType<WindDecomposer>();
            cbfMonitor = FindFirstObjectByType<CBFMonitor>();
            particles = FindFirstObjectByType<VAWTParticles>();
            rotorPhysics = FindFirstObjectByType<RotorPhysics>();
            timelineSlider = FindFirstObjectByType<TimelineSlider>();
        }

        private void OnEnable()
        {
            if (decomposer != null)
            {
                decomposer.DecompositionUpdated += HandleDataChanged;
            }

            if (cbfMonitor != null)
            {
                cbfMonitor.CaptureUpdated += HandleDataChanged;
            }

            if (timelineSlider != null)
            {
                timelineSlider.FrameChanged += HandleFrameChanged;
            }

            HandleDataChanged();
        }

        private void OnDisable()
        {
            if (decomposer != null)
            {
                decomposer.DecompositionUpdated -= HandleDataChanged;
            }

            if (cbfMonitor != null)
            {
                cbfMonitor.CaptureUpdated -= HandleDataChanged;
            }

            if (timelineSlider != null)
            {
                timelineSlider.FrameChanged -= HandleFrameChanged;
            }
        }

        private void OnDestroy()
        {
            DestroyTexture(ref captureTexture);
            DestroyTexture(ref decompositionTexture);
        }

        private void Update()
        {
            int currentFrame = timelineSlider != null ? timelineSlider.CurrentFrameIndex : 0;
            if (currentFrame != lastFrameIndex)
            {
                Redraw(currentFrame);
                lastFrameIndex = currentFrame;
            }
        }

        private void HandleDataChanged()
        {
            lastFrameIndex = -1;
            Redraw(timelineSlider != null ? timelineSlider.CurrentFrameIndex : 0);
        }

        private void HandleFrameChanged(int frameIndex)
        {
            Redraw(frameIndex);
            lastFrameIndex = frameIndex;
        }

        private void Redraw(int frameIndex)
        {
            if (decomposer == null || cbfMonitor == null || decomposer.FrameCount == 0 || cbfMonitor.CaptureFrames.Count == 0)
            {
                return;
            }

            frameIndex = Mathf.Clamp(frameIndex, 0, decomposer.AnimatedFrameCount - 1);
            WindFrameData frame = decomposer.GetFrame(frameIndex);
            CaptureFrameData capture = cbfMonitor.GetFrame(frameIndex);

            if (statusText != null)
            {
                statusText.color = SeasonColor(frame.Season);
                statusText.text =
                    $"Hour {frame.HourOfYear}\n" +
                    $"Season: {frame.Season} | Mode: {frame.ControlMode}\n" +
                    $"U = {frame.UMean:F2} m/s | TSR = {frame.Tsr:F2} | Cp = {frame.CpEffective:F3} | RPM = {frame.RotorRpm:F1}\n" +
                    $"P = {frame.ElectricalPowerKw * 1000f:F0} W | Rated = {frame.RatedPowerKw * 1000f:F0} W | Cap = {(frame.AtRatedCap ? "yes" : "no")}\n" +
                    $"Aero tq = {frame.AerodynamicTorqueNm:F2} Nm | Gen tq = {frame.GeneratorTorqueNm:F2} Nm | Brake = {frame.BrakeTorqueNm:F2} Nm\n" +
                    $"u' = {frame.UPrime:F2} | w×r = {frame.OmegaCrossR:F2} | |v_rel| = {frame.VRelMagnitude:F2}\n" +
                    $"Inner particles = {(particles != null ? particles.GetInnerCount(frameIndex) : capture.InnerCount)} | " +
                    $"Outer particles = {(particles != null ? particles.GetOuterCount(frameIndex) : capture.OuterCount)}\n" +
                    $"Mean Cp = {cbfMonitor.MeanCp:F3} | Mean |v_rel| = {cbfMonitor.MeanVRel:F2} | Energy = {cbfMonitor.AnnualEnergyMWh:F2} MWh";
            }

            if (alertBadge != null)
            {
                alertBadge.color = capture.Alert ? new Color(0.86f, 0.13f, 0.13f, 1f) : new Color(0.12f, 0.72f, 0.34f, 0.9f);
            }

            if (alertText != null)
            {
                if (frame.ControlMode == "brake")
                {
                    alertText.text = "BRAKE: overspeed protection active";
                    alertText.color = new Color(0.86f, 0.13f, 0.13f, 1f);
                }
                else if (frame.ControlMode == "startup")
                {
                    alertText.text = "STARTUP: Savonius-assisted handoff zone";
                    alertText.color = new Color(0.95f, 0.6f, 0.1f, 1f);
                }
                else if (frame.AtRatedCap)
                {
                    alertText.text = "MPPT: rated cap reached";
                    alertText.color = new Color(0.12f, 0.38f, 0.95f, 1f);
                }
                else if (capture.Alert)
                {
                    alertText.text = "ALERT: Savonius needed";
                    alertText.color = new Color(0.86f, 0.13f, 0.13f, 1f);
                }
                else
                {
                    alertText.text = "MPPT: lift regime stable";
                    alertText.color = new Color(0.12f, 0.55f, 0.32f, 1f);
                }
            }

            DrawCaptureGraph(frameIndex);
            DrawDecompositionGraph(frameIndex);
        }

        private void DrawCaptureGraph(int frameIndex)
        {
            EnsureTexture(ref captureTexture, 512, 180, captureGraphImage);
            ClearTexture(captureTexture, BackgroundColor);

            int count = decomposer.AnimatedFrameCount;
            float maxH = 0.1f;
            for (int i = 0; i < count; i++)
            {
                maxH = Mathf.Max(maxH, cbfMonitor.GetFrame(i).H);
            }

            float scaleX = (captureTexture.width - 20f) / Mathf.Max(1, count - 1);
            float scaleY = (captureTexture.height - 20f) / Mathf.Max(0.1f, maxH + 0.05f);

            for (int i = 0; i < count; i++)
            {
                CaptureFrameData frame = cbfMonitor.GetFrame(i);
                if (!frame.Alert)
                {
                    continue;
                }

                int x = 10 + Mathf.RoundToInt(i * scaleX);
                int top = 10 + Mathf.RoundToInt(frame.H * scaleY);
                for (int y = 10; y <= top; y++)
                {
                    SetPixelSafe(captureTexture, x, y, new Color(1f, 0.65f, 0.65f, 1f));
                }
            }

            DrawLine(captureTexture, 10, 10 + Mathf.RoundToInt(0.1f * scaleY), captureTexture.width - 10, 10 + Mathf.RoundToInt(0.1f * scaleY), new Color(0.45f, 0.48f, 0.55f, 1f), dashed: true);

            for (int i = 1; i < count; i++)
            {
                int x0 = 10 + Mathf.RoundToInt((i - 1) * scaleX);
                int y0 = 10 + Mathf.RoundToInt(cbfMonitor.GetFrame(i - 1).H * scaleY);
                int x1 = 10 + Mathf.RoundToInt(i * scaleX);
                int y1 = 10 + Mathf.RoundToInt(cbfMonitor.GetFrame(i).H * scaleY);
                DrawLine(captureTexture, x0, y0, x1, y1, new Color(0.12f, 0.38f, 0.95f, 1f));
            }

            int currentX = 10 + Mathf.RoundToInt(frameIndex * scaleX);
            DrawLine(captureTexture, currentX, 10, currentX, captureTexture.height - 10, new Color(0.86f, 0.13f, 0.13f, 1f));
            captureTexture.Apply();
        }

        private void DrawDecompositionGraph(int frameIndex)
        {
            EnsureTexture(ref decompositionTexture, 512, 220, decompositionGraphImage);
            ClearTexture(decompositionTexture, BackgroundColor);

            int count = decomposer.AnimatedFrameCount;
            float minValue = -0.5f;
            float maxValue = 0.5f;
            for (int i = 0; i < count; i++)
            {
                WindFrameData frame = decomposer.GetFrame(i);
                minValue = Mathf.Min(minValue, frame.UPrime, frame.VRel);
                maxValue = Mathf.Max(maxValue, frame.UMean, frame.OmegaCrossR, frame.VRel);
            }

            float scaleX = (decompositionTexture.width - 20f) / Mathf.Max(1, count - 1);
            float scaleY = (decompositionTexture.height - 20f) / Mathf.Max(0.1f, maxValue - minValue);

            for (int i = 1; i < count; i++)
            {
                DrawSeriesLine(decompositionTexture, i - 1, i, scaleX, scaleY, minValue, decomposer.GetFrame(i - 1).UMean, decomposer.GetFrame(i).UMean, new Color(0.12f, 0.38f, 0.95f, 1f));
                DrawSeriesLine(decompositionTexture, i - 1, i, scaleX, scaleY, minValue, decomposer.GetFrame(i - 1).UPrime, decomposer.GetFrame(i).UPrime, new Color(0.95f, 0.47f, 0.13f, 1f));
                DrawSeriesLine(decompositionTexture, i - 1, i, scaleX, scaleY, minValue, decomposer.GetFrame(i - 1).OmegaCrossR, decomposer.GetFrame(i).OmegaCrossR, new Color(0.13f, 0.64f, 0.33f, 1f));
                DrawSeriesLine(decompositionTexture, i - 1, i, scaleX, scaleY, minValue, decomposer.GetFrame(i - 1).VRel, decomposer.GetFrame(i).VRel, new Color(0.06f, 0.08f, 0.1f, 1f));
            }

            int currentX = 10 + Mathf.RoundToInt(frameIndex * scaleX);
            DrawLine(decompositionTexture, currentX, 10, currentX, decompositionTexture.height - 10, new Color(0.86f, 0.13f, 0.13f, 1f));
            decompositionTexture.Apply();
        }

        private static void DrawSeriesLine(Texture2D texture, int index0, int index1, float scaleX, float scaleY, float minValue, float value0, float value1, Color color)
        {
            int x0 = 10 + Mathf.RoundToInt(index0 * scaleX);
            int y0 = 10 + Mathf.RoundToInt((value0 - minValue) * scaleY);
            int x1 = 10 + Mathf.RoundToInt(index1 * scaleX);
            int y1 = 10 + Mathf.RoundToInt((value1 - minValue) * scaleY);
            DrawLine(texture, x0, y0, x1, y1, color);
        }

        private static void EnsureTexture(ref Texture2D texture, int width, int height, RawImage target)
        {
            if (texture != null)
            {
                return;
            }

            texture = new Texture2D(width, height, TextureFormat.RGBA32, false)
            {
                wrapMode = TextureWrapMode.Clamp,
                filterMode = FilterMode.Bilinear
            };

            if (target != null)
            {
                target.texture = texture;
            }
        }

        private static void ClearTexture(Texture2D texture, Color color)
        {
            Color[] pixels = texture.GetPixels();
            for (int i = 0; i < pixels.Length; i++)
            {
                pixels[i] = color;
            }

            texture.SetPixels(pixels);
        }

        private static void DrawLine(Texture2D texture, int x0, int y0, int x1, int y1, Color color, bool dashed = false)
        {
            int dx = Mathf.Abs(x1 - x0);
            int dy = Mathf.Abs(y1 - y0);
            int sx = x0 < x1 ? 1 : -1;
            int sy = y0 < y1 ? 1 : -1;
            int err = dx - dy;
            int step = 0;

            while (true)
            {
                if (!dashed || (step / 4) % 2 == 0)
                {
                    SetPixelSafe(texture, x0, y0, color);
                }

                if (x0 == x1 && y0 == y1)
                {
                    break;
                }

                int e2 = 2 * err;
                if (e2 > -dy)
                {
                    err -= dy;
                    x0 += sx;
                }

                if (e2 < dx)
                {
                    err += dx;
                    y0 += sy;
                }

                step++;
            }
        }

        private static void SetPixelSafe(Texture2D texture, int x, int y, Color color)
        {
            if (x < 0 || x >= texture.width || y < 0 || y >= texture.height)
            {
                return;
            }

            texture.SetPixel(x, y, color);
        }

        private static void DestroyTexture(ref Texture2D texture)
        {
            if (texture == null)
            {
                return;
            }

            Object.Destroy(texture);
            texture = null;
        }

        private static Color SeasonColor(string season)
        {
            switch (season)
            {
                case "Amihan":
                    return new Color(0.12f, 0.38f, 0.95f, 1f);
                case "Habagat":
                    return new Color(0.12f, 0.62f, 0.32f, 1f);
                case "Transition_DryDown":
                    return new Color(0.95f, 0.6f, 0.1f, 1f);
                case "Transition_Rampup":
                    return new Color(0.46f, 0.24f, 0.86f, 1f);
                default:
                    return Color.black;
            }
        }
    }
}
