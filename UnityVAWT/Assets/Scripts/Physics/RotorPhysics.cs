using UnityEngine;

namespace CDO.VAWT.Unity
{
    public class RotorPhysics : MonoBehaviour
    {
        [SerializeField] private WindDecomposer decomposer;
        [SerializeField] private TimelineSlider timelineSlider;
        [SerializeField] private Transform rotorRoot;
        [SerializeField] private float responseSharpness = 8f;
        [SerializeField] private Vector3 spinAxis = Vector3.up;

        public float CurrentOmegaRadS { get; private set; }
        public float CurrentCp { get; private set; }
        public float CurrentTsr { get; private set; }
        public float CurrentPowerW { get; private set; }

        private void Reset()
        {
            decomposer = FindObjectOfType<WindDecomposer>();
            timelineSlider = FindObjectOfType<TimelineSlider>();
        }

        private void Update()
        {
            if (decomposer == null || decomposer.FrameCount == 0)
            {
                return;
            }

            int frameIndex = timelineSlider != null ? timelineSlider.CurrentFrameIndex : 0;
            WindFrameData frame = decomposer.GetFrame(frameIndex);

            CurrentCp = frame.CpEffective;
            CurrentTsr = frame.Tsr;
            CurrentPowerW = 0.5f * frame.AirDensity * decomposer.SweptAreaM2 * frame.UMean * frame.UMean * frame.UMean * frame.CpEffective;

            float targetOmega = frame.OmegaRadS;
            CurrentOmegaRadS = Mathf.Lerp(CurrentOmegaRadS, targetOmega, 1f - Mathf.Exp(-responseSharpness * Time.deltaTime));

            if (rotorRoot != null)
            {
                float deltaDegrees = CurrentOmegaRadS * Mathf.Rad2Deg * Time.deltaTime;
                rotorRoot.Rotate(spinAxis, deltaDegrees, Space.Self);
            }
        }
    }
}
