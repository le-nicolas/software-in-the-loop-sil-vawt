using UnityEngine;
using UnityEngine.UI;

namespace CDO.VAWT.Unity
{
    public class ParameterPanel : MonoBehaviour
    {
        [SerializeField] private WindDecomposer decomposer;
        [SerializeField] private CBFMonitor cbfMonitor;

        [Header("Sliders")]
        [SerializeField] private Slider tsrOptSlider;
        [SerializeField] private Slider tsrSpreadSlider;
        [SerializeField] private Slider cpGenericSlider;
        [SerializeField] private Slider alphaSlider;
        [SerializeField] private Slider playbackSpeedSlider;

        [Header("Labels")]
        [SerializeField] private Text tsrOptLabel;
        [SerializeField] private Text tsrSpreadLabel;
        [SerializeField] private Text cpGenericLabel;
        [SerializeField] private Text alphaLabel;
        [SerializeField] private Text playbackSpeedLabel;

        [Header("Optional Timeline")]
        [SerializeField] private TimelineSlider timelineSlider;

        private void Reset()
        {
            decomposer = FindFirstObjectByType<WindDecomposer>();
            cbfMonitor = FindFirstObjectByType<CBFMonitor>();
            timelineSlider = FindFirstObjectByType<TimelineSlider>();
        }

        private void Start()
        {
            BindSlider(tsrOptSlider, HandleParameterChanged);
            BindSlider(tsrSpreadSlider, HandleParameterChanged);
            BindSlider(cpGenericSlider, HandleParameterChanged);
            BindSlider(alphaSlider, HandleParameterChanged);
            BindSlider(playbackSpeedSlider, HandlePlaybackSpeedChanged);

            if (decomposer != null)
            {
                if (tsrOptSlider != null) tsrOptSlider.value = decomposer.TsrOpt;
                if (tsrSpreadSlider != null) tsrSpreadSlider.value = decomposer.TsrSpread;
                if (cpGenericSlider != null) cpGenericSlider.value = decomposer.CpGeneric;
            }

            if (alphaSlider != null)
            {
                alphaSlider.value = 0.3f;
            }

            if (playbackSpeedSlider != null)
            {
                playbackSpeedSlider.value = 1f;
            }

            HandleParameterChanged(0f);
            HandlePlaybackSpeedChanged(playbackSpeedSlider != null ? playbackSpeedSlider.value : 1f);
        }

        private void OnDestroy()
        {
            UnbindSlider(tsrOptSlider, HandleParameterChanged);
            UnbindSlider(tsrSpreadSlider, HandleParameterChanged);
            UnbindSlider(cpGenericSlider, HandleParameterChanged);
            UnbindSlider(alphaSlider, HandleParameterChanged);
            UnbindSlider(playbackSpeedSlider, HandlePlaybackSpeedChanged);
        }

        private void HandleParameterChanged(float _)
        {
            float tsrOpt = tsrOptSlider != null ? tsrOptSlider.value : 2.5f;
            float tsrSpread = tsrSpreadSlider != null ? tsrSpreadSlider.value : 1.85f;
            float cpGeneric = cpGenericSlider != null ? cpGenericSlider.value : 0.33f;
            float alpha = alphaSlider != null ? alphaSlider.value : 0.3f;

            if (decomposer != null)
            {
                decomposer.SetVisualizationParameters(tsrOpt, tsrSpread, cpGeneric);
            }

            if (cbfMonitor != null)
            {
                cbfMonitor.SetAlpha(alpha);
            }

            SetLabel(tsrOptLabel, $"TSR opt: {tsrOpt:F2}");
            SetLabel(tsrSpreadLabel, $"Lookup width: {tsrSpread:F2}");
            SetLabel(cpGenericLabel, $"Cp peak scale: {cpGeneric:F2}");
            SetLabel(alphaLabel, $"alpha: {alpha:F2}");
        }

        private void HandlePlaybackSpeedChanged(float value)
        {
            float speed = Mathf.Max(0.1f, value);
            if (timelineSlider != null)
            {
                timelineSlider.SetPlaybackSpeed(speed);
            }

            SetLabel(playbackSpeedLabel, $"Playback: {speed:F1}x");
        }

        private static void BindSlider(Slider slider, UnityEngine.Events.UnityAction<float> callback)
        {
            if (slider != null)
            {
                slider.onValueChanged.AddListener(callback);
            }
        }

        private static void UnbindSlider(Slider slider, UnityEngine.Events.UnityAction<float> callback)
        {
            if (slider != null)
            {
                slider.onValueChanged.RemoveListener(callback);
            }
        }

        private static void SetLabel(Text label, string value)
        {
            if (label != null)
            {
                label.text = value;
            }
        }
    }
}
