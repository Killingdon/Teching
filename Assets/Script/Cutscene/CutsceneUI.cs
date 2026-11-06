using System.Collections;
using TMPro;
using UnityEngine;
using UnityEngine.InputSystem;
using UnityEngine.UI;

/// <summary>
/// Screen-space pieces of a cutscene: letterbox bars, captions, the dialog box with an animated
/// portrait, fades, the glitch overlay and the title card. Driven by <see cref="CutsceneDirector"/>.
/// </summary>
public class CutsceneUI : MonoBehaviour
{
    [Header("References")]
    [SerializeField] CanvasGroup fade;
    [SerializeField] RectTransform letterboxTop;
    [SerializeField] RectTransform letterboxBottom;
    [SerializeField] TMP_Text caption;
    [SerializeField] CanvasGroup dialog;
    [SerializeField] Image portrait;
    [SerializeField] TMP_Text speakerName;
    [SerializeField] TMP_Text body;
    [SerializeField] TMP_Text continueMark;
    [SerializeField] Image glitch;
    [SerializeField] Sprite[] glitchFrames;
    [SerializeField] CanvasGroup title;
    [SerializeField] Image titleLogo;
    [SerializeField] Sprite[] titleFrames;
    [SerializeField] TMP_Text pressKey;
    [SerializeField] TMP_Text skipHint;
    [SerializeField] CanvasGroup flash;
    [SerializeField] CanvasGroup endCard;
    [SerializeField] TMP_Text endTitle;
    [SerializeField] TMP_Text endBody;
    [SerializeField] TMP_Text endPrompt;

    [Header("Behaviour")]
    [SerializeField] float letterboxHeight = 110f;
    [SerializeField] float captionCharsPerSecond = 32f;
    [Tooltip("Advance dialog automatically (for trailers / testing)")]
    public bool autoAdvance;
    public float autoAdvanceDelay = 1.2f;

    void Awake()
    {
        if (dialog) { dialog.alpha = 0; dialog.gameObject.SetActive(false); }
        if (caption) caption.text = "";
        if (glitch) glitch.gameObject.SetActive(false);
        if (title) { title.alpha = 0; title.gameObject.SetActive(false); }
        if (flash) { flash.alpha = 0; flash.gameObject.SetActive(false); }
        if (endCard) { endCard.alpha = 0; endCard.gameObject.SetActive(false); }
        SetBars(0);
    }

    /// <summary>Space / Enter / E / left click.</summary>
    public static bool AdvancePressed()
    {
        var kb = Keyboard.current;
        var mouse = Mouse.current;
        return (kb != null && (kb.spaceKey.wasPressedThisFrame || kb.enterKey.wasPressedThisFrame ||
                               kb.numpadEnterKey.wasPressedThisFrame || kb.eKey.wasPressedThisFrame))
               || (mouse != null && mouse.leftButton.wasPressedThisFrame);
    }

    static IEnumerator Wait(float seconds)
    {
        for (float t = 0; t < seconds; t += Time.unscaledDeltaTime) yield return null;
    }

    // ------------------------------------------------------------------ fade / letterbox

    public void SetFade(float alpha) { if (fade) fade.alpha = alpha; }

    public IEnumerator Fade(float to, float duration)
    {
        if (!fade) yield break;
        float from = fade.alpha;
        for (float t = 0; t < duration; t += Time.unscaledDeltaTime)
        {
            fade.alpha = Mathf.Lerp(from, to, t / duration);
            yield return null;
        }
        fade.alpha = to;
    }

    public IEnumerator Letterbox(bool on, float duration)
    {
        float from = letterboxTop ? letterboxTop.sizeDelta.y : 0, to = on ? letterboxHeight : 0;
        for (float t = 0; t < duration; t += Time.unscaledDeltaTime)
        {
            SetBars(Mathf.Lerp(from, to, Mathf.SmoothStep(0, 1, t / duration)));
            yield return null;
        }
        SetBars(to);
    }

    void SetBars(float h)
    {
        if (letterboxTop) letterboxTop.sizeDelta = new Vector2(0, h);
        if (letterboxBottom) letterboxBottom.sizeDelta = new Vector2(0, h);
    }

    public void ShowSkipHint(bool on) { if (skipHint) skipHint.gameObject.SetActive(on); }

    // ------------------------------------------------------------------ caption

    public IEnumerator ShowCaption(string text, float hold)
    {
        if (!caption) yield break;
        text = TextTokens.Apply(text);
        caption.text = "";
        yield return null; // don't let the key press that ended the previous step skip this one
        float shown = 0;
        int last = 0;
        while (shown < text.Length)
        {
            if (AdvancePressed()) shown = text.Length;
            shown += captionCharsPerSecond * Time.unscaledDeltaTime;
            int len = Mathf.Min(text.Length, (int)shown);
            if (len != last)
            {
                caption.text = text.Substring(0, len) + (len < text.Length ? "_" : "");
                if (len % 2 == 0 && text[len - 1] != ' ') AudioManager.Play(Sfx.Type, 0.35f);
                last = len;
            }
            yield return null;
        }
        caption.text = text;
        for (float t = 0; t < hold; t += Time.unscaledDeltaTime)
        {
            yield return null;
            if (AdvancePressed()) break;
        }
    }

    public void ClearCaption() { if (caption) caption.text = ""; }

    // ------------------------------------------------------------------ dialog

    public IEnumerator ShowDialog(DialogSpeaker speaker, string text, int expression)
    {
        if (!dialog) yield break;
        text = TextTokens.Apply(text);
        if (!dialog.gameObject.activeSelf)
        {
            dialog.gameObject.SetActive(true);
            dialog.alpha = 0;
        }
        speakerName.text = speaker != null ? speaker.displayName : "";
        speakerName.color = speaker != null ? speaker.nameColor : Color.white;
        body.color = speaker != null ? speaker.textColor : Color.white;
        body.text = "";
        continueMark.text = "";
        var frames = speaker != null ? speaker.portrait : null;
        bool hasPortrait = frames != null && frames.Length > 0;
        portrait.gameObject.SetActive(hasPortrait);
        int rest = expression >= 0 && hasPortrait && expression < frames.Length ? expression : 0;
        Sprite Frame(int i) => hasPortrait ? frames[Mathf.Clamp(i, 0, frames.Length - 1)] : null;
        if (hasPortrait) portrait.sprite = Frame(rest);

        for (float t = 0; t < 0.12f && dialog.alpha < 1; t += Time.unscaledDeltaTime)
        {
            dialog.alpha = Mathf.Clamp01(t / 0.12f);
            yield return null;
        }
        dialog.alpha = 1;

        // type out
        float cps = speaker != null ? speaker.charsPerSecond : 40f;
        float shown = 0, mouth = 0;
        int last = 0;
        bool talkFrame = false;
        while (shown < text.Length)
        {
            yield return null;
            if (AdvancePressed()) shown = text.Length;
            shown += cps * Time.unscaledDeltaTime;
            int len = Mathf.Min(text.Length, (int)shown);
            if (len != last)
            {
                body.text = text.Substring(0, len);
                char c = text[len - 1];
                if (speaker != null && speaker.voice != null && len % 2 == 0 && char.IsLetterOrDigit(c) && AudioManager.Instance != null)
                    AudioManager.Instance.PlayClip(speaker.voice, 0.7f, 0.06f);
                last = len;
            }
            mouth += Time.unscaledDeltaTime;
            if (hasPortrait && expression < 0 && mouth > 0.11f)
            {
                mouth = 0;
                talkFrame = !talkFrame && frames.Length > 1;
                portrait.sprite = Frame(talkFrame ? 1 : 0);
            }
        }
        body.text = text;
        if (hasPortrait) portrait.sprite = Frame(rest);

        // wait for the player (blink the portrait now and then)
        float blink = Random.Range(1.5f, 3f), waited = 0;
        while (true)
        {
            yield return null;
            waited += Time.unscaledDeltaTime;
            continueMark.text = (Time.unscaledTime % 0.8f) < 0.5f ? ">" : "";
            blink -= Time.unscaledDeltaTime;
            if (hasPortrait && expression < 0 && frames.Length > 2)
            {
                if (blink < 0) { portrait.sprite = Frame(2); if (blink < -0.12f) { portrait.sprite = Frame(0); blink = Random.Range(2f, 4f); } }
            }
            if (AdvancePressed() || (autoAdvance && waited > autoAdvanceDelay)) break;
        }
        continueMark.text = "";
        AudioManager.Play(Sfx.Click, 0.5f);
    }

    public void HideDialog()
    {
        if (dialog && dialog.gameObject.activeSelf) dialog.gameObject.SetActive(false);
    }

    // ------------------------------------------------------------------ glitch / title

    public IEnumerator Glitch(float duration)
    {
        if (!glitch || glitchFrames == null || glitchFrames.Length == 0) yield break;
        glitch.gameObject.SetActive(true);
        var rt = (RectTransform)glitch.transform;
        float end = Time.unscaledTime + duration;
        while (Time.unscaledTime < end)
        {
            glitch.sprite = glitchFrames[Random.Range(0, glitchFrames.Length)];
            glitch.color = new Color(1, 1, 1, Random.Range(0.6f, 1f));
            rt.anchoredPosition = new Vector2(Random.Range(-24f, 24f), 0);
            yield return Wait(0.05f);
        }
        rt.anchoredPosition = Vector2.zero;
        glitch.gameObject.SetActive(false);
    }

    /// <summary>Full-screen white flash that fades out (explosions).</summary>
    public IEnumerator Flash(float duration)
    {
        if (!flash) yield break;
        flash.gameObject.SetActive(true);
        flash.alpha = 1f;
        for (float t = 0; t < duration; t += Time.unscaledDeltaTime)
        {
            flash.alpha = 1f - Mathf.SmoothStep(0, 1, t / duration);
            yield return null;
        }
        flash.alpha = 0f;
        flash.gameObject.SetActive(false);
    }

    /// <summary>Text card over black: first line = big title, the rest = body. Waits for any key.</summary>
    public IEnumerator EndCard(string text, string prompt)
    {
        if (!endCard) yield break;
        HideDialog();
        ClearCaption();
        ShowSkipHint(false);
        var lines = TextTokens.Apply(text).Replace("\r", "").Split('\n');
        endTitle.text = lines[0];
        endBody.text = string.Join("\n", lines, 1, lines.Length - 1);
        endPrompt.text = prompt;
        endCard.gameObject.SetActive(true);
        for (float t = 0; t < 1.5f; t += Time.unscaledDeltaTime)
        {
            endCard.alpha = t / 1.5f;
            yield return null;
        }
        endCard.alpha = 1;
        float wait = 0;
        while (true)
        {
            yield return null;
            wait += Time.unscaledDeltaTime;
            endPrompt.alpha = wait < 1.5f ? 0f : ((Time.unscaledTime % 1.2f) < 0.8f ? 1f : 0.15f);
            bool any = (Keyboard.current != null && Keyboard.current.anyKey.wasPressedThisFrame)
                       || (Mouse.current != null && Mouse.current.leftButton.wasPressedThisFrame);
            if (wait > 1.5f && (any || (autoAdvance && wait > autoAdvanceDelay + 2f))) break;
        }
        AudioManager.Play(Sfx.Click);
        for (float t = 0; t < 0.6f; t += Time.unscaledDeltaTime)
        {
            endCard.alpha = 1f - t / 0.6f;
            yield return null;
        }
        endCard.gameObject.SetActive(false);
    }

    public IEnumerator TitleCard()
    {
        if (!title) yield break;
        ShowSkipHint(false);
        HideDialog();
        ClearCaption();
        title.gameObject.SetActive(true);
        for (float t = 0; t < 1.2f; t += Time.unscaledDeltaTime)
        {
            title.alpha = t / 1.2f;
            yield return null;
        }
        title.alpha = 1;
        float wait = 0;
        while (true)
        {
            yield return null;
            wait += Time.unscaledDeltaTime;
            if (titleLogo && titleFrames != null && titleFrames.Length > 1)
                titleLogo.sprite = titleFrames[(Time.unscaledTime % 2.2f) > 2.05f ? 1 : 0];
            if (pressKey) pressKey.alpha = (Time.unscaledTime % 1.2f) < 0.8f ? 1 : 0.15f;
            bool any = (Keyboard.current != null && Keyboard.current.anyKey.wasPressedThisFrame)
                       || (Mouse.current != null && Mouse.current.leftButton.wasPressedThisFrame);
            if (wait > 0.8f && (any || (autoAdvance && wait > autoAdvanceDelay + 1f))) break;
        }
        AudioManager.Play(Sfx.Accept);
        for (int i = 0; i < 4; i++)
        {
            if (pressKey) pressKey.alpha = i % 2;
            yield return Wait(0.08f);
        }
    }
}
