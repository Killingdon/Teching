// Builds the CRT terminal UI prefab and adds it to a scene.
// Menu: Tools > REWIND.exe > Terminal > ...
using System.Linq;
using TMPro;
using UnityEditor;
using UnityEditor.SceneManagement;
using UnityEngine;
using UnityEngine.EventSystems;
using UnityEngine.InputSystem.UI;
using UnityEngine.TextCore.LowLevel;
using UnityEngine.UI;

public static class TerminalSetup
{
    const string PrefabPath = "Assets/Prefabs/UI/TerminalUI.prefab";
    const string FontPath = "Assets/Art/Fonts/VT323/VT323-Regular.ttf";
    const string FontAssetPath = "Assets/Art/Fonts/VT323/VT323 SDF.asset";
    const string PanelSheet = "Assets/Art/UI/panel_9slice.png";
    const string ButtonSheet = "Assets/Art/UI/button_9slice.png";
    const string ScanlineSheet = "Assets/Art/UI/ui_scanlines.png";
    const string Log = "[Terminal Setup] ";

    // Canvas is 1920x1080; art is 16 PPU and the canvas reference is 100 PPU, so a
    // multiplier of 100/16/6 makes one art pixel exactly 6 UI units (320x180 * 6 = 1920x1080).
    const float PixelMultiplier = 100f / 16f / 6f;

    static readonly Color32 Green = new Color32(0x66, 0xFF, 0x99, 0xFF);
    static readonly Color32 GreenDark = new Color32(0x1E, 0x6B, 0x45, 0xFF);
    static readonly Color32 GreenDeep = new Color32(0x0C, 0x2A, 0x1C, 0xFF);
    static readonly Color32 Amber = new Color32(0xE4, 0xB6, 0x5B, 0xFF);
    static readonly Color32 Text = new Color32(0xD8, 0xE0, 0xE6, 0xFF);

    // ------------------------------------------------------------------ menu

    [MenuItem("Tools/REWIND.exe/Terminal/Rebuild Terminal UI Prefab")]
    public static void BuildPrefabMenu()
    {
        BuildPrefab();
        Selection.activeObject = AssetDatabase.LoadAssetAtPath<GameObject>(PrefabPath);
    }

    [MenuItem("Tools/REWIND.exe/Terminal/Add Terminal To Open Scene")]
    public static void AddToOpenScene()
    {
        if (AssetDatabase.LoadAssetAtPath<GameObject>(PrefabPath) == null) BuildPrefab();
        SetupScene(UnityEngine.SceneManagement.SceneManager.GetActiveScene());
    }

    /// <summary>Batch entry: builds the prefab and wires Assets/Scenes/SampleScene.unity.</summary>
    public static void BatchSetupSampleScene()
    {
        BuildPrefab();
        var scene = EditorSceneManager.OpenScene("Assets/Scenes/SampleScene.unity");
        SetupScene(scene);
        EditorSceneManager.SaveScene(scene);
    }

    // ------------------------------------------------------------------ scene wiring

    static void SetupScene(UnityEngine.SceneManagement.Scene scene)
    {
        var prefab = AssetDatabase.LoadAssetAtPath<GameObject>(PrefabPath);
        var roots = scene.GetRootGameObjects();

        // Keep the earlier hand-made draft for reference, but switch it off.
        foreach (var go in roots.Where(r => r.name == "TerminalCanvas"))
        {
            go.name = "TerminalCanvas (old draft)";
            go.SetActive(false);
            Debug.Log(Log + "Disabled the old 'TerminalCanvas' draft (kept in the scene for reference).");
        }

        if (!roots.Any(r => r.GetComponentInChildren<TerminalController>(true)))
        {
            var inst = (GameObject)PrefabUtility.InstantiatePrefab(prefab, scene);
            inst.name = "TerminalUI";
            Undo.RegisterCreatedObjectUndo(inst, "Add Terminal UI");
            Debug.Log(Log + "Added TerminalUI to " + scene.name);
        }

        if (!roots.Any(r => r.GetComponentInChildren<EventSystem>(true)))
        {
            var es = new GameObject("EventSystem", typeof(EventSystem), typeof(InputSystemUIInputModule));
            UnityEngine.SceneManagement.SceneManager.MoveGameObjectToScene(es, scene);
        }

        EditorSceneManager.MarkSceneDirty(scene);
    }

    // ------------------------------------------------------------------ prefab

    public static void BuildPrefab()
    {
        var font = EnsureFont();
        var panel = SpriteAt(PanelSheet, 0);
        var button = SpriteAt(ButtonSheet, 0);
        var scan = SpriteAt(ScanlineSheet, 0);

        var root = new GameObject("TerminalUI", typeof(RectTransform), typeof(Canvas), typeof(CanvasScaler), typeof(GraphicRaycaster));
        try
        {
            var canvas = root.GetComponent<Canvas>();
            canvas.renderMode = RenderMode.ScreenSpaceOverlay;
            canvas.sortingOrder = 50;
            canvas.pixelPerfect = true;
            var scaler = root.GetComponent<CanvasScaler>();
            scaler.uiScaleMode = CanvasScaler.ScaleMode.ScaleWithScreenSize;
            scaler.referenceResolution = new Vector2(1920, 1080);
            scaler.matchWidthOrHeight = 0.5f;
            scaler.referencePixelsPerUnit = 100;

            var window = Rect("Window", root.transform, Vector2.zero, Vector2.one, Vector2.zero, Vector2.zero);

            var backdrop = Img(Rect("Backdrop", window, Vector2.zero, Vector2.one, Vector2.zero, Vector2.zero), null, new Color(0, 0, 0, 0.7f));
            backdrop.raycastTarget = true; // block clicks to the room behind

            // Screen: 248 x 148 art pixels
            var screen = Rect("Screen", window, new Vector2(0.5f, 0.5f), new Vector2(0.5f, 0.5f), Vector2.zero, Vector2.zero);
            screen.sizeDelta = new Vector2(1488, 888);
            var screenGroup = screen.gameObject.AddComponent<CanvasGroup>();
            Img(screen, null, new Color32(0x08, 0x10, 0x0C, 0xF5));
            var frame = Img(Rect("Frame", screen, Vector2.zero, Vector2.one, Vector2.zero, Vector2.zero), panel, Color.white);
            frame.type = Image.Type.Sliced;
            frame.fillCenter = false;
            frame.pixelsPerUnitMultiplier = PixelMultiplier;

            // Header bar
            var header = Rect("Header", screen, new Vector2(0, 1), new Vector2(1, 1), new Vector2(42, -42 - 72), new Vector2(-42, -42));
            Img(header, null, GreenDeep);
            var title = Label("Title", header, "OLDTECH OS // TERMINAL v0.03", 44, Green, TextAlignmentOptions.MidlineLeft, font);
            Stretch(title.rectTransform, new Vector2(24, 0), new Vector2(-360, 0));
            var hintLbl = Label("CloseHint", header, "[ESC] CLOSE", 34, Amber, TextAlignmentOptions.MidlineRight, font);
            Stretch(hintLbl.rectTransform, new Vector2(0, 0), new Vector2(-120, 0));

            var closeRt = Rect("CloseButton", header, new Vector2(1, 0.5f), new Vector2(1, 0.5f), Vector2.zero, Vector2.zero);
            closeRt.sizeDelta = new Vector2(90, 60);
            closeRt.anchoredPosition = new Vector2(-57, 0);
            var closeImg = Img(closeRt, button, Color.white);
            closeImg.type = Image.Type.Sliced;
            closeImg.pixelsPerUnitMultiplier = PixelMultiplier;
            var closeBtn = closeRt.gameObject.AddComponent<Button>();
            closeBtn.targetGraphic = closeImg;
            closeBtn.transition = Selectable.Transition.SpriteSwap;
            closeBtn.spriteState = new SpriteState
            {
                highlightedSprite = SpriteAt(ButtonSheet, 1),
                pressedSprite = SpriteAt(ButtonSheet, 2),
                selectedSprite = button,
            };
            closeBtn.navigation = new Navigation { mode = Navigation.Mode.None };
            var x = Label("X", closeRt, "X", 44, Green, TextAlignmentOptions.Center, font);
            Stretch(x.rectTransform, Vector2.zero, Vector2.zero);

            var sep = Rect("Separator", screen, new Vector2(0, 1), new Vector2(1, 1), new Vector2(42, -42 - 72 - 6), new Vector2(-42, -42 - 72));
            Img(sep, null, GreenDark);

            // Output (scrolling)
            var scrollRt = Rect("Output", screen, Vector2.zero, Vector2.one, new Vector2(60, 42 + 66 + 18), new Vector2(-60, -(42 + 72 + 24)));
            var scroll = scrollRt.gameObject.AddComponent<ScrollRect>();
            var viewport = Rect("Viewport", scrollRt, Vector2.zero, Vector2.one, Vector2.zero, Vector2.zero);
            viewport.gameObject.AddComponent<RectMask2D>();
            var output = Label("OutputText", viewport, "", 38, Text, TextAlignmentOptions.TopLeft, font);
            var ort = output.rectTransform;
            ort.anchorMin = new Vector2(0, 1);
            ort.anchorMax = new Vector2(1, 1);
            ort.pivot = new Vector2(0, 1);
            ort.anchoredPosition = Vector2.zero;
            ort.sizeDelta = Vector2.zero;
            output.textWrappingMode = TextWrappingModes.Normal;
            output.overflowMode = TextOverflowModes.Overflow;
            output.richText = true;
            output.lineSpacing = 4;
            output.gameObject.AddComponent<ContentSizeFitter>().verticalFit = ContentSizeFitter.FitMode.PreferredSize;
            scroll.viewport = viewport;
            scroll.content = ort;
            scroll.horizontal = false;
            scroll.vertical = true;
            scroll.movementType = ScrollRect.MovementType.Clamped;
            scroll.scrollSensitivity = 40;
            scroll.inertia = false;

            // Input line
            var row = Rect("InputRow", screen, new Vector2(0, 0), new Vector2(1, 0), new Vector2(42, 42), new Vector2(-42, 42 + 66));
            Img(row, null, GreenDeep);
            var prompt = Label("Prompt", row, ">", 44, Green, TextAlignmentOptions.MidlineLeft, font);
            prompt.rectTransform.anchorMin = new Vector2(0, 0);
            prompt.rectTransform.anchorMax = new Vector2(0, 1);
            prompt.rectTransform.pivot = new Vector2(0, 0.5f);
            prompt.rectTransform.sizeDelta = new Vector2(40, 0);
            prompt.rectTransform.anchoredPosition = new Vector2(20, 0);

            var fieldRt = Rect("InputField", row, Vector2.zero, Vector2.one, new Vector2(66, 0), new Vector2(-18, 0));
            var fieldBg = Img(fieldRt, null, new Color(0, 0, 0, 0));
            var textArea = Rect("Text Area", fieldRt, Vector2.zero, Vector2.one, Vector2.zero, Vector2.zero);
            textArea.gameObject.AddComponent<RectMask2D>();
            var placeholder = Label("Placeholder", textArea, "TYPE A COMMAND...", 38, GreenDark, TextAlignmentOptions.MidlineLeft, font);
            Stretch(placeholder.rectTransform, Vector2.zero, Vector2.zero);
            var typed = Label("Text", textArea, "", 38, Text, TextAlignmentOptions.MidlineLeft, font);
            Stretch(typed.rectTransform, Vector2.zero, Vector2.zero);
            typed.richText = false;
            typed.textWrappingMode = TextWrappingModes.NoWrap;

            var field = fieldRt.gameObject.AddComponent<TMP_InputField>();
            field.targetGraphic = fieldBg;
            field.textViewport = textArea;
            field.textComponent = typed;
            field.placeholder = placeholder;
            if (font != null) field.fontAsset = font;
            field.pointSize = 38;
            field.lineType = TMP_InputField.LineType.SingleLine;
            field.characterLimit = 64;
            field.onFocusSelectAll = false;
            field.restoreOriginalTextOnEscape = false;
            field.resetOnDeActivation = false;
            field.customCaretColor = true;
            field.caretColor = Green;
            field.caretWidth = 5;
            field.caretBlinkRate = 1.2f;
            field.selectionColor = new Color32(0x36, 0xB3, 0x6E, 0x90);
            field.richText = false;
            field.navigation = new Navigation { mode = Navigation.Mode.None };
            field.transition = Selectable.Transition.None;

            // CRT scanlines over everything inside the frame
            var scanImg = Img(Rect("Scanlines", screen, Vector2.zero, Vector2.one, new Vector2(36, 36), new Vector2(-36, -36)), scan, Color.white);
            scanImg.type = Image.Type.Tiled;
            scanImg.pixelsPerUnitMultiplier = PixelMultiplier * 2f; // 1 art pixel = 3 UI units
            scanImg.raycastTarget = false;

            // Controller
            var ctrl = root.AddComponent<TerminalController>();
            var so = new SerializedObject(ctrl);
            so.FindProperty("window").objectReferenceValue = window.gameObject;
            so.FindProperty("screen").objectReferenceValue = screen;
            so.FindProperty("screenGroup").objectReferenceValue = screenGroup;
            so.FindProperty("titleText").objectReferenceValue = title;
            so.FindProperty("outputText").objectReferenceValue = output;
            so.FindProperty("outputScroll").objectReferenceValue = scroll;
            so.FindProperty("inputField").objectReferenceValue = field;
            so.FindProperty("closeButton").objectReferenceValue = closeBtn;
            var audio = root.AddComponent<AudioSource>();
            audio.playOnAwake = false;
            so.FindProperty("audioSource").objectReferenceValue = audio;
            AssignAudio(so);
            so.ApplyModifiedPropertiesWithoutUndo();

            window.gameObject.SetActive(false);
            RewindExe.ArtPipeline.RewindArt.EnsureFolder("Assets/Prefabs/UI");
            PrefabUtility.SaveAsPrefabAsset(root, PrefabPath);
            Debug.Log(Log + "Saved " + PrefabPath + (font != null ? " (font: VT323)" : " (default TMP font)"));
        }
        finally
        {
            Object.DestroyImmediate(root);
        }
    }

    // ------------------------------------------------------------------ audio

    /// <summary>Hooks the generated terminal sounds (Assets/Audio/SFX) into a TerminalController.</summary>
    public static void AssignAudio(SerializedObject so)
    {
        void Clip(string field, string file)
        {
            var clip = AssetDatabase.LoadAssetAtPath<AudioClip>($"Assets/Audio/SFX/{file}.wav");
            var prop = so.FindProperty(field);
            if (clip != null && prop != null) prop.objectReferenceValue = clip;
        }
        Clip("openClip", "terminal_open");
        Clip("closeClip", "terminal_close");
        Clip("typeClip", "terminal_type");
        Clip("errorClip", "terminal_error");
        Clip("acceptClip", "terminal_accept");
        so.ApplyModifiedPropertiesWithoutUndo();
    }

    // ------------------------------------------------------------------ font

    static TMP_FontAsset EnsureFont()
    {
        var existing = AssetDatabase.LoadAssetAtPath<TMP_FontAsset>(FontAssetPath);
        if (existing != null) return existing;
        var source = AssetDatabase.LoadAssetAtPath<Font>(FontPath);
        if (source == null)
        {
            Debug.LogWarning(Log + "VT323 font not found at " + FontPath + "; using the default TMP font.");
            return TMP_Settings.defaultFontAsset;
        }

        var fa = TMP_FontAsset.CreateFontAsset(source, 48, 6, GlyphRenderMode.SDFAA, 1024, 1024, AtlasPopulationMode.Dynamic);
        fa.name = "VT323 SDF";
        AssetDatabase.CreateAsset(fa, FontAssetPath);
        for (int i = 0; i < fa.atlasTextures.Length; i++)
        {
            fa.atlasTextures[i].name = "VT323 SDF Atlas " + i;
            AssetDatabase.AddObjectToAsset(fa.atlasTextures[i], fa);
        }
        fa.material.name = "VT323 SDF Material";
        AssetDatabase.AddObjectToAsset(fa.material, fa);

        var ascii = new string(Enumerable.Range(32, 95).Select(c => (char)c).ToArray());
        fa.TryAddCharacters(ascii, out _);
        EditorUtility.SetDirty(fa);
        AssetDatabase.SaveAssets();
        return fa;
    }

    // ------------------------------------------------------------------ helpers

    static Sprite SpriteAt(string sheet, int index)
    {
        var name = System.IO.Path.GetFileNameWithoutExtension(sheet) + "_" + index;
        var s = AssetDatabase.LoadAllAssetsAtPath(sheet).OfType<Sprite>().FirstOrDefault(x => x.name == name);
        if (s == null) Debug.LogWarning(Log + "Sprite not found: " + name);
        return s;
    }

    static RectTransform Rect(string name, Transform parent, Vector2 aMin, Vector2 aMax, Vector2 offMin, Vector2 offMax)
    {
        var go = new GameObject(name, typeof(RectTransform));
        go.layer = LayerMask.NameToLayer("UI");
        var rt = (RectTransform)go.transform;
        rt.SetParent(parent, false);
        rt.anchorMin = aMin;
        rt.anchorMax = aMax;
        rt.offsetMin = offMin;
        rt.offsetMax = offMax;
        return rt;
    }

    static void Stretch(RectTransform rt, Vector2 offMin, Vector2 offMax)
    {
        rt.anchorMin = Vector2.zero;
        rt.anchorMax = Vector2.one;
        rt.offsetMin = offMin;
        rt.offsetMax = offMax;
    }

    static Image Img(RectTransform rt, Sprite sprite, Color color)
    {
        var img = rt.gameObject.AddComponent<Image>();
        img.sprite = sprite;
        img.color = color;
        img.raycastTarget = false;
        return img;
    }

    static TextMeshProUGUI Label(string name, Transform parent, string text, float size, Color color,
                                 TextAlignmentOptions align, TMP_FontAsset font)
    {
        var rt = Rect(name, parent, Vector2.zero, Vector2.one, Vector2.zero, Vector2.zero);
        var t = rt.gameObject.AddComponent<TextMeshProUGUI>();
        if (font != null) t.font = font;
        t.text = text;
        t.fontSize = size;
        t.color = color;
        t.alignment = align;
        t.raycastTarget = false;
        t.textWrappingMode = TextWrappingModes.NoWrap;
        return t;
    }
}
