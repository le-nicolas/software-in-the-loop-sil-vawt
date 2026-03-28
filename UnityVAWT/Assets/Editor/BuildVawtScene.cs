using System.IO;
using CDO.VAWT.Unity;
using UnityEditor;
using UnityEditor.SceneManagement;
using UnityEngine;
using UnityEngine.EventSystems;
using UnityEngine.InputSystem.UI;
using UnityEngine.UI;

public static class BuildVawtScene
{
    private const string SceneDirectory = "Assets/Scenes";
    private const string ScenePath = "Assets/Scenes/VAWTScene.unity";

    public static void CreateOrUpdateScene()
    {
        Directory.CreateDirectory(Path.Combine(Application.dataPath, "Scenes"));

        var scene = EditorSceneManager.NewScene(NewSceneSetup.EmptyScene, NewSceneMode.Single);
        scene.name = "VAWTScene";

        var cameraGo = new GameObject("Main Camera");
        var camera = cameraGo.AddComponent<Camera>();
        cameraGo.tag = "MainCamera";
        camera.clearFlags = CameraClearFlags.SolidColor;
        camera.backgroundColor = new Color(0.93f, 0.96f, 0.99f, 1f);
        camera.nearClipPlane = 0.03f;
        camera.farClipPlane = 200f;
        var orbitCamera = cameraGo.AddComponent<OrbitCamera>();

        var lightGo = new GameObject("Directional Light");
        var light = lightGo.AddComponent<Light>();
        light.type = LightType.Directional;
        light.intensity = 1.1f;
        light.color = new Color(1f, 0.98f, 0.95f, 1f);
        lightGo.transform.rotation = Quaternion.Euler(42f, -35f, 0f);

        var eventSystemGo = new GameObject("EventSystem");
        eventSystemGo.AddComponent<EventSystem>();
        var uiInputModule = eventSystemGo.AddComponent<InputSystemUIInputModule>();
        uiInputModule.AssignDefaultActions();

        var systemGo = new GameObject("VAWTSystem");
        var dataLoader = systemGo.AddComponent<WindDataLoader>();
        var decomposer = systemGo.AddComponent<WindDecomposer>();
        var cbfMonitor = systemGo.AddComponent<CBFMonitor>();
        var rotorMesh = systemGo.AddComponent<RotorMesh>();
        var rotorPhysics = systemGo.AddComponent<RotorPhysics>();
        var sphereZones = systemGo.AddComponent<SphereZones>();
        var particles = systemGo.AddComponent<VAWTParticles>();

        var particleSystem = systemGo.GetComponent<ParticleSystem>();
        if (particleSystem == null)
        {
            particleSystem = systemGo.AddComponent<ParticleSystem>();
        }

        var particleRenderer = systemGo.GetComponent<ParticleSystemRenderer>();
        if (particleRenderer == null)
        {
            particleRenderer = systemGo.AddComponent<ParticleSystemRenderer>();
        }

        particleRenderer.renderMode = ParticleSystemRenderMode.Billboard;
        particleRenderer.material = CreateFallbackMaterial("VAWTParticlesMaterial", new Color(0.12f, 0.38f, 0.95f, 0.95f));

        var meshRoot = new GameObject("RotorViewRoot");
        meshRoot.transform.SetParent(systemGo.transform, false);

        var orbitTarget = new GameObject("OrbitTarget");
        orbitTarget.transform.SetParent(systemGo.transform, false);
        orbitTarget.transform.localPosition = new Vector3(0f, 0.9f, 0f);

        var canvasGo = new GameObject("UICanvas");
        var canvas = canvasGo.AddComponent<Canvas>();
        canvas.renderMode = RenderMode.ScreenSpaceOverlay;
        canvasGo.AddComponent<CanvasScaler>().uiScaleMode = CanvasScaler.ScaleMode.ScaleWithScreenSize;
        canvasGo.AddComponent<GraphicRaycaster>();

        var hudGo = new GameObject("HUD");
        hudGo.transform.SetParent(canvasGo.transform, false);
        var hudController = hudGo.AddComponent<HUDController>();

        var directionHistogramGo = new GameObject("DirectionHistogram");
        directionHistogramGo.transform.SetParent(canvasGo.transform, false);
        var directionHistogram = directionHistogramGo.AddComponent<DirectionHistogram>();

        var timelineGo = new GameObject("Timeline");
        timelineGo.transform.SetParent(canvasGo.transform, false);
        var timelineSlider = timelineGo.AddComponent<TimelineSlider>();

        var panelGo = new GameObject("ParameterPanel");
        panelGo.transform.SetParent(canvasGo.transform, false);
        var parameterPanel = panelGo.AddComponent<ParameterPanel>();

        var statusText = CreateText("StatusText", hudGo.transform, new Vector2(20f, -20f), new Vector2(720f, 220f), TextAnchor.UpperLeft, 18);
        var alertText = CreateText("AlertText", hudGo.transform, new Vector2(20f, -250f), new Vector2(520f, 40f), TextAnchor.MiddleLeft, 20);
        var alertBadge = CreateImage("AlertBadge", hudGo.transform, new Vector2(560f, -250f), new Vector2(26f, 26f), new Color(0.12f, 0.72f, 0.34f, 0.9f));
        var captureGraph = CreateRawImage("CaptureGraph", hudGo.transform, new Vector2(20f, -320f), new Vector2(512f, 180f));
        var decompositionGraph = CreateRawImage("DecompositionGraph", hudGo.transform, new Vector2(20f, -520f), new Vector2(512f, 220f));

        var histogramImage = CreateRawImage("HistogramImage", directionHistogramGo.transform, new Vector2(-260f, -20f), new Vector2(360f, 360f));
        var dominantSectorText = CreateText("DominantSectorText", directionHistogramGo.transform, new Vector2(-260f, -400f), new Vector2(360f, 40f), TextAnchor.MiddleCenter, 18);

        var slider = CreateSlider("TimelineSlider", timelineGo.transform, new Vector2(0f, 40f), new Vector2(600f, 20f));
        var playButton = CreateButton("PlayButton", timelineGo.transform, "Play", new Vector2(-170f, 80f), new Vector2(100f, 32f));
        var pauseButton = CreateButton("PauseButton", timelineGo.transform, "Pause", new Vector2(-50f, 80f), new Vector2(100f, 32f));
        var currentHourText = CreateText("CurrentHourText", timelineGo.transform, new Vector2(100f, 80f), new Vector2(180f, 32f), TextAnchor.MiddleLeft, 18);
        var speedText = CreateText("SpeedText", timelineGo.transform, new Vector2(300f, 80f), new Vector2(180f, 32f), TextAnchor.MiddleLeft, 18);

        var tsrOptSlider = CreateLabeledSlider("TsrOptSlider", panelGo.transform, "TSR Opt", new Vector2(0f, -20f), out var tsrOptLabel);
        var tsrSpreadSlider = CreateLabeledSlider("TsrSpreadSlider", panelGo.transform, "Lookup Width", new Vector2(0f, -90f), out var tsrSpreadLabel);
        var cpGenericSlider = CreateLabeledSlider("CpGenericSlider", panelGo.transform, "Cp Scale", new Vector2(0f, -160f), out var cpGenericLabel);
        var alphaSlider = CreateLabeledSlider("AlphaSlider", panelGo.transform, "Alpha", new Vector2(0f, -230f), out var alphaLabel);
        var playbackSpeedSlider = CreateLabeledSlider("PlaybackSpeedSlider", panelGo.transform, "Playback", new Vector2(0f, -300f), out var playbackLabel);

        ConfigureSliderRange(tsrOptSlider, 1.5f, 3.5f, 2.5f);
        ConfigureSliderRange(tsrSpreadSlider, 0.8f, 2.5f, 1.85f);
        ConfigureSliderRange(cpGenericSlider, 0.1f, 0.4f, 0.33f);
        ConfigureSliderRange(alphaSlider, 0.05f, 1.0f, 0.30f);
        ConfigureSliderRange(playbackSpeedSlider, 0.25f, 8.0f, 1.0f);

        SetObjectReference(rotorMesh, "decomposer", decomposer);
        SetObjectReference(rotorMesh, "rotorRoot", meshRoot.transform);
        SetObjectReference(rotorPhysics, "decomposer", decomposer);
        SetObjectReference(rotorPhysics, "timelineSlider", timelineSlider);
        SetObjectReference(rotorPhysics, "rotorRoot", meshRoot.transform);
        SetObjectReference(cbfMonitor, "decomposer", decomposer);
        SetObjectReference(sphereZones, "decomposer", decomposer);
        SetObjectReference(sphereZones, "cbfMonitor", cbfMonitor);
        SetObjectReference(sphereZones, "timelineSlider", timelineSlider);
        SetObjectReference(particles, "decomposer", decomposer);
        SetObjectReference(particles, "timelineSlider", timelineSlider);
        SetObjectReference(particles, "particleSystemComponent", particleSystem);
        SetObjectReference(timelineSlider, "decomposer", decomposer);
        SetObjectReference(timelineSlider, "timeline", slider);
        SetObjectReference(timelineSlider, "playButton", playButton.GetComponent<Button>());
        SetObjectReference(timelineSlider, "pauseButton", pauseButton.GetComponent<Button>());
        SetObjectReference(timelineSlider, "currentHourLabel", currentHourText);
        SetObjectReference(timelineSlider, "speedLabel", speedText);
        SetObjectReference(parameterPanel, "decomposer", decomposer);
        SetObjectReference(parameterPanel, "cbfMonitor", cbfMonitor);
        SetObjectReference(parameterPanel, "tsrOptSlider", tsrOptSlider);
        SetObjectReference(parameterPanel, "tsrSpreadSlider", tsrSpreadSlider);
        SetObjectReference(parameterPanel, "cpGenericSlider", cpGenericSlider);
        SetObjectReference(parameterPanel, "alphaSlider", alphaSlider);
        SetObjectReference(parameterPanel, "playbackSpeedSlider", playbackSpeedSlider);
        SetObjectReference(parameterPanel, "tsrOptLabel", tsrOptLabel);
        SetObjectReference(parameterPanel, "tsrSpreadLabel", tsrSpreadLabel);
        SetObjectReference(parameterPanel, "cpGenericLabel", cpGenericLabel);
        SetObjectReference(parameterPanel, "alphaLabel", alphaLabel);
        SetObjectReference(parameterPanel, "playbackSpeedLabel", playbackLabel);
        SetObjectReference(parameterPanel, "timelineSlider", timelineSlider);
        SetObjectReference(hudController, "dataLoader", dataLoader);
        SetObjectReference(hudController, "decomposer", decomposer);
        SetObjectReference(hudController, "cbfMonitor", cbfMonitor);
        SetObjectReference(hudController, "particles", particles);
        SetObjectReference(hudController, "rotorPhysics", rotorPhysics);
        SetObjectReference(hudController, "timelineSlider", timelineSlider);
        SetObjectReference(hudController, "statusText", statusText);
        SetObjectReference(hudController, "alertText", alertText);
        SetObjectReference(hudController, "alertBadge", alertBadge);
        SetObjectReference(hudController, "captureGraphImage", captureGraph);
        SetObjectReference(hudController, "decompositionGraphImage", decompositionGraph);
        SetObjectReference(directionHistogram, "decomposer", decomposer);
        SetObjectReference(directionHistogram, "histogramImage", histogramImage);
        SetObjectReference(directionHistogram, "dominantSectorText", dominantSectorText);
        SetObjectReference(orbitCamera, "target", orbitTarget.transform);

        AssetDatabase.Refresh();
        EditorSceneManager.SaveScene(scene, ScenePath);
        EditorBuildSettings.scenes = new[]
        {
            new EditorBuildSettingsScene(ScenePath, true)
        };
        EditorSceneManager.OpenScene(ScenePath, OpenSceneMode.Single);
        AssetDatabase.SaveAssets();
        Debug.Log("VAWTScene created and configured.");
    }

    private static Material CreateFallbackMaterial(string name, Color color)
    {
        var shader = Shader.Find("Universal Render Pipeline/Particles/Unlit")
            ?? Shader.Find("Particles/Standard Unlit")
            ?? Shader.Find("Sprites/Default");

        if (shader == null)
        {
            return null;
        }

        var material = new Material(shader) { name = name };
        if (material.HasProperty("_BaseColor"))
        {
            material.SetColor("_BaseColor", color);
        }
        else if (material.HasProperty("_Color"))
        {
            material.SetColor("_Color", color);
        }

        return material;
    }

    private static Text CreateText(string name, Transform parent, Vector2 anchoredPos, Vector2 size, TextAnchor anchor, int fontSize)
    {
        var go = new GameObject(name);
        go.transform.SetParent(parent, false);
        var rect = go.AddComponent<RectTransform>();
        rect.anchorMin = new Vector2(0f, 1f);
        rect.anchorMax = new Vector2(0f, 1f);
        rect.pivot = new Vector2(0f, 1f);
        rect.anchoredPosition = anchoredPos;
        rect.sizeDelta = size;

        var text = go.AddComponent<Text>();
        text.font = Resources.GetBuiltinResource<Font>("LegacyRuntime.ttf");
        text.fontSize = fontSize;
        text.alignment = anchor;
        text.horizontalOverflow = HorizontalWrapMode.Wrap;
        text.verticalOverflow = VerticalWrapMode.Overflow;
        text.color = new Color(0.08f, 0.11f, 0.15f, 1f);
        return text;
    }

    private static Image CreateImage(string name, Transform parent, Vector2 anchoredPos, Vector2 size, Color color)
    {
        var go = new GameObject(name);
        go.transform.SetParent(parent, false);
        var rect = go.AddComponent<RectTransform>();
        rect.anchorMin = new Vector2(0f, 1f);
        rect.anchorMax = new Vector2(0f, 1f);
        rect.pivot = new Vector2(0f, 1f);
        rect.anchoredPosition = anchoredPos;
        rect.sizeDelta = size;

        var image = go.AddComponent<Image>();
        image.color = color;
        return image;
    }

    private static RawImage CreateRawImage(string name, Transform parent, Vector2 anchoredPos, Vector2 size)
    {
        var go = new GameObject(name);
        go.transform.SetParent(parent, false);
        var rect = go.AddComponent<RectTransform>();
        rect.anchorMin = new Vector2(0f, 1f);
        rect.anchorMax = new Vector2(0f, 1f);
        rect.pivot = new Vector2(0f, 1f);
        rect.anchoredPosition = anchoredPos;
        rect.sizeDelta = size;

        var image = go.AddComponent<RawImage>();
        image.color = Color.white;
        return image;
    }

    private static Slider CreateSlider(string name, Transform parent, Vector2 anchoredPos, Vector2 size)
    {
        var root = new GameObject(name);
        root.transform.SetParent(parent, false);
        var rect = root.AddComponent<RectTransform>();
        rect.anchorMin = new Vector2(0.5f, 1f);
        rect.anchorMax = new Vector2(0.5f, 1f);
        rect.pivot = new Vector2(0.5f, 1f);
        rect.anchoredPosition = anchoredPos;
        rect.sizeDelta = size;

        var background = CreateImage("Background", root.transform, Vector2.zero, size, new Color(0.82f, 0.86f, 0.92f, 1f));
        var fillArea = new GameObject("Fill Area");
        fillArea.transform.SetParent(root.transform, false);
        var fillAreaRect = fillArea.AddComponent<RectTransform>();
        fillAreaRect.anchorMin = Vector2.zero;
        fillAreaRect.anchorMax = Vector2.one;
        fillAreaRect.offsetMin = new Vector2(5f, 5f);
        fillAreaRect.offsetMax = new Vector2(-20f, -5f);

        var fill = CreateImage("Fill", fillArea.transform, Vector2.zero, Vector2.zero, new Color(0.12f, 0.38f, 0.95f, 1f));
        var fillRect = fill.rectTransform;
        fillRect.anchorMin = Vector2.zero;
        fillRect.anchorMax = Vector2.one;
        fillRect.offsetMin = Vector2.zero;
        fillRect.offsetMax = Vector2.zero;

        var handleArea = new GameObject("Handle Slide Area");
        handleArea.transform.SetParent(root.transform, false);
        var handleAreaRect = handleArea.AddComponent<RectTransform>();
        handleAreaRect.anchorMin = Vector2.zero;
        handleAreaRect.anchorMax = Vector2.one;
        handleAreaRect.offsetMin = new Vector2(10f, 0f);
        handleAreaRect.offsetMax = new Vector2(-10f, 0f);

        var handle = CreateImage("Handle", handleArea.transform, Vector2.zero, new Vector2(20f, size.y + 12f), new Color(0.95f, 0.6f, 0.1f, 1f));

        var slider = root.AddComponent<Slider>();
        slider.targetGraphic = handle;
        slider.fillRect = fillRect;
        slider.handleRect = handle.rectTransform;
        slider.direction = Slider.Direction.LeftToRight;
        return slider;
    }

    private static GameObject CreateButton(string name, Transform parent, string label, Vector2 anchoredPos, Vector2 size)
    {
        var root = new GameObject(name);
        root.transform.SetParent(parent, false);
        var rect = root.AddComponent<RectTransform>();
        rect.anchorMin = new Vector2(0.5f, 1f);
        rect.anchorMax = new Vector2(0.5f, 1f);
        rect.pivot = new Vector2(0.5f, 1f);
        rect.anchoredPosition = anchoredPos;
        rect.sizeDelta = size;

        var image = root.AddComponent<Image>();
        image.color = new Color(0.12f, 0.38f, 0.95f, 1f);
        var button = root.AddComponent<Button>();
        button.targetGraphic = image;

        var labelText = CreateText("Label", root.transform, new Vector2(0f, 0f), size, TextAnchor.MiddleCenter, 16);
        labelText.rectTransform.anchorMin = Vector2.zero;
        labelText.rectTransform.anchorMax = Vector2.one;
        labelText.rectTransform.pivot = new Vector2(0.5f, 0.5f);
        labelText.rectTransform.anchoredPosition = Vector2.zero;
        labelText.color = Color.white;
        labelText.text = label;
        return root;
    }

    private static Slider CreateLabeledSlider(string name, Transform parent, string labelText, Vector2 anchoredPos, out Text label)
    {
        var root = new GameObject(name);
        root.transform.SetParent(parent, false);
        var rect = root.AddComponent<RectTransform>();
        rect.anchorMin = new Vector2(1f, 1f);
        rect.anchorMax = new Vector2(1f, 1f);
        rect.pivot = new Vector2(1f, 1f);
        rect.anchoredPosition = new Vector2(-20f, anchoredPos.y);
        rect.sizeDelta = new Vector2(320f, 60f);

        label = CreateText("Label", root.transform, new Vector2(0f, 0f), new Vector2(320f, 24f), TextAnchor.MiddleLeft, 16);
        label.text = labelText;

        var slider = CreateSlider("Slider", root.transform, new Vector2(0f, -30f), new Vector2(320f, 18f));
        var sliderRect = slider.GetComponent<RectTransform>();
        sliderRect.anchorMin = new Vector2(0f, 1f);
        sliderRect.anchorMax = new Vector2(0f, 1f);
        sliderRect.pivot = new Vector2(0f, 1f);
        sliderRect.anchoredPosition = new Vector2(0f, -28f);
        return slider;
    }

    private static void ConfigureSliderRange(Slider slider, float min, float max, float value)
    {
        slider.minValue = min;
        slider.maxValue = max;
        slider.value = value;
    }

    private static void SetObjectReference(Object target, string fieldName, Object value)
    {
        var serializedObject = new SerializedObject(target);
        var property = serializedObject.FindProperty(fieldName);
        property.objectReferenceValue = value;
        serializedObject.ApplyModifiedPropertiesWithoutUndo();
        EditorUtility.SetDirty(target);
    }
}
