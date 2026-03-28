using UnityEngine;
using UnityEngine.Rendering;

namespace CDO.VAWT.Unity
{
    public class SphereZones : MonoBehaviour
    {
        [SerializeField] private WindDecomposer decomposer;
        [SerializeField] private CBFMonitor cbfMonitor;
        [SerializeField] private TimelineSlider timelineSlider;
        [SerializeField] private Transform sphereRoot;
        [SerializeField] private MeshRenderer outerRenderer;
        [SerializeField] private MeshRenderer innerRenderer;

        private Material outerMaterial;
        private Material innerMaterial;

        private void Reset()
        {
            decomposer = FindFirstObjectByType<WindDecomposer>();
            cbfMonitor = FindFirstObjectByType<CBFMonitor>();
            timelineSlider = FindFirstObjectByType<TimelineSlider>();
        }

        private void Awake()
        {
            EnsureSphereVisuals();
        }

        private void Update()
        {
            if (decomposer == null || cbfMonitor == null || cbfMonitor.CaptureFrames.Count == 0)
            {
                return;
            }

            int frameIndex = timelineSlider != null ? timelineSlider.CurrentFrameIndex : 0;
            CaptureFrameData capture = cbfMonitor.GetFrame(frameIndex);

            float outerOpacity = Mathf.Lerp(0.15f, 0.35f, capture.ParticleDensity);
            float innerOpacity = capture.Alert ? 0.35f : 0.15f;

            ApplyColor(outerMaterial, new Color(0.16f, 0.45f, 0.95f, outerOpacity));
            ApplyColor(innerMaterial, new Color(0.98f, 0.48f, 0.13f, innerOpacity));
        }

        private void EnsureSphereVisuals()
        {
            if (sphereRoot == null)
            {
                GameObject root = new GameObject("SphereZonesRoot");
                root.transform.SetParent(transform, false);
                sphereRoot = root.transform;
            }

            float radius = decomposer != null ? decomposer.RotorRadiusM : 0.75f;

            if (outerRenderer == null)
            {
                outerRenderer = CreateSphere("OuterLiftZone", sphereRoot, radius, out outerMaterial);
            }
            else
            {
                outerMaterial = outerRenderer.material;
            }

            if (innerRenderer == null)
            {
                innerRenderer = CreateSphere("InnerDragZone", sphereRoot, radius * 0.5f, out innerMaterial);
            }
            else
            {
                innerMaterial = innerRenderer.material;
            }

            ApplyColor(outerMaterial, new Color(0.16f, 0.45f, 0.95f, 0.15f));
            ApplyColor(innerMaterial, new Color(0.98f, 0.48f, 0.13f, 0.15f));
        }

        private MeshRenderer CreateSphere(string name, Transform parent, float radius, out Material material)
        {
            GameObject sphere = GameObject.CreatePrimitive(PrimitiveType.Sphere);
            sphere.name = name;
            sphere.transform.SetParent(parent, false);
            sphere.transform.localPosition = Vector3.zero;
            sphere.transform.localScale = Vector3.one * radius * 2f;

            Collider collider = sphere.GetComponent<Collider>();
            if (collider != null)
            {
                Destroy(collider);
            }

            MeshRenderer renderer = sphere.GetComponent<MeshRenderer>();
            material = CreateTransparentMaterial(name + "Mat");
            renderer.sharedMaterial = material;
            return renderer;
        }

        private static Material CreateTransparentMaterial(string materialName)
        {
            Shader shader = FindPreferredShader(
                "Universal Render Pipeline/Unlit",
                "Sprites/Default",
                "Unlit/Color",
                "Standard"
            );
            if (shader == null)
            {
                return null;
            }

            Material material = new Material(shader) { name = materialName };

            if (material.HasProperty("_Surface"))
            {
                material.SetFloat("_Surface", 1f);
            }

            material.SetOverrideTag("RenderType", "Transparent");
            if (material.HasProperty("_SrcBlend"))
            {
                material.SetInt("_SrcBlend", (int)BlendMode.SrcAlpha);
            }

            if (material.HasProperty("_DstBlend"))
            {
                material.SetInt("_DstBlend", (int)BlendMode.OneMinusSrcAlpha);
            }

            if (material.HasProperty("_ZWrite"))
            {
                material.SetInt("_ZWrite", 0);
            }

            material.renderQueue = (int)RenderQueue.Transparent;
            return material;
        }

        private static void ApplyColor(Material material, Color color)
        {
            if (material == null)
            {
                return;
            }

            if (material.HasProperty("_BaseColor"))
            {
                material.SetColor("_BaseColor", color);
            }
            else if (material.HasProperty("_Color"))
            {
                material.SetColor("_Color", color);
            }
        }

        private static Shader FindPreferredShader(params string[] shaderNames)
        {
            for (int i = 0; i < shaderNames.Length; i++)
            {
                Shader shader = Shader.Find(shaderNames[i]);
                if (shader != null)
                {
                    return shader;
                }
            }

            return null;
        }
    }
}
