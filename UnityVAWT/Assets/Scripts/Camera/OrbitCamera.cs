using UnityEngine;
using UnityEngine.InputSystem;

namespace CDO.VAWT.Unity
{
    public class OrbitCamera : MonoBehaviour
    {
        private const float MouseDeltaScale = 0.05f;
        private const float ScrollDeltaScale = 0.005f;

        [SerializeField] private Transform target;
        [SerializeField] private float distance = 4f;
        [SerializeField] private float minDistance = 1.8f;
        [SerializeField] private float maxDistance = 8f;
        [SerializeField] private float orbitSpeed = 120f;
        [SerializeField] private float zoomSpeed = 4f;
        [SerializeField] private float pitch = 25f;
        [SerializeField] private float yaw = 35f;

        private void LateUpdate()
        {
            if (target == null)
            {
                return;
            }

            var mouse = Mouse.current;
            if (mouse == null)
            {
                return;
            }

            if (mouse.leftButton.isPressed)
            {
                Vector2 delta = mouse.delta.ReadValue();
                yaw += delta.x * orbitSpeed * Time.deltaTime * MouseDeltaScale;
                pitch -= delta.y * orbitSpeed * Time.deltaTime * MouseDeltaScale;
                pitch = Mathf.Clamp(pitch, 5f, 80f);
            }

            float scroll = mouse.scroll.ReadValue().y;
            distance = Mathf.Clamp(distance - scroll * zoomSpeed * ScrollDeltaScale, minDistance, maxDistance);

            Quaternion rotation = Quaternion.Euler(pitch, yaw, 0f);
            Vector3 offset = rotation * new Vector3(0f, 0f, -distance);
            transform.position = target.position + offset;
            transform.rotation = rotation;
        }
    }
}
