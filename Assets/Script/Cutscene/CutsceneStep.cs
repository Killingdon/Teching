using System;
using UnityEngine;

/// <summary>What a cutscene step does. Only the fields that action uses matter (see tooltips).</summary>
public enum CutsceneAction
{
    Wait,               // duration
    Dialog,             // speaker, text, expression
    Caption,            // text, duration (how long it stays after typing)
    ClearCaption,
    MoveActor,          // target, position.x, speed
    Teleport,           // target, position
    CameraMove,         // position, duration
    CameraCut,          // position
    FadeOut,            // duration  (to black)
    FadeIn,             // duration  (from black)
    Letterbox,          // boolValue (on/off), duration
    SetAnimatorInt,     // target, parameter, intValue
    SetAnimatorBool,    // target, parameter, boolValue
    SetAnimatorTrigger, // target, parameter
    SetActive,          // target, boolValue
    PlaySfx,            // sfx  (or clip, if set)
    PlayMusic,          // clip (empty = stop)
    PlayAmbience,       // clip (empty = stop)
    Shake,              // duration, amount
    Glitch,             // duration
    TitleCard,          // waits for any key
    LoadScene,          // sceneName (empty = the director's Next Scene), duration (fade)
    // --- added for the endings (new actions always go at the END: Unity stores them as numbers)
    Flash,              // duration (white flash that fades out)
    EndCard,            // text (first line = big title, rest = body), parameter = prompt; waits for any key
    FadeSprite,         // target (SpriteRenderer), amount = target alpha 0-1, duration
}

/// <summary>One line of the cutscene script. Edit these on the CutsceneDirector.</summary>
[Serializable]
public class CutsceneStep
{
    [Tooltip("Auto-generated summary (shown as the list element name)")]
    public string label;

    public CutsceneAction action;

    [Header("Dialog / Caption")]
    [Tooltip("Speaker id from the director's Speakers list (e.g. OPERATOR, SYSTEM)")]
    public string speaker;
    [TextArea(2, 5)] public string text;
    [Tooltip("Portrait frame to show instead of the normal one (-1 = normal). Operator: 3 = surprised. System: 3 = glitch")]
    public int expression = -1;

    [Header("Objects / movement")]
    public Transform target;
    [Tooltip("World position for MoveActor (x only), Teleport, CameraMove and CameraCut")]
    public Vector2 position;
    [Tooltip("MoveActor: walking speed in units per second")]
    public float speed = 2.5f;

    [Header("Timing")]
    [Tooltip("Seconds. Wait / fades / camera moves / shake / glitch / how long a caption stays")]
    public float duration = 1f;
    [Tooltip("Shake strength in units")]
    public float amount = 0.1f;
    [Tooltip("Start this step and go straight on to the next one (run things at the same time)")]
    public bool dontWait;

    [Header("Animator / SetActive")]
    public string parameter;
    public int intValue;
    public bool boolValue;

    [Header("Audio / Scene")]
    public Sfx sfx;
    public AudioClip clip;
    public string sceneName;

    public string Describe()
    {
        string T(string s, int n = 38) => string.IsNullOrEmpty(s) ? "" : (s.Replace("\n", " ").Length > n ? s.Replace("\n", " ").Substring(0, n) + "..." : s.Replace("\n", " "));
        string tgt = target != null ? target.name : "-";
        string d;
        switch (action)
        {
            case CutsceneAction.Dialog: d = $"{speaker}: {T(text)}"; break;
            case CutsceneAction.Caption: d = $"Caption: {T(text)}"; break;
            case CutsceneAction.MoveActor: d = $"Move {tgt} -> x {position.x:0.#}"; break;
            case CutsceneAction.Teleport: d = $"Teleport {tgt} -> {position}"; break;
            case CutsceneAction.CameraMove: d = $"Camera -> {position} ({duration:0.#}s)"; break;
            case CutsceneAction.CameraCut: d = $"Camera cut -> {position}"; break;
            case CutsceneAction.SetAnimatorInt: d = $"{tgt}.{parameter} = {intValue}"; break;
            case CutsceneAction.SetAnimatorBool: d = $"{tgt}.{parameter} = {boolValue}"; break;
            case CutsceneAction.SetAnimatorTrigger: d = $"{tgt}.{parameter}!"; break;
            case CutsceneAction.SetActive: d = $"{tgt} active = {boolValue}"; break;
            case CutsceneAction.PlaySfx: d = $"Sound: {(clip != null ? clip.name : sfx.ToString())}"; break;
            case CutsceneAction.PlayMusic: d = $"Music: {(clip != null ? clip.name : "stop")}"; break;
            case CutsceneAction.PlayAmbience: d = $"Ambience: {(clip != null ? clip.name : "stop")}"; break;
            case CutsceneAction.Letterbox: d = $"Letterbox {(boolValue ? "on" : "off")}"; break;
            case CutsceneAction.LoadScene: d = $"Load scene {(string.IsNullOrEmpty(sceneName) ? "(next)" : sceneName)}"; break;
            case CutsceneAction.EndCard: d = $"End card: {T(text)}"; break;
            case CutsceneAction.FadeSprite: d = $"Fade {tgt} -> {amount:0.##} ({duration:0.#}s)"; break;
            case CutsceneAction.ClearCaption:
            case CutsceneAction.TitleCard: d = action.ToString(); break;
            default: d = $"{action} {duration:0.##}s"; break;
        }
        return (dontWait ? "|| " : "") + d;
    }
}

/// <summary>A character who can talk in dialog boxes.</summary>
[Serializable]
public class DialogSpeaker
{
    public string id = "OPERATOR";
    public string displayName = "OPERATOR";
    [Tooltip("0 = normal, 1 = talking, 2 = blink, 3+ = extra expressions")]
    public Sprite[] portrait = Array.Empty<Sprite>();
    public Color nameColor = new Color32(0xE4, 0xB6, 0x5B, 0xFF);
    public Color textColor = new Color32(0xD8, 0xE0, 0xE6, 0xFF);
    [Tooltip("Short blip played while the text types out")]
    public AudioClip voice;
    public float charsPerSecond = 40f;
}
