// REWIND.exe developer tools.  Tools > REWIND.exe > Dev Tools   (Ctrl+Shift+D)
// Play any cutscene / ending straight from edit mode, and cheat around the game in Play Mode.
using System.IO;
using System.Linq;
using UnityEditor;
using UnityEditor.SceneManagement;
using UnityEngine;
using UnityEngine.SceneManagement;

public class RewindDevTools : EditorWindow
{
    const string IntroScene = "Assets/Scenes/Intro.unity";
    const string GameScene = "Assets/Scenes/SampleScene.unity";
    const string ResetKey = "rw_dev_reset_start_scene";
    const string AutoplayKey = "rw_dev_autoplay";
    Vector2 m_Scroll;

    [MenuItem("Tools/REWIND.exe/Dev Tools %#d", priority = 0)]
    public static void Open() => GetWindow<RewindDevTools>("REWIND Dev");

    [MenuItem("Tools/REWIND.exe/Dev/Play Intro", priority = 20)] static void MIntro() => PlayScene(IntroScene);
    [MenuItem("Tools/REWIND.exe/Dev/Play Game (skip intro)", priority = 21)] static void MGame() => PlayScene(GameScene);
    [MenuItem("Tools/REWIND.exe/Dev/Play Ending - Fail (die in bunker)", priority = 40)] static void MFail() => PlayEnding(GameEnding.Fail);
    [MenuItem("Tools/REWIND.exe/Dev/Play Ending - Bad (kill protocol)", priority = 41)] static void MBad() => PlayEnding(GameEnding.Bad);
    [MenuItem("Tools/REWIND.exe/Dev/Play Ending - Good (lifecycle mode)", priority = 42)] static void MGood() => PlayEnding(GameEnding.Good);

    static bool Autoplay
    {
        get => EditorPrefs.GetBool(AutoplayKey, false);
        set => EditorPrefs.SetBool(AutoplayKey, value);
    }

    // ------------------------------------------------------------------ play helpers

    public static void PlayEnding(GameEnding ending)
    {
        if (EditorApplication.isPlaying) Endings.Play(ending, countAttempt: false);
        else PlayScene($"Assets/Scenes/{Endings.SceneFor(ending)}.unity");
    }

    /// <summary>Enters Play Mode starting from this scene (your open scene is left untouched).</summary>
    public static void PlayScene(string path)
    {
        if (EditorApplication.isPlaying)
        {
            SceneManager.LoadScene(Path.GetFileNameWithoutExtension(path));
            return;
        }
        var asset = AssetDatabase.LoadAssetAtPath<SceneAsset>(path);
        if (asset == null) { Debug.LogError("[Dev] Scene not found: " + path); return; }
        if (!EditorSceneManager.SaveCurrentModifiedScenesIfUserWantsTo()) return;
        EditorSceneManager.playModeStartScene = asset;
        SessionState.SetBool(ResetKey, true);
        EditorApplication.EnterPlaymode();
    }

    [InitializeOnLoadMethod]
    static void Hooks()
    {
        EditorApplication.playModeStateChanged += state =>
        {
            if (state == PlayModeStateChange.EnteredEditMode && SessionState.GetBool(ResetKey, false))
            {
                EditorSceneManager.playModeStartScene = null; // next normal Play starts from the open scene again
                SessionState.SetBool(ResetKey, false);
            }
        };
        SceneManager.sceneLoaded += (s, m) => ApplyAutoplay();
    }

    static void ApplyAutoplay()
    {
        if (!Application.isPlaying) return;
        foreach (var ui in Object.FindObjectsByType<CutsceneUI>(FindObjectsInactive.Include)) ui.autoAdvance = Autoplay;
    }

    // ------------------------------------------------------------------ GUI

    void OnInspectorUpdate()
    {
        if (EditorApplication.isPlaying) Repaint();
    }

    static void Header(string text)
    {
        EditorGUILayout.Space(6);
        EditorGUILayout.LabelField(text, EditorStyles.boldLabel);
    }

    void OnGUI()
    {
        m_Scroll = EditorGUILayout.BeginScrollView(m_Scroll);
        bool playing = EditorApplication.isPlaying;
        EditorGUILayout.HelpBox(playing
            ? "Play Mode: buttons act on the running game."
            : "Edit Mode: scene buttons enter Play Mode from that scene; your open scene is not changed.", MessageType.None);

        Header("Start");
        using (new EditorGUILayout.HorizontalScope())
        {
            if (GUILayout.Button("Intro cutscene")) PlayScene(IntroScene);
            if (GUILayout.Button("Game (skip intro)")) PlayScene(GameScene);
        }

        Header("Endings");
        using (new EditorGUILayout.HorizontalScope())
        {
            GUI.backgroundColor = new Color(1f, 0.75f, 0.5f);
            if (GUILayout.Button("FAIL\ndie in bunker", GUILayout.Height(40))) PlayEnding(GameEnding.Fail);
            GUI.backgroundColor = new Color(1f, 0.5f, 0.5f);
            if (GUILayout.Button("BAD\nkill protocol", GUILayout.Height(40))) PlayEnding(GameEnding.Bad);
            GUI.backgroundColor = new Color(0.55f, 1f, 0.65f);
            if (GUILayout.Button("GOOD\nlifecycle mode", GUILayout.Height(40))) PlayEnding(GameEnding.Good);
            GUI.backgroundColor = Color.white;
        }

        Header("Cutscenes");
        bool auto = EditorGUILayout.ToggleLeft("Auto-play dialog (no key presses needed)", Autoplay);
        if (auto != Autoplay) { Autoplay = auto; ApplyAutoplay(); }
        using (new EditorGUI.DisabledScope(!playing))
        {
            if (GUILayout.Button("Skip current cutscene (like Esc)"))
                foreach (var d in Object.FindObjectsByType<CutsceneDirector>(FindObjectsInactive.Exclude)) d.Skip();
            var dir = playing ? Object.FindFirstObjectByType<CutsceneDirector>() : null;
            if (dir != null) EditorGUILayout.LabelField("Current step", dir.CurrentStep.ToString());
        }

        Header("Game (Play Mode)");
        using (new EditorGUI.DisabledScope(!playing || RoomManager.Instance == null))
        {
            using (new EditorGUILayout.HorizontalScope())
            {
                EditorGUILayout.LabelField("Go to room", GUILayout.Width(80));
                for (int i = 1; i <= 4; i++)
                    if (GUILayout.Button($"0{i}")) RoomManager.Instance.GoToRoom($"room_0{i}");
            }
            if (GUILayout.Button("Unlock all doors"))
                foreach (var e in Object.FindObjectsByType<RoomExit>(FindObjectsInactive.Include)) e.locked = false;
        }
        var lp = playing ? LifecycleProgress.Instance : null;
        using (new EditorGUI.DisabledScope(lp == null))
        {
            using (new EditorGUILayout.HorizontalScope())
            {
                EditorGUILayout.LabelField(lp != null ? $"Sectors {lp.RestoredCount}/{lp.SectorsRequired}" : "Sectors", GUILayout.Width(80));
                for (int i = 1; i <= 4; i++)
                {
                    bool on = lp != null && lp.IsRestored(i);
                    GUI.backgroundColor = on ? new Color(0.55f, 1f, 0.65f) : Color.white;
                    if (GUILayout.Button(on ? $"{i} OK" : $"{i}") && lp != null && !on) lp.RestoreSector(i);
                }
                GUI.backgroundColor = Color.white;
            }
            using (new EditorGUILayout.HorizontalScope())
            {
                if (GUILayout.Button("Restore all") && lp != null)
                    for (int i = 1; i <= lp.SectorsRequired; i++) if (!lp.IsRestored(i)) lp.RestoreSector(i);
                if (GUILayout.Button("Run RESTART CYCLE") && lp != null) lp.TryRestartCycle();
                if (GUILayout.Button("Reset") && lp != null) lp.ResetProgress();
            }
            if (lp != null) EditorGUILayout.LabelField("Failed restarts", lp.FailedRestarts.ToString());
        }

        Header("Save data");
        using (new EditorGUILayout.HorizontalScope())
        {
            int att = EditorGUILayout.IntField("Previous attempts", Endings.Attempts);
            if (att != Endings.Attempts) Endings.Attempts = att;
            if (GUILayout.Button($"Reset ({Endings.FirstAttempt:000})", GUILayout.Width(90))) Endings.Attempts = Endings.FirstAttempt;
        }
        EditorGUILayout.HelpBox("Terminal cheats (Editor / Development builds): type DEV in any terminal.", MessageType.Info);
        EditorGUILayout.EndScrollView();
    }
}
