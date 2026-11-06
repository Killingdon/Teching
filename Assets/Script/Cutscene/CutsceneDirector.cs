using System.Collections;
using System.Collections.Generic;
using System.Linq;
using UnityEngine;
using UnityEngine.InputSystem;
using UnityEngine.SceneManagement;

/// <summary>
/// Plays a cutscene: a list of steps (dialog lines, captions, walking, camera moves, sounds...)
/// run top to bottom. Edit the Steps list in the Inspector to change the story.
/// Space / Enter / click advances dialog, Esc skips to the title card (or the next scene).
/// </summary>
public class CutsceneDirector : MonoBehaviour
{
    [SerializeField] CutsceneUI ui;
    [Tooltip("Camera that CameraMove / CameraCut / Shake move. Default = main camera")]
    [SerializeField] Transform cameraRig;
    [SerializeField] List<DialogSpeaker> speakers = new List<DialogSpeaker>();
    [SerializeField] List<CutsceneStep> steps = new List<CutsceneStep>();

    [Header("Flow")]
    [Tooltip("Scene loaded when the cutscene ends (must be in File > Build Profiles scene list)")]
    [SerializeField] string nextScene = "SampleScene";
    [SerializeField] bool playOnStart = true;
    [SerializeField] bool allowSkip = true;

    public int CurrentStep { get; private set; } = -1;
    public bool IsPlaying { get; private set; }
    public CutsceneUI UI => ui;

    bool m_Skipping;
    Vector3 m_ShakeOffset;

    void OnValidate()
    {
        foreach (var s in steps) if (s != null) s.label = s.Describe();
    }

    void Start()
    {
        if (cameraRig == null && Camera.main != null) cameraRig = Camera.main.transform;
        if (playOnStart) Play();
    }

    public void Play()
    {
        StopAllCoroutines();
        m_Skipping = false;
        StartCoroutine(Run(0));
    }

    void Update()
    {
        if (!IsPlaying || !allowSkip || m_Skipping) return;
        if (Keyboard.current != null && Keyboard.current.escapeKey.wasPressedThisFrame) Skip();
    }

    /// <summary>Jumps to the title card (if the script has one after the current step) or ends the cutscene.</summary>
    public void Skip()
    {
        m_Skipping = true;
        StopAllCoroutines();
        if (cameraRig) cameraRig.position -= m_ShakeOffset;
        m_ShakeOffset = Vector3.zero;
        int resume = -1;
        for (int i = CurrentStep + 1; i < steps.Count; i++)
            if (steps[i] != null && (steps[i].action == CutsceneAction.TitleCard || steps[i].action == CutsceneAction.EndCard)) { resume = i; break; }
        StartCoroutine(SkipRoutine(resume));
    }

    IEnumerator SkipRoutine(int resumeAt)
    {
        ui.HideDialog();
        ui.ClearCaption();
        // Keep the audio right: apply the music / ambience steps we jump over.
        int until = resumeAt >= 0 ? resumeAt : steps.Count;
        for (int i = Mathf.Max(0, CurrentStep + 1); i < until; i++)
        {
            var s = steps[i];
            if (s != null && (s.action == CutsceneAction.PlayMusic || s.action == CutsceneAction.PlayAmbience))
                StartCoroutine(Execute(s));
        }
        if (resumeAt < 0 && AudioManager.Instance) AudioManager.Instance.PlayAmbience(null);
        AudioManager.Play(Sfx.TapeRewind, 0.6f);
        yield return ui.Fade(1f, 0.35f);
        m_Skipping = false;
        if (resumeAt >= 0) yield return Run(resumeAt);
        else LoadNext();
    }

    IEnumerator Run(int from)
    {
        IsPlaying = true;
        ui.ShowSkipHint(allowSkip);
        for (int i = from; i < steps.Count; i++)
        {
            CurrentStep = i;
            var step = steps[i];
            if (step == null) continue;
            if (HidesDialog(step.action)) ui.HideDialog();
            if (step.dontWait) StartCoroutine(Execute(step));
            else yield return Execute(step);
            if (step.action == CutsceneAction.LoadScene) yield break;
        }
        IsPlaying = false;
        LoadNext();
    }

    static bool HidesDialog(CutsceneAction a) =>
        a != CutsceneAction.Dialog && a != CutsceneAction.PlaySfx && a != CutsceneAction.SetAnimatorInt &&
        a != CutsceneAction.SetAnimatorBool && a != CutsceneAction.SetAnimatorTrigger && a != CutsceneAction.SetActive &&
        a != CutsceneAction.PlayMusic && a != CutsceneAction.PlayAmbience && a != CutsceneAction.FadeSprite;

    void LoadNext()
    {
        IsPlaying = false;
        if (!string.IsNullOrEmpty(nextScene)) SceneManager.LoadScene(nextScene);
    }

    // ------------------------------------------------------------------ steps

    IEnumerator Execute(CutsceneStep s)
    {
        switch (s.action)
        {
            case CutsceneAction.Wait:
                yield return Wait(s.duration);
                break;
            case CutsceneAction.Dialog:
                yield return ui.ShowDialog(speakers.FirstOrDefault(sp => sp.id == s.speaker), s.text ?? "", s.expression);
                break;
            case CutsceneAction.Caption:
                yield return ui.ShowCaption(s.text ?? "", s.duration);
                break;
            case CutsceneAction.ClearCaption:
                ui.ClearCaption();
                break;
            case CutsceneAction.MoveActor:
                if (s.target) yield return MoveActor(s.target, s.position.x, s.speed);
                break;
            case CutsceneAction.Teleport:
                if (s.target) s.target.position = new Vector3(s.position.x, s.position.y, s.target.position.z);
                break;
            case CutsceneAction.CameraMove:
                yield return MoveCamera(s.position, s.duration);
                break;
            case CutsceneAction.CameraCut:
                if (cameraRig) cameraRig.position = new Vector3(s.position.x, s.position.y, cameraRig.position.z);
                break;
            case CutsceneAction.FadeOut:
                yield return ui.Fade(1f, s.duration);
                break;
            case CutsceneAction.FadeIn:
                yield return ui.Fade(0f, s.duration);
                break;
            case CutsceneAction.Letterbox:
                yield return ui.Letterbox(s.boolValue, s.duration);
                break;
            case CutsceneAction.SetAnimatorInt:
                if (Anim(s, out var a1)) a1.SetInteger(s.parameter, s.intValue);
                break;
            case CutsceneAction.SetAnimatorBool:
                if (Anim(s, out var a2)) a2.SetBool(s.parameter, s.boolValue);
                break;
            case CutsceneAction.SetAnimatorTrigger:
                if (Anim(s, out var a3)) a3.SetTrigger(s.parameter);
                break;
            case CutsceneAction.SetActive:
                if (s.target) s.target.gameObject.SetActive(s.boolValue);
                break;
            case CutsceneAction.PlaySfx:
                if (s.clip != null) { if (AudioManager.Instance) AudioManager.Instance.PlayClip(s.clip); }
                else AudioManager.Play(s.sfx);
                break;
            case CutsceneAction.PlayMusic:
                if (AudioManager.Instance) AudioManager.Instance.PlayMusic(s.clip);
                break;
            case CutsceneAction.PlayAmbience:
                if (AudioManager.Instance) AudioManager.Instance.PlayAmbience(s.clip);
                break;
            case CutsceneAction.Shake:
                yield return Shake(s.duration, s.amount);
                break;
            case CutsceneAction.Glitch:
                yield return ui.Glitch(s.duration);
                break;
            case CutsceneAction.TitleCard:
                yield return ui.TitleCard();
                break;
            case CutsceneAction.Flash:
                yield return ui.Flash(s.duration);
                break;
            case CutsceneAction.EndCard:
                yield return ui.EndCard(s.text ?? "", string.IsNullOrEmpty(s.parameter) ? "PRESS ANY KEY" : s.parameter);
                break;
            case CutsceneAction.FadeSprite:
                yield return FadeSprite(s.target, s.amount, s.duration);
                break;
            case CutsceneAction.LoadScene:
                yield return ui.Fade(1f, s.duration);
                IsPlaying = false;
                SceneManager.LoadScene(string.IsNullOrEmpty(s.sceneName) ? nextScene : s.sceneName);
                break;
        }
    }

    static IEnumerator Wait(float seconds)
    {
        for (float t = 0; t < seconds; t += Time.unscaledDeltaTime) yield return null;
    }

    static bool Anim(CutsceneStep s, out Animator animator)
    {
        animator = s.target ? s.target.GetComponent<Animator>() : null;
        return animator != null && animator.runtimeAnimatorController != null;
    }

    static void SetParam(Animator a, string name, float f, bool? b = null)
    {
        if (a == null) return;
        foreach (var p in a.parameters)
        {
            if (p.name != name) continue;
            if (p.type == AnimatorControllerParameterType.Float) a.SetFloat(name, f);
            else if (p.type == AnimatorControllerParameterType.Bool && b.HasValue) a.SetBool(name, b.Value);
        }
    }

    IEnumerator MoveActor(Transform actor, float targetX, float speed)
    {
        var anim = actor.GetComponent<Animator>();
        var sr = actor.GetComponent<SpriteRenderer>();
        SetParam(anim, "Grounded", 0, true);
        float dir = Mathf.Sign(targetX - actor.position.x);
        if (sr && dir != 0) sr.flipX = dir < 0;
        SetParam(anim, "Speed", Mathf.Abs(speed));
        while (Mathf.Abs(targetX - actor.position.x) > 0.01f)
        {
            float step = Mathf.Min(Mathf.Abs(targetX - actor.position.x), speed * Time.deltaTime);
            actor.position += new Vector3(dir * step, 0, 0);
            yield return null;
        }
        actor.position = new Vector3(targetX, actor.position.y, actor.position.z);
        SetParam(anim, "Speed", 0);
    }

    static IEnumerator FadeSprite(Transform target, float alpha, float duration)
    {
        var sr = target ? target.GetComponent<SpriteRenderer>() : null;
        if (sr == null) yield break;
        if (!sr.gameObject.activeSelf) sr.gameObject.SetActive(true);
        float from = sr.color.a;
        for (float t = 0; t < duration; t += Time.unscaledDeltaTime)
        {
            var c = sr.color;
            c.a = Mathf.Lerp(from, alpha, t / duration);
            sr.color = c;
            yield return null;
        }
        var e = sr.color;
        e.a = alpha;
        sr.color = e;
    }

    IEnumerator MoveCamera(Vector2 to, float duration)
    {
        if (!cameraRig) yield break;
        var from = cameraRig.position;
        var target = new Vector3(to.x, to.y, from.z);
        for (float t = 0; t < duration; t += Time.deltaTime)
        {
            cameraRig.position = Vector3.Lerp(from, target, Mathf.SmoothStep(0, 1, t / duration)) + m_ShakeOffset;
            yield return null;
        }
        cameraRig.position = target + m_ShakeOffset;
    }

    IEnumerator Shake(float duration, float amount)
    {
        if (!cameraRig) yield break;
        for (float t = 0; t < duration; t += Time.unscaledDeltaTime)
        {
            cameraRig.position -= m_ShakeOffset;
            float k = amount * (1f - t / duration);
            m_ShakeOffset = new Vector3(Random.Range(-k, k), Random.Range(-k, k), 0);
            cameraRig.position += m_ShakeOffset;
            yield return null;
        }
        cameraRig.position -= m_ShakeOffset;
        m_ShakeOffset = Vector3.zero;
    }
}
