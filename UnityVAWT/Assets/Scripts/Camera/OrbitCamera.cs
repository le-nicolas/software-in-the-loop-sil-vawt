using UnityEngine;

namespace CDO.VAWT.Unity
{
    public class OrbitCamera : MonoBehaviour
    {
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

            if (Input.GetMouseButton(0))
            {
                yaw += Input.GetAxis("Mouse X") * orbitSpeed * Time.deltaTime;
                pitch -= Input.GetAxis("Mouse Y") * orbitSpeed * Time.deltaTime;
                pitch = Mathf.Clamp(pitch, 5f, 80f);
            }

            float scroll = Input.mouseScrollDelta.y;
            distance = Mathf.Clamp(distance - scroll * zoomSpeed * Time.deltaTime * 40f, minDistance, maxDistance);

            Quaternion rotation = Quaternion.Euler(pitch, yaw, 0f);
            Vector3 offset = rotation * new Vector3(0f, 0f, -distance);
            transform.position = target.position + offset;
            transform.rotation = rotation;
        }
    }
}
