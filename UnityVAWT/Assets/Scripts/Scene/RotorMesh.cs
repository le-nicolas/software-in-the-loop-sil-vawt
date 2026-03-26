using UnityEngine;
using UnityEngine.Rendering;

namespace CDO.VAWT.Unity
{
    public class RotorMesh : MonoBehaviour
    {
        [SerializeField] private WindDecomposer decomposer;
        [SerializeField] private Transform rotorRoot;
        [SerializeField] private bool rebuildOnAwake = true;

        private void Reset()
        {
            decomposer = FindObjectOfType<WindDecomposer>();
        }

        private void Awake()
        {
            if (rebuildOnAwake)
            {
                BuildRotor();
            }
        }

        public Transform RotorRoot => rotorRoot;

        public void BuildRotor()
        {
            if (rotorRoot == null)
            {
                GameObject root = new GameObject("RotorRoot");
                root.transform.SetParent(transform, false);
                rotorRoot = root.transform;
            }

            ClearChildren(rotorRoot);

            float radius = decomposer != null ? decomposer.RotorRadiusM : 0.75f;
            float height = 1.8f;

            CreateShaft(height);
            CreateSavoniusCups(radius, height);
            CreateDarrieusBlades(radius, height);
        }

        private void CreateShaft(float height)
        {
            GameObject shaft = GameObject.CreatePrimitive(PrimitiveType.Cylinder);
            shaft.name = "Shaft";
            shaft.transform.SetParent(rotorRoot, false);
            shaft.transform.localScale = new Vector3(0.08f, height * 0.5f, 0.08f);
            ApplyRenderer(shaft, new Color(0.2f, 0.2f, 0.22f, 1f));
        }

        private void CreateSavoniusCups(float radius, float height)
        {
            for (int i = 0; i < 2; i++)
            {
                GameObject cup = GameObject.CreatePrimitive(PrimitiveType.Cylinder);
                cup.name = $"SavoniusCup_{i}";
                cup.transform.SetParent(rotorRoot, false);
                cup.transform.localScale = new Vector3(radius * 0.55f, height * 0.24f, radius * 0.22f);
                cup.transform.localPosition = new Vector3(i == 0 ? -radius * 0.18f : radius * 0.18f, 0f, 0f);
                cup.transform.localRotation = Quaternion.Euler(90f, 0f, i == 0 ? 90f : -90f);
                ApplyRenderer(cup, new Color(0.9f, 0.46f, 0.16f, 0.92f));
            }
        }

        private void CreateDarrieusBlades(float radius, float height)
        {
            for (int i = 0; i < 3; i++)
            {
                float angle = i * 120f * Mathf.Deg2Rad;
                Vector3 position = new Vector3(Mathf.Cos(angle) * radius * 0.88f, 0f, Mathf.Sin(angle) * radius * 0.88f);

                GameObject blade = GameObject.CreatePrimitive(PrimitiveType.Cube);
                blade.name = $"DarrieusBlade_{i}";
                blade.transform.SetParent(rotorRoot, false);
                blade.transform.localPosition = position;
                blade.transform.localScale = new Vector3(0.05f, height, 0.18f);
                blade.transform.localRotation = Quaternion.Euler(0f, -i * 120f, 0f);
                ApplyRenderer(blade, new Color(0.2f, 0.55f, 0.95f, 0.96f));
            }
        }

        private static void ApplyRenderer(GameObject go, Color color)
        {
            Collider collider = go.GetComponent<Collider>();
            if (collider != null)
            {
                Object.Destroy(collider);
            }

            MeshRenderer renderer = go.GetComponent<MeshRenderer>();
            if (renderer == null)
            {
                return;
            }

            Shader shader = Shader.Find("Universal Render Pipeline/Lit");
            Material material = new Material(shader);
            if (material.HasProperty("_Surface"))
            {
                material.SetFloat("_Surface", 1f);
            }

            material.SetOverrideTag("RenderType", "Transparent");
            material.SetInt("_SrcBlend", (int)BlendMode.SrcAlpha);
            material.SetInt("_DstBlend", (int)BlendMode.OneMinusSrcAlpha);
            material.SetInt("_ZWrite", 0);
            material.renderQueue = (int)RenderQueue.Transparent;
            if (material.HasProperty("_BaseColor"))
            {
                material.SetColor("_BaseColor", color);
            }

            renderer.sharedMaterial = material;
        }

        private static void ClearChildren(Transform parent)
        {
            for (int i = parent.childCount - 1; i >= 0; i--)
            {
                Object.Destroy(parent.GetChild(i).gameObject);
            }
        }
    }
}
