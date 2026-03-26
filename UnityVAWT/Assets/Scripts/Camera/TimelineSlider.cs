using System;
using UnityEngine;
using UnityEngine.UI;

namespace CDO.VAWT.Unity
{
    public class TimelineSlider : MonoBehaviour
    {
        [SerializeField] private WindDecomposer decomposer;
        [SerializeField] private Slider timeline;
        [SerializeField] private Button playButton;
        [SerializeField] private Button pauseButton;
        [SerializeField] private Text currentHourLabel;
        [SerializeField] private Text speedLabel;
        [SerializeField] private float playbackFramesPerSecond = 10f;
        [SerializeField] private float playbackSpeedMultiplier = 1f;

        private float playbackAccumulator;

        public event Action<int> FrameChanged;

        public int CurrentFrameIndex { get; private set; }
        public bool IsPlaying { get; private set; }

        private void Reset()
        {
            decomposer = FindObjectOfType<WindDecomposer>();
        }

        private void Start()
        {
            if (playButton != null)
            {
                playButton.onClick.AddListener(Play);
            }

            if (pauseButton != null)
            {
                pauseButton.onClick.AddListener(Pause);
            }

            if (timeline != null)
            {
                timeline.onValueChanged.AddListener(HandleSliderChanged);
            }

            if (decomposer != null)
            {
                decomposer.DecompositionUpdated += ConfigureSlider;
                if (decomposer.FrameCount > 0)
                {
                    ConfigureSlider();
                }
            }

            UpdateLabels();
        }

        private void OnDestroy()
        {
            if (playButton != null)
            {
                playButton.onClick.RemoveListener(Play);
            }

            if (pauseButton != null)
            {
                pauseButton.onClick.RemoveListener(Pause);
            }

            if (timeline != null)
            {
                timeline.onValueChanged.RemoveListener(HandleSliderChanged);
            }

            if (decomposer != null)
            {
                decomposer.DecompositionUpdated -= ConfigureSlider;
            }
        }

        private void Update()
        {
            if (!IsPlaying || decomposer == null || decomposer.AnimatedFrameCount <= 1)
            {
                return;
            }

            playbackAccumulator += Time.deltaTime * playbackFramesPerSecond * playbackSpeedMultiplier;
            if (playbackAccumulator < 1f)
            {
                return;
            }

            int step = Mathf.FloorToInt(playbackAccumulator);
            playbackAccumulator -= step;
            SetFrame(CurrentFrameIndex + step);
        }

        public void Play()
        {
            IsPlaying = true;
        }

        public void Pause()
        {
            IsPlaying = false;
        }

        public void SetPlaybackSpeed(float multiplier)
        {
            playbackSpeedMultiplier = Mathf.Max(0.1f, multiplier);
            UpdateLabels();
        }

        public void SetFrame(int frameIndex)
        {
            if (decomposer == null || decomposer.AnimatedFrameCount == 0)
            {
                CurrentFrameIndex = 0;
                return;
            }

            int safeIndex = frameIndex % decomposer.AnimatedFrameCount;
            if (safeIndex < 0)
            {
                safeIndex += decomposer.AnimatedFrameCount;
            }

            CurrentFrameIndex = safeIndex;
            if (timeline != null)
            {
                timeline.SetValueWithoutNotify(CurrentFrameIndex);
            }

            UpdateLabels();
            FrameChanged?.Invoke(CurrentFrameIndex);
        }

        private void ConfigureSlider()
        {
            if (timeline != null)
            {
                timeline.minValue = 0;
                timeline.maxValue = Mathf.Max(0, decomposer.AnimatedFrameCount - 1);
                timeline.wholeNumbers = true;
                timeline.SetValueWithoutNotify(CurrentFrameIndex);
            }

            UpdateLabels();
        }

        private void HandleSliderChanged(float value)
        {
            SetFrame(Mathf.RoundToInt(value));
        }

        private void UpdateLabels()
        {
            if (currentHourLabel != null)
            {
                int hour = decomposer != null && decomposer.FrameCount > 0 ? decomposer.GetFrame(CurrentFrameIndex).HourOfYear : 0;
                currentHourLabel.text = $"Hour: {hour}";
            }

            if (speedLabel != null)
            {
                speedLabel.text = $"Speed: {playbackSpeedMultiplier:F1}x";
            }
        }
    }
}
