// REWIND.exe - art import pipeline.
//
// Reads Assets/Art/art_manifest.json (written by Tools/ArtGen/generate_art.py) and:
//   1. Imports every listed sheet as a pixel-perfect sprite sheet (16 PPU, Point, uncompressed)
//      and slices it into frames with the right pivot / 9-slice border.
//   2. Builds AnimationClips, Animator Controllers and prefabs (SpriteRenderer + Animator).
//   3. Creates Tile assets + a Tile Palette for the tileset.
//   4. (Menu) Builds a showcase scene that shows every asset animating.
//
// Menu: Tools > REWIND.exe > ...
using System;
using System.Collections.Generic;
using System.IO;
using System.Linq;
using System.Security.Cryptography;
using System.Text;
using UnityEditor;
using UnityEditor.Animations;
using UnityEditor.SceneManagement;
using UnityEditor.U2D.Sprites;
using UnityEngine;
using UnityEngine.Tilemaps;
using UnityEngine.UI;

namespace RewindExe.ArtPipeline
{
    [Serializable] public class AnimDef { public string name; public int[] frames; public float fps; public bool loop; }
    [Serializable] public class ParamDef { public string name; public string type; }
    [Serializable] public class StateDef { public string name; public string clip; }
    [Serializable] public class CondDef { public string parameter; public string mode; public float threshold; }

    [Serializable]
    public class TransDef
    {
        public string from; public string to; public bool hasExitTime; public float exitTime; public CondDef[] conditions;
    }

    [Serializable]
    public class SheetDef
    {
        public string path; public string group;
        public int frameWidth; public int frameHeight; public int frameCount;
        public float pivotX; public float pivotY; public int[] border;
        public AnimDef[] animations; public int[] tileFrames; public int[] tileFramesNoCollider;
        public bool wrapRepeat;
    }

    [Serializable]
    public class CtrlDef
    {
        public string name; public string sheet; public string folder; public string defaultState; public int sortingOrder;
        public ParamDef[] parameters; public StateDef[] states; public TransDef[] transitions;
    }

    [Serializable]
    public class Manifest { public int pixelsPerUnit = 16; public SheetDef[] sheets; public CtrlDef[] controllers; }

    public static class RewindArt
    {
        public const string ManifestPath = "Assets/Art/art_manifest.json";
        public const string AnimRoot = "Assets/Art/Animations";
        public const string PrefabRoot = "Assets/Art/Prefabs";
        public const string TileRoot = "Assets/Art/Environment/Tiles/TileAssets";
        public const string PalettePath = "Assets/Art/Environment/Tiles/ComplexPalette.prefab";
        public const string ShowcasePath = "Assets/Art/Demo/ArtShowcase.unity";
        const string Log = "[REWIND Art] ";

        public static Manifest LoadManifest()
        {
            if (!File.Exists(ManifestPath)) return null;
            return JsonUtility.FromJson<Manifest>(File.ReadAllText(ManifestPath));
        }

        public static string SpriteName(string sheetPath, int index) =>
            Path.GetFileNameWithoutExtension(sheetPath) + "_" + index;

        // ------------------------------------------------------------------ menu

        [MenuItem("Tools/REWIND.exe/Reimport Art Sheets")]
        public static void ReimportSheets()
        {
            var m = LoadManifest();
            if (m == null) { Debug.LogError(Log + "Manifest not found: " + ManifestPath); return; }
            foreach (var s in m.sheets)
                AssetDatabase.ImportAsset(s.path, ImportAssetOptions.ForceUpdate);
            BuildAll();
        }

        [MenuItem("Tools/REWIND.exe/Rebuild Animations, Prefabs and Tiles")]
        public static void BuildAll()
        {
            var m = LoadManifest();
            if (m == null) { Debug.LogError(Log + "Manifest not found: " + ManifestPath); return; }

            int clips = 0, ctrls = 0, tiles = 0;
            var clipLookup = new Dictionary<string, AnimationClip>();
            // Create every output folder up front: inside StartAssetEditing, IsValidFolder does not
            // see folders created in the same batch, which used to produce "Animations 1", "Animations 2", ...
            foreach (var sheet in m.sheets)
            {
                if (sheet.animations != null && sheet.animations.Length > 0) EnsureFolder($"{AnimRoot}/{sheet.group}");
                if ((sheet.tileFrames?.Length ?? 0) + (sheet.tileFramesNoCollider?.Length ?? 0) > 0) EnsureFolder(TileRoot);
            }
            try
            {
                AssetDatabase.StartAssetEditing();
                foreach (var sheet in m.sheets)
                {
                    var sprites = LoadSprites(sheet.path);
                    if (sprites.Count == 0) { Debug.LogWarning(Log + "No sprites yet for " + sheet.path); continue; }
                    foreach (var a in sheet.animations ?? Array.Empty<AnimDef>())
                    {
                        var clip = BuildClip(sheet, a, sprites);
                        if (clip != null) { clipLookup[a.name] = clip; clips++; }
                    }
                    tiles += BuildTiles(sheet, sprites);
                }
            }
            finally
            {
                AssetDatabase.StopAssetEditing();
                AssetDatabase.SaveAssets();
            }

            foreach (var c in m.controllers ?? Array.Empty<CtrlDef>())
            {
                var ctrl = BuildController(c, clipLookup);
                if (ctrl == null) continue;
                BuildPrefab(c, ctrl, clipLookup);
                ctrls++;
            }
            BuildPalette(m);
            AssetDatabase.SaveAssets();
            AssetDatabase.Refresh();
            Debug.Log($"{Log}Built {clips} clips, {ctrls} controllers + prefabs, {tiles} tiles.");
        }

        [MenuItem("Tools/REWIND.exe/Build and Open Showcase Scene")]
        public static void BuildShowcaseMenu()
        {
            if (!EditorSceneManager.SaveCurrentModifiedScenesIfUserWantsTo()) return;
            BuildAll();
            BuildShowcase();
        }

        /// <summary>Batch-mode entry: Unity.exe -batchmode -projectPath . -executeMethod RewindExe.ArtPipeline.RewindArt.BatchBuild -quit</summary>
        public static void BatchBuild()
        {
            var m = LoadManifest();
            foreach (var s in m.sheets) AssetDatabase.ImportAsset(s.path, ImportAssetOptions.ForceUpdate);
            BuildAll();
            BuildShowcase();
            Verify(m);
        }

        // ------------------------------------------------------------------ sprites

        static Dictionary<string, Sprite> LoadSprites(string path) =>
            AssetDatabase.LoadAllAssetsAtPath(path).OfType<Sprite>()
                .GroupBy(s => s.name).ToDictionary(g => g.Key, g => g.First());

        static Sprite FirstFrame(CtrlDef c, Dictionary<string, AnimationClip> clips)
        {
            var state = c.states.FirstOrDefault(s => s.name == c.defaultState) ?? c.states[0];
            if (!clips.TryGetValue(state.clip, out var clip)) return null;
            var binding = AnimationUtility.GetObjectReferenceCurveBindings(clip).FirstOrDefault();
            var keys = AnimationUtility.GetObjectReferenceCurve(clip, binding);
            return keys != null && keys.Length > 0 ? keys[0].value as Sprite : null;
        }

        // ------------------------------------------------------------------ clips

        static AnimationClip BuildClip(SheetDef sheet, AnimDef a, Dictionary<string, Sprite> sprites)
        {
            var folder = $"{AnimRoot}/{sheet.group}";
            EnsureFolder(folder);
            var path = $"{folder}/{a.name}.anim";
            var clip = AssetDatabase.LoadAssetAtPath<AnimationClip>(path);
            bool isNew = clip == null;
            if (isNew) clip = new AnimationClip { name = a.name };
            clip.frameRate = a.fps;

            int n = a.frames.Length;
            var keys = new ObjectReferenceKeyframe[n + 1];
            for (int i = 0; i <= n; i++)
            {
                int frame = a.frames[Mathf.Min(i, n - 1)];
                if (!sprites.TryGetValue(SpriteName(sheet.path, frame), out var sprite))
                {
                    Debug.LogError($"{Log}{a.name}: missing sprite frame {frame} in {sheet.path}");
                    return null;
                }
                // The extra final key holds the last frame for its full duration.
                keys[i] = new ObjectReferenceKeyframe { time = i / a.fps, value = sprite };
            }

            AnimationUtility.SetObjectReferenceCurve(clip,
                EditorCurveBinding.PPtrCurve("", typeof(SpriteRenderer), "m_Sprite"), keys);
            if (sheet.path.StartsWith("Assets/Art/UI/"))
            {
                // UI sheets also drive a uGUI Image, so the same clip works on Canvas elements.
                AnimationUtility.SetObjectReferenceCurve(clip,
                    EditorCurveBinding.PPtrCurve("", typeof(Image), "m_Sprite"), keys);
            }

            var settings = AnimationUtility.GetAnimationClipSettings(clip);
            settings.loopTime = a.loop;
            AnimationUtility.SetAnimationClipSettings(clip, settings);

            if (isNew) AssetDatabase.CreateAsset(clip, path);
            else EditorUtility.SetDirty(clip);
            return clip;
        }

        // ------------------------------------------------------------------ controllers

        static AnimatorController BuildController(CtrlDef c, Dictionary<string, AnimationClip> clips)
        {
            var folder = $"{AnimRoot}/{c.folder}";
            EnsureFolder(folder);
            var path = $"{folder}/{c.name}.controller";
            var ctrl = AssetDatabase.LoadAssetAtPath<AnimatorController>(path);
            if (ctrl == null) ctrl = AnimatorController.CreateAnimatorControllerAtPath(path);

            // Rebuild in place so the asset GUID (and references to it) survive.
            var sm = ctrl.layers[0].stateMachine;
            foreach (var t in sm.anyStateTransitions.ToArray()) sm.RemoveAnyStateTransition(t);
            foreach (var s in sm.states.ToArray()) sm.RemoveState(s.state);
            foreach (var p in ctrl.parameters.ToArray()) ctrl.RemoveParameter(p);

            foreach (var p in c.parameters ?? Array.Empty<ParamDef>())
                ctrl.AddParameter(p.name, (AnimatorControllerParameterType)Enum.Parse(typeof(AnimatorControllerParameterType), p.type));

            var states = new Dictionary<string, AnimatorState>();
            for (int i = 0; i < c.states.Length; i++)
            {
                var sd = c.states[i];
                var st = sm.AddState(sd.name, new Vector3(300 + (i % 3) * 240, (i / 3) * 90 - 60, 0));
                st.writeDefaultValues = false;
                if (clips.TryGetValue(sd.clip, out var clip)) st.motion = clip;
                else Debug.LogWarning($"{Log}{c.name}: clip {sd.clip} not found");
                states[sd.name] = st;
            }
            if (states.TryGetValue(c.defaultState, out var def)) sm.defaultState = def;

            foreach (var t in c.transitions ?? Array.Empty<TransDef>())
            {
                if (!states.TryGetValue(t.to, out var to)) continue;
                AnimatorStateTransition tr;
                if (t.from == "Any")
                {
                    tr = sm.AddAnyStateTransition(to);
                    tr.canTransitionToSelf = false;
                }
                else if (states.TryGetValue(t.from, out var from)) tr = from.AddTransition(to);
                else continue;

                tr.hasExitTime = t.hasExitTime;
                tr.exitTime = t.exitTime;
                tr.hasFixedDuration = true;
                tr.duration = 0f; // pixel art: snap, never blend
                foreach (var cd in t.conditions ?? Array.Empty<CondDef>())
                    tr.AddCondition((AnimatorConditionMode)Enum.Parse(typeof(AnimatorConditionMode), cd.mode), cd.threshold, cd.parameter);
            }
            EditorUtility.SetDirty(ctrl);
            return ctrl;
        }

        static void BuildPrefab(CtrlDef c, AnimatorController ctrl, Dictionary<string, AnimationClip> clips)
        {
            EnsureFolder(PrefabRoot);
            var go = new GameObject(c.name);
            try
            {
                var sr = go.AddComponent<SpriteRenderer>();
                sr.sprite = FirstFrame(c, clips);
                sr.sortingOrder = c.sortingOrder;
                go.AddComponent<Animator>().runtimeAnimatorController = ctrl;
                PrefabUtility.SaveAsPrefabAsset(go, $"{PrefabRoot}/{c.name}.prefab");
            }
            finally { UnityEngine.Object.DestroyImmediate(go); }
        }

        // ------------------------------------------------------------------ tiles

        static int BuildTiles(SheetDef sheet, Dictionary<string, Sprite> sprites)
        {
            int count = 0;
            void Make(int index, Tile.ColliderType collider)
            {
                if (!sprites.TryGetValue(SpriteName(sheet.path, index), out var sprite)) return;
                EnsureFolder(TileRoot);
                var path = $"{TileRoot}/{sprite.name}.asset";
                var tile = AssetDatabase.LoadAssetAtPath<Tile>(path);
                bool isNew = tile == null;
                if (isNew) tile = ScriptableObject.CreateInstance<Tile>();
                tile.sprite = sprite;
                tile.colliderType = collider;
                if (isNew) AssetDatabase.CreateAsset(tile, path); else EditorUtility.SetDirty(tile);
                count++;
            }
            foreach (var i in sheet.tileFrames ?? Array.Empty<int>()) Make(i, Tile.ColliderType.Sprite);
            foreach (var i in sheet.tileFramesNoCollider ?? Array.Empty<int>()) Make(i, Tile.ColliderType.None);
            return count;
        }

        static void BuildPalette(Manifest m)
        {
            var sheet = m.sheets.FirstOrDefault(s => s.tileFrames != null && s.tileFrames.Length > 0);
            if (sheet == null) return;

            if (AssetDatabase.LoadAssetAtPath<GameObject>(PalettePath) == null)
            {
                // Same structure Unity's "Create New Palette" makes: Grid root + Tilemap child + GridPalette sub-asset.
                var root = new GameObject(Path.GetFileNameWithoutExtension(PalettePath));
                root.AddComponent<Grid>().cellSize = Vector3.one;
                var layer = new GameObject("Layer1");
                layer.transform.SetParent(root.transform);
                layer.AddComponent<Tilemap>();
                layer.AddComponent<TilemapRenderer>().enabled = false;
                PrefabUtility.SaveAsPrefabAsset(root, PalettePath);
                UnityEngine.Object.DestroyImmediate(root);
                var palette = ScriptableObject.CreateInstance<GridPalette>();
                palette.name = "Palette Settings";
                palette.cellSizing = GridPalette.CellSizing.Automatic;
                AssetDatabase.AddObjectToAsset(palette, PalettePath);
                AssetDatabase.ImportAsset(PalettePath);
            }

            var contents = PrefabUtility.LoadPrefabContents(PalettePath);
            try
            {
                var tm = contents.GetComponentInChildren<Tilemap>();
                tm.ClearAllTiles();
                int cols = 8;
                foreach (var i in (sheet.tileFrames ?? new int[0]).Concat(sheet.tileFramesNoCollider ?? new int[0]))
                {
                    var tile = AssetDatabase.LoadAssetAtPath<Tile>($"{TileRoot}/{SpriteName(sheet.path, i)}.asset");
                    if (tile != null) tm.SetTile(new Vector3Int(i % cols, -(i / cols), 0), tile);
                }
                PrefabUtility.SaveAsPrefabAsset(contents, PalettePath);
            }
            finally { PrefabUtility.UnloadPrefabContents(contents); }
        }

        // ------------------------------------------------------------------ showcase scene

        public static void BuildShowcase()
        {
            EnsureFolder(Path.GetDirectoryName(ShowcasePath).Replace('\\', '/'));
            var scene = EditorSceneManager.NewScene(NewSceneSetup.EmptyScene, NewSceneMode.Single);

            // Camera: 320x180 reference, 16 PPU => orthographic size 5.625 (GDD 7.3)
            var camGo = new GameObject("Main Camera") { tag = "MainCamera" };
            var cam = camGo.AddComponent<Camera>();
            cam.orthographic = true;
            cam.orthographicSize = 180f / 2f / 16f;
            cam.clearFlags = CameraClearFlags.SolidColor;
            cam.backgroundColor = new Color32(0x10, 0x18, 0x20, 0xFF);
            camGo.transform.position = new Vector3(0, 0, -10);
            AddPixelPerfectCamera(camGo);

            Sprite S(string sheetPath, int i) =>
                AssetDatabase.LoadAllAssetsAtPath(sheetPath).OfType<Sprite>().FirstOrDefault(s => s.name == SpriteName(sheetPath, i));

            void Static(string name, Sprite sprite, Vector3 pos, int order)
            {
                if (sprite == null) return;
                var go = new GameObject(name);
                go.transform.position = pos;
                var sr = go.AddComponent<SpriteRenderer>();
                sr.sprite = sprite;
                sr.sortingOrder = order;
            }

            Static("BG_Far", S("Assets/Art/Environment/Backgrounds/bg_far.png", 0), Vector3.zero, -30);
            Static("BG_Mid", S("Assets/Art/Environment/Backgrounds/bg_mid.png", 0), Vector3.zero, -20);

            // Tilemaps
            var grid = new GameObject("Grid").AddComponent<Grid>();
            Tile T(int i) => AssetDatabase.LoadAssetAtPath<Tile>($"{TileRoot}/tileset_complex_{i}.asset");
            var bgMap = CreateTilemap(grid, "Background", -10, false);
            var solid = CreateTilemap(grid, "Solid", 0, true);
            for (int x = -10; x < 10; x++)
            {
                solid.SetTile(new Vector3Int(x, -4, 0), T(x == -10 ? 0 : x == 9 ? 2 : (x == 0 ? 7 : 1)));
                for (int y = -6; y < -4; y++)
                    solid.SetTile(new Vector3Int(x, y, 0), T(x == -10 ? 8 : x == 9 ? 10 : 9));
                bgMap.SetTile(new Vector3Int(x, 4, 0), T(x % 5 == 0 ? 31 : 22));
                bgMap.SetTile(new Vector3Int(x, -3, 0), T(x % 7 == 0 ? 21 : (x % 4 == 0 ? 20 : 19)));
            }
            solid.SetTile(new Vector3Int(-1, 1, 0), T(3));
            solid.SetTile(new Vector3Int(0, 1, 0), T(4));
            solid.SetTile(new Vector3Int(1, 1, 0), T(5));

            // Animated prefabs. Floor top is y = -3.
            const float floor = -3f;
            void Place(string prefab, float x, float y)
            {
                var asset = AssetDatabase.LoadAssetAtPath<GameObject>($"{PrefabRoot}/{prefab}.prefab");
                if (asset == null) { Debug.LogWarning(Log + "Missing prefab " + prefab); return; }
                var inst = (GameObject)PrefabUtility.InstantiatePrefab(asset);
                inst.transform.position = new Vector3(x, y, 0);
            }
            Place("Operator", -8.5f, floor);
            Place("DustPuff", -8.5f, floor);
            Place("InteractPrompt", -6.5f, floor + 2.2f);
            Place("TapeRecorder", -6.5f, floor);
            Place("Door", -4.5f, floor);
            Place("PowerSwitch", -3.3f, floor);
            Place("ExitTerminal", -2.2f, floor);
            Place("MainTerminal", 0.4f, floor);
            Place("CRTMonitor", 3.2f, floor);
            Place("Mainframe", 5.0f, floor);
            Place("WarningBeacon", 6.2f, floor);
            Place("Switch", -8.5f, 0.5f);
            Place("RecordMarker", -8.5f, 0.5f);
            Place("VentFan", -4.5f, 2.2f);
            Place("MovingPlatform", 3.5f, 2.0f);
            Place("Conveyor", 7.5f, 0.8f);
            Place("Sparks", 5.0f, 0.4f);
            Place("CeilingLamp", -1.0f, 5.625f);
            Place("CeilingLamp", 5.5f, 5.625f);
            Static("Prop_Crate", S("Assets/Art/Decor/props_16.png", 6), new Vector3(7.6f, floor, 0), 1);
            Static("Prop_Note", S("Assets/Art/Decor/props_16.png", 8), new Vector3(8.6f, floor, 0), 1);
            Static("Prop_RecSign", S("Assets/Art/Decor/props_16.png", 3), new Vector3(-6.5f, 1.5f, 0), 1);
            Static("Prop_HighVoltage", S("Assets/Art/Decor/props_16.png", 2), new Vector3(-3.3f, -0.6f, 0), 1);

            var overlay = new GameObject("CRT_Overlay");
            var osr = overlay.AddComponent<SpriteRenderer>();
            osr.sprite = S("Assets/Art/Effects/crt_overlay.png", 0);
            osr.sortingOrder = 100;
            overlay.transform.SetParent(camGo.transform, false);
            overlay.transform.localPosition = new Vector3(0, 0, 10);

            EditorSceneManager.SaveScene(scene, ShowcasePath);
            Debug.Log(Log + "Showcase scene saved: " + ShowcasePath);
        }

        static Tilemap CreateTilemap(Grid grid, string name, int order, bool collide)
        {
            var go = new GameObject(name);
            go.transform.SetParent(grid.transform, false);
            var tm = go.AddComponent<Tilemap>();
            go.AddComponent<TilemapRenderer>().sortingOrder = order;
            if (collide) go.AddComponent<TilemapCollider2D>();
            return tm;
        }

        static void AddPixelPerfectCamera(GameObject camGo)
        {
            // Looked up by name so this file compiles whether or not URP is installed.
            var type = Type.GetType("UnityEngine.Rendering.Universal.PixelPerfectCamera, Unity.RenderPipelines.Universal.Runtime");
            if (type == null) return;
            var ppc = camGo.AddComponent(type);
            void Set(string prop, object v) => type.GetProperty(prop)?.SetValue(ppc, v);
            Set("assetsPPU", 16);
            Set("refResolutionX", 320);
            Set("refResolutionY", 180);
        }

        // ------------------------------------------------------------------ verification (batch)

        static void Verify(Manifest m)
        {
            int bad = 0;
            foreach (var s in m.sheets)
            {
                var ti = (TextureImporter)AssetImporter.GetAtPath(s.path);
                int sprites = LoadSprites(s.path).Count;
                bool ok = ti != null && ti.filterMode == FilterMode.Point && Mathf.Approximately(ti.spritePixelsPerUnit, m.pixelsPerUnit)
                          && sprites == s.frameCount;
                if (!ok) { bad++; Debug.LogError($"{Log}VERIFY FAIL {s.path}: sprites={sprites}/{s.frameCount} filter={ti?.filterMode} ppu={ti?.spritePixelsPerUnit}"); }
            }
            foreach (var c in m.controllers)
            {
                var ctrl = AssetDatabase.LoadAssetAtPath<AnimatorController>($"{AnimRoot}/{c.folder}/{c.name}.controller");
                var missing = ctrl == null ? c.states.Length : ctrl.layers[0].stateMachine.states.Count(s => s.state.motion == null);
                if (missing > 0) { bad++; Debug.LogError($"{Log}VERIFY FAIL controller {c.name}: {missing} states without clips"); }
            }
            Debug.Log(bad == 0 ? Log + "VERIFY OK - all sheets sliced, all controllers wired." : $"{Log}VERIFY found {bad} problems.");
        }

        // ------------------------------------------------------------------ utils

        public static void EnsureFolder(string folder)
        {
            if (AssetDatabase.IsValidFolder(folder)) return;
            if (Directory.Exists(folder))
            {
                // On disk but not imported yet (e.g. during StartAssetEditing): never create a numbered duplicate.
                return;
            }
            var parent = Path.GetDirectoryName(folder).Replace('\\', '/');
            EnsureFolder(parent);
            AssetDatabase.CreateFolder(parent, Path.GetFileName(folder));
        }

        internal static GUID StableGuid(string s)
        {
            using (var md5 = MD5.Create())
            {
                var hash = md5.ComputeHash(Encoding.UTF8.GetBytes("rewind:" + s));
                return new GUID(BitConverter.ToString(hash).Replace("-", "").ToLowerInvariant());
            }
        }
    }

    /// <summary>Applies pixel-art import settings and grid slicing to every sheet in the manifest.</summary>
    public class RewindSpriteImporter : AssetPostprocessor
    {
        public override uint GetVersion() => 2;

        void OnPreprocessTexture()
        {
            if (!assetPath.StartsWith("Assets/Art/")) return;
            var m = RewindArt.LoadManifest();
            var def = m?.sheets?.FirstOrDefault(s => s.path == assetPath);
            if (def == null) return;

            var ti = (TextureImporter)assetImporter;
            var st = new TextureImporterSettings();
            ti.ReadTextureSettings(st);
            st.spriteMeshType = SpriteMeshType.FullRect;
            st.spriteGenerateFallbackPhysicsShape = true;
            ti.SetTextureSettings(st);

            ti.textureType = TextureImporterType.Sprite;
            ti.spriteImportMode = SpriteImportMode.Multiple;
            ti.spritePixelsPerUnit = m.pixelsPerUnit;
            ti.filterMode = FilterMode.Point;
            ti.textureCompression = TextureImporterCompression.Uncompressed;
            ti.mipmapEnabled = false;
            ti.alphaIsTransparency = true;
            ti.wrapMode = def.wrapRepeat ? TextureWrapMode.Repeat : TextureWrapMode.Clamp;
            ti.maxTextureSize = 2048;

            if (!ReadPngSize(assetPath, out int texW, out int texH)) return;
            int cols = Mathf.Max(1, texW / def.frameWidth);
            var border = def.border != null && def.border.Length == 4
                ? new Vector4(def.border[0], def.border[1], def.border[2], def.border[3]) : Vector4.zero;
            var rects = new List<SpriteRect>();
            for (int i = 0; i < def.frameCount; i++)
            {
                int cx = i % cols, cy = i / cols;
                var name = RewindArt.SpriteName(assetPath, i);
                rects.Add(new SpriteRect
                {
                    name = name,
                    rect = new Rect(cx * def.frameWidth, texH - (cy + 1) * def.frameHeight, def.frameWidth, def.frameHeight),
                    alignment = SpriteAlignment.Custom,
                    pivot = new Vector2(def.pivotX, def.pivotY),
                    border = border,
                    spriteID = RewindArt.StableGuid(name),
                });
            }

            var factory = new SpriteDataProviderFactories();
            factory.Init();
            var dp = factory.GetSpriteEditorDataProviderFromObject(ti);
            dp.InitSpriteEditorDataProvider();

            // Leave existing slicing untouched when it already matches, so sprite IDs stay stable.
            var existing = dp.GetSpriteRects();
            bool same = existing.Length == rects.Count && existing.Zip(rects, (a, b) =>
                a.name == b.name && a.rect == b.rect && a.pivot == b.pivot && a.border == b.border).All(x => x);
            if (same) return;

            dp.SetSpriteRects(rects.ToArray());
            var names = dp.GetDataProvider<ISpriteNameFileIdDataProvider>();
            names?.SetNameFileIdPairs(rects.Select(r => new SpriteNameFileIdPair(r.name, r.spriteID)).ToList());
            dp.Apply();
        }

        static void OnPostprocessAllAssets(string[] imported, string[] deleted, string[] moved, string[] movedFrom)
        {
            if (Application.isBatchMode) return; // BatchBuild drives the build explicitly
            if (!imported.Any(p => p.StartsWith("Assets/Art/") && (p.EndsWith(".png") || p == RewindArt.ManifestPath))) return;
            var m = RewindArt.LoadManifest();
            if (m == null || !imported.Any(p => p == RewindArt.ManifestPath || m.sheets.Any(s => s.path == p))) return;
            if (s_Scheduled) return;
            s_Scheduled = true;
            EditorApplication.delayCall += () => { s_Scheduled = false; RewindArt.BuildAll(); };
        }

        static bool s_Scheduled;

        static bool ReadPngSize(string path, out int w, out int h)
        {
            w = h = 0;
            var bytes = new byte[24];
            using (var fs = File.OpenRead(path))
                if (fs.Read(bytes, 0, 24) < 24) return false;
            w = (bytes[16] << 24) | (bytes[17] << 16) | (bytes[18] << 8) | bytes[19];
            h = (bytes[20] << 24) | (bytes[21] << 16) | (bytes[22] << 8) | bytes[23];
            return w > 0 && h > 0;
        }
    }
}
