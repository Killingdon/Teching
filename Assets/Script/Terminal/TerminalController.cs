using System;
using System.Collections;
using System.Collections.Generic;
using System.Linq;
using System.Text;
using TMPro;
using UnityEngine;
using UnityEngine.InputSystem;
using UnityEngine.UI;

/// <summary>
/// CRT terminal window. Open it with <see cref="Open"/> (ComputerController does this when the
/// player clicks the computer or presses E on it). Text is typed out line by line; the player
/// types commands into the input line and presses Enter. Esc / EXIT / the X button close it.
///
/// Other systems can listen to <see cref="Opened"/> / <see cref="Closed"/> or check
/// <see cref="IsOpen"/> to block player input while the terminal is up.
/// </summary>
public class TerminalController : MonoBehaviour
{
    public static TerminalController Instance { get; private set; }
    public static bool IsOpen => Instance != null && Instance.m_Open;
    public static event Action<ComputerController> Opened;
    public static event Action Closed;

    [Header("UI references")]
    [SerializeField] GameObject window;
    [SerializeField] RectTransform screen;
    [SerializeField] CanvasGroup screenGroup;
    [SerializeField] TMP_Text titleText;
    [SerializeField] TMP_Text outputText;
    [SerializeField] ScrollRect outputScroll;
    [SerializeField] TMP_InputField inputField;
    [SerializeField] Button closeButton;

    [Header("Behaviour")]
    [Tooltip("Typing speed of terminal output (characters per second)")]
    [SerializeField] float charsPerSecond = 140f;
    [Tooltip("Pause between printed lines (seconds)")]
    [SerializeField] float lineDelay = 0.05f;
    [SerializeField] int maxLines = 300;
    [Tooltip("Sets Time.timeScale to 0 while the terminal is open")]
    [SerializeField] bool pauseGameWhileOpen = false;
    [SerializeField] bool crtFlicker = true;
    [SerializeField] string defaultTitle = "OLDTECH OS // TERMINAL v0.03";

    [Header("Colors")]
    [SerializeField] Color systemColor = new Color32(0x66, 0xFF, 0x99, 0xFF); // GDD CRT green
    [SerializeField] Color userColor = new Color32(0xD8, 0xE0, 0xE6, 0xFF);
    [SerializeField] Color warningColor = new Color32(0xE4, 0xB6, 0x5B, 0xFF); // GDD warning amber
    [SerializeField] Color errorColor = new Color32(0xFF, 0x7A, 0x70, 0xFF);

    [Header("Audio (optional)")]
    [SerializeField] AudioSource audioSource;
    [SerializeField] AudioClip openClip;
    [SerializeField] AudioClip closeClip;
    [SerializeField] AudioClip typeClip;
    [SerializeField] AudioClip errorClip;
    [Tooltip("Played when a computer's custom command runs (e.g. a correct code)")]
    [SerializeField] AudioClip acceptClip;

    struct PendingLine { public string text; public Color color; }

    readonly List<string> m_Lines = new List<string>();      // finished lines (with color tags)
    readonly Queue<PendingLine> m_Queue = new Queue<PendingLine>();
    readonly List<string> m_History = new List<string>();
    int m_HistoryIndex;
    string m_TypingLine = "";
    bool m_Open, m_Typing, m_Skip, m_Busy;
    float m_PrevTimeScale = 1f;
    ComputerController m_Source;
    Coroutine m_PowerRoutine, m_TypeRoutine;

    public ComputerController Source => m_Source;
    /// <summary>True while text is still being typed out.</summary>
    public bool IsTyping => m_Typing || m_Queue.Count > 0;
    /// <summary>True while powering on/off or typing: commands submitted now are ignored.</summary>
    public bool IsBusy => m_Busy || IsTyping;

    // ------------------------------------------------------------------ lifecycle

    void Awake()
    {
        if (Instance != null && Instance != this)
        {
            Debug.LogWarning("[Terminal] More than one TerminalController in the scene; using the first one.", this);
            return;
        }
        Instance = this;
        if (closeButton) closeButton.onClick.AddListener(Close);
        if (inputField)
        {
            inputField.onSubmit.AddListener(Submit);
            inputField.richText = false;
        }
        if (window) window.SetActive(false);
    }

    void OnDestroy()
    {
        if (Instance == this) Instance = null;
    }

    void Update()
    {
        if (!m_Open) return;
        var kb = Keyboard.current;

        if (kb != null && kb.escapeKey.wasPressedThisFrame && !m_Busy)
        {
            Close();
            return;
        }

        // Skip the typewriter effect with Enter / Space / click.
        if (m_Typing && ((kb != null && (kb.enterKey.wasPressedThisFrame || kb.spaceKey.wasPressedThisFrame || kb.numpadEnterKey.wasPressedThisFrame))
                         || (Mouse.current != null && Mouse.current.leftButton.wasPressedThisFrame)))
            m_Skip = true;

        if (!m_Typing && !m_Busy && inputField && kb != null)
        {
            if (kb.upArrowKey.wasPressedThisFrame) BrowseHistory(-1);
            else if (kb.downArrowKey.wasPressedThisFrame) BrowseHistory(+1);
            else if (!inputField.isFocused && kb.anyKey.wasPressedThisFrame) Focus();
        }

        if (crtFlicker && screenGroup)
        {
            float n = Mathf.PerlinNoise(Time.unscaledTime * 9f, 0.37f);
            screenGroup.alpha = n > 0.92f ? 0.86f : 0.97f + n * 0.03f;
        }
    }

    // ------------------------------------------------------------------ open / close

    /// <summary>Opens the terminal for a computer (its title, boot text and custom commands are used).</summary>
    public void Open(ComputerController source)
    {
        if (m_Open || m_Busy) return;
        m_Open = true;
        m_Source = source;
        if (pauseGameWhileOpen) { m_PrevTimeScale = Time.timeScale; Time.timeScale = 0f; }

        if (titleText) titleText.text = source != null && !string.IsNullOrEmpty(source.systemName) ? source.systemName : defaultTitle;
        m_Lines.Clear();
        m_Queue.Clear();
        m_TypingLine = "";
        Refresh();
        if (inputField) inputField.text = "";
        SetInputEnabled(false);

        window.SetActive(true);
        Play(openClip);
        if (m_PowerRoutine != null) StopCoroutine(m_PowerRoutine);
        m_PowerRoutine = StartCoroutine(PowerOn());
        if (m_TypeRoutine != null) StopCoroutine(m_TypeRoutine);
        m_TypeRoutine = StartCoroutine(TypeLoop());
        Opened?.Invoke(source);
    }

    public void Close()
    {
        if (!m_Open || m_Busy) return;
        Play(closeClip);
        if (m_PowerRoutine != null) StopCoroutine(m_PowerRoutine);
        m_PowerRoutine = StartCoroutine(PowerOff());
    }

    IEnumerator PowerOn()
    {
        m_Busy = true;
        // CRT turn-on: a bright line stretches across, then opens vertically.
        screen.localScale = new Vector3(0.02f, 0.006f, 1f);
        yield return ScaleTo(new Vector3(1f, 0.006f, 1f), 0.10f);
        yield return ScaleTo(Vector3.one, 0.14f);
        m_Busy = false;

        var boot = m_Source != null && m_Source.bootMessages != null && m_Source.bootMessages.Length > 0
            ? m_Source.bootMessages
            : DefaultBoot;
        foreach (var block in boot)
            Print(block, systemColor);
        Print("");
        Print("TYPE HELP FOR A LIST OF COMMANDS.", warningColor);
    }

    IEnumerator PowerOff()
    {
        m_Busy = true;
        SetInputEnabled(false);
        yield return ScaleTo(new Vector3(1f, 0.006f, 1f), 0.10f);
        yield return ScaleTo(new Vector3(0f, 0.006f, 1f), 0.08f);
        window.SetActive(false);
        if (m_TypeRoutine != null) StopCoroutine(m_TypeRoutine);
        m_Busy = false;
        m_Open = false;
        m_Typing = false;
        if (pauseGameWhileOpen) Time.timeScale = m_PrevTimeScale;
        var src = m_Source;
        m_Source = null;
        Closed?.Invoke();
        if (src != null) src.OnTerminalClosed();
    }

    IEnumerator ScaleTo(Vector3 target, float duration)
    {
        var start = screen.localScale;
        for (float t = 0; t < duration; t += Time.unscaledDeltaTime)
        {
            screen.localScale = Vector3.Lerp(start, target, t / duration);
            yield return null;
        }
        screen.localScale = target;
    }

    static readonly string[] DefaultBoot =
    {
        "OLDTECH BIOS v1.07 ... MEMORY CHECK 640K OK",
        "MAGNETIC TAPE DRIVE ......... DETECTED",
        "SYSTEM INITIALIZED",
        "",
        "WELCOME, OPERATOR.",
    };

    // ------------------------------------------------------------------ output

    /// <summary>Queues text to be typed out. Multi-line strings are split into separate lines.</summary>
    public void Print(string text, Color? color = null)
    {
        var c = color ?? systemColor;
        text = TextTokens.Apply(text);
        foreach (var line in (text ?? "").Replace("\r", "").Split('\n'))
            m_Queue.Enqueue(new PendingLine { text = line, color = c });
    }

    public void PrintWarning(string text) => Print(text, warningColor);
    public void PrintError(string text) => Print(text, errorColor);

    public void Clear()
    {
        m_Lines.Clear();
        m_Queue.Clear();
        m_TypingLine = "";
        Refresh();
    }

    IEnumerator TypeLoop()
    {
        while (true)
        {
            if (m_Queue.Count == 0 || m_Busy)
            {
                if (m_Typing)
                {
                    m_Typing = false;
                    m_Skip = false;
                    SetInputEnabled(true);
                    Focus();
                }
                yield return null;
                continue;
            }

            if (!m_Typing)
            {
                m_Typing = true;
                SetInputEnabled(false);
            }

            var line = m_Queue.Dequeue();
            string open = $"<color=#{ColorUtility.ToHtmlStringRGB(line.color)}><noparse>";
            const string close = "</noparse></color>";
            float shown = 0f;
            int lastLen = -1;
            while (!m_Skip && shown < line.text.Length)
            {
                shown += charsPerSecond * Time.unscaledDeltaTime;
                int len = Mathf.Min(line.text.Length, Mathf.FloorToInt(shown));
                if (len != lastLen)
                {
                    m_TypingLine = open + line.text.Substring(0, len) + "_" + close; // cursor while typing
                    Refresh();
                    if (len % 3 == 0) Play(typeClip, 0.3f, 0.12f);
                    lastLen = len;
                }
                yield return null;
            }
            m_TypingLine = "";
            m_Lines.Add(line.text.Length == 0 ? "" : open + line.text + close);
            while (m_Lines.Count > maxLines) m_Lines.RemoveAt(0);
            Refresh();
            if (!m_Skip && lineDelay > 0)
                for (float t = 0; t < lineDelay && !m_Skip; t += Time.unscaledDeltaTime) yield return null;
        }
    }

    void Refresh()
    {
        if (!outputText) return;
        var sb = new StringBuilder();
        for (int i = 0; i < m_Lines.Count; i++)
        {
            if (i > 0) sb.Append('\n');
            sb.Append(m_Lines[i]);
        }
        if (m_TypingLine.Length > 0)
        {
            if (m_Lines.Count > 0) sb.Append('\n');
            sb.Append(m_TypingLine);
        }
        outputText.text = sb.ToString();
        if (outputScroll)
        {
            Canvas.ForceUpdateCanvases();
            outputScroll.verticalNormalizedPosition = 0f;
        }
    }

    // ------------------------------------------------------------------ input

    /// <summary>Runs a command line, exactly as if the player typed it and pressed Enter.</summary>
    public void Submit(string raw)
    {
        if (!m_Open || m_Busy) return;
        if (m_Typing) { m_Skip = true; return; }

        var line = (raw ?? "").Trim();
        if (inputField) inputField.text = "";
        if (line.Length == 0) { Focus(); return; }

        if (m_History.Count == 0 || m_History[m_History.Count - 1] != line) m_History.Add(line);
        m_HistoryIndex = m_History.Count;

        Play(typeClip, 0.8f, 0.05f);
        Print("> " + line, userColor);
        Execute(line);
        Focus();
    }

    void Execute(string line)
    {
        var parts = line.Split(new[] { ' ' }, StringSplitOptions.RemoveEmptyEntries);
        var name = parts[0].ToUpperInvariant();
        var args = string.Join(" ", parts.Skip(1));

        // Commands defined on the computer win over the built-ins, so designers can override them.
        // The whole line is tried first ("UNLOCK 4471"), then just the first word ("UNLOCK").
        if (m_Source != null && (m_Source.TryGetCommand(line, out var custom) || m_Source.TryGetCommand(name, out custom)))
        {
            Play(acceptClip);
            if (!string.IsNullOrEmpty(custom.response)) Print(custom.response);
            custom.onExecute?.Invoke();
            return;
        }
        // Right command, wrong code (e.g. "UNLOCK 1234" when only "UNLOCK 4471" exists).
        if (m_Source != null && m_Source.commands.Any(c => c != null && c.Verb == name))
        {
            Play(errorClip);
            PrintError("ACCESS DENIED: INVALID CODE.");
            return;
        }

        switch (name)
        {
            case "HELP":
            case "?":
                Print("AVAILABLE COMMANDS:", warningColor);
                Print("  HELP      THIS LIST");
                Print("  STATUS    SYSTEM STATUS");
                Print("  HINT      OPERATOR ASSISTANCE");
                Print("  LOG       READ SYSTEM LOG");
                Print("  WHOAMI    OPERATOR IDENTITY");
                Print("  ECHO X    PRINT X");
                Print("  CLEAR     CLEAR SCREEN");
                Print("  VOLUME    SOUND LEVELS  (VOLUME MUSIC 50)");
                Print("  MUTE      SOUND OFF / ON");
                Print("  EXIT      CLOSE TERMINAL  [ESC]");
                if (m_Source != null)
                    foreach (var c in m_Source.commands.Where(c => !string.IsNullOrWhiteSpace(c.command) && !string.IsNullOrWhiteSpace(c.description)))
                        Print($"  {c.Verb,-9} {c.description.ToUpperInvariant()}");
                break;
            case "CLEAR":
            case "CLS":
                Clear();
                break;
            case "STATUS":
                if (m_Source != null && m_Source.statusLines != null && m_Source.statusLines.Length > 0)
                    foreach (var s in m_Source.statusLines) Print(s);
                else
                {
                    Print("SYSTEM ......... ONLINE");
                    Print("TAPE MEMORY .... 08.0 SEC");
                    Print("RECORD SLOTS ... 1");
                    Print("SAMPLE RATE .... 10 HZ");
                }
                break;
            case "HINT":
                if (m_Source != null && !string.IsNullOrWhiteSpace(m_Source.hint)) { Print("HINT:", warningColor); Print(m_Source.hint); }
                else Print("NO HINT AVAILABLE IN THIS SECTOR.", warningColor);
                break;
            case "LOG":
                if (m_Source != null && m_Source.logEntries != null && m_Source.logEntries.Length > 0)
                    foreach (var entry in m_Source.logEntries) { Print(entry); Print(""); }
                else Print("LOG ARCHIVE EMPTY.", warningColor);
                break;
            case "WHOAMI":
                Print("OPERATOR.");
                Print("IDENTITY: [DATA CORRUPTED]", errorColor);
                break;
            case "VOLUME":
            case "VOL":
                Volume(parts.Skip(1).ToArray());
                break;
            case "MUTE":
                ToggleMute();
                break;
            case "DEV":
                // Developer commands: only in the Editor and in Development builds.
                if (!(Application.isEditor || Debug.isDebugBuild)) goto default;
                DevCommand(parts.Skip(1).Select(x => x.ToUpperInvariant()).ToArray());
                break;
            case "ECHO":
                Print(args);
                break;
            case "EXIT":
            case "QUIT":
            case "LOGOUT":
                Print("SESSION TERMINATED.", warningColor);
                StartCoroutine(CloseWhenDone());
                break;
            default:
                Play(errorClip);
                PrintError($"UNKNOWN COMMAND: {name}");
                Print("TYPE HELP FOR A LIST OF COMMANDS.", warningColor);
                break;
        }
    }

    void DevCommand(string[] a)
    {
        string sub = a.Length > 0 ? a[0] : "HELP";
        string arg = a.Length > 1 ? a[1] : "";
        switch (sub)
        {
            case "ENDING":
                GameEnding e;
                if (arg == "FAIL") e = GameEnding.Fail;
                else if (arg == "BAD") e = GameEnding.Bad;
                else if (arg == "GOOD") e = GameEnding.Good;
                else { PrintError("USAGE: DEV ENDING FAIL|BAD|GOOD"); return; }
                PrintWarning($"DEV: PLAYING {e.ToString().ToUpperInvariant()} ENDING...");
                StartCoroutine(DevEnding(e));
                return;
            case "ROOM":
                if (RoomManager.Instance == null || !int.TryParse(arg, out int room)) { PrintError("USAGE: DEV ROOM 1-4"); return; }
                Close();
                RoomManager.Instance.GoToRoom($"room_{room:00}");
                return;
            case "UNLOCK":
                int n = 0;
                foreach (var exit in FindObjectsByType<RoomExit>(FindObjectsInactive.Include))
                    if (exit.locked) { exit.locked = false; n++; }
                PrintWarning($"DEV: {n} DOOR(S) UNLOCKED.");
                return;
            case "SECTOR":
                var lp = LifecycleProgress.Instance;
                if (lp == null) { PrintError("DEV: NO LIFECYCLEPROGRESS IN SCENE."); return; }
                if (arg == "ALL") { for (int i = 1; i <= lp.SectorsRequired; i++) if (!lp.IsRestored(i)) lp.RestoreSector(i); }
                else if (int.TryParse(arg, out int sec)) lp.RestoreSector(sec);
                else PrintError("USAGE: DEV SECTOR 1-4|ALL");
                return;
            case "ATTEMPTS":
                if (int.TryParse(arg, out int att)) Endings.Attempts = att;
                PrintWarning($"DEV: ATTEMPTS = {Endings.Attempts:000}");
                return;
            default:
                PrintWarning("DEV COMMANDS (EDITOR / DEV BUILDS ONLY):");
                Print("  DEV ENDING FAIL|BAD|GOOD   PLAY AN ENDING");
                Print("  DEV ROOM 1-4               GO TO A ROOM");
                Print("  DEV SECTOR 1-4|ALL         RESTORE SECTORS");
                Print("  DEV UNLOCK                 UNLOCK ALL DOORS");
                Print("  DEV ATTEMPTS N             SET ATTEMPT COUNTER");
                return;
        }
    }

    IEnumerator DevEnding(GameEnding e)
    {
        while (IsTyping) yield return null;
        for (float t = 0; t < 0.4f; t += Time.unscaledDeltaTime) yield return null;
        Endings.Play(e, countAttempt: false);
    }

    Vector3 m_Unmute;

    void ToggleMute()
    {
        var am = AudioManager.Instance;
        if (am == null) { PrintWarning("AUDIO SUBSYSTEM OFFLINE."); return; }
        if (am.SfxVolume > 0 || am.MusicVolume > 0 || am.AmbienceVolume > 0)
        {
            m_Unmute = new Vector3(am.MusicVolume, am.SfxVolume, am.AmbienceVolume);
            am.MusicVolume = am.SfxVolume = am.AmbienceVolume = 0f;
            Print("AUDIO MUTED. TYPE MUTE AGAIN TO RESTORE.");
        }
        else
        {
            var u = m_Unmute == Vector3.zero ? new Vector3(0.55f, 0.8f, 0.6f) : m_Unmute;
            am.MusicVolume = u.x;
            am.SfxVolume = u.y;
            am.AmbienceVolume = u.z;
            Print("AUDIO RESTORED.");
        }
    }

    void Volume(string[] args)
    {
        var am = AudioManager.Instance;
        if (am == null) { PrintWarning("AUDIO SUBSYSTEM OFFLINE."); return; }
        if (args.Length >= 2 && int.TryParse(args[1], out int pct))
        {
            float v = Mathf.Clamp(pct, 0, 100) / 100f;
            switch (args[0].ToUpperInvariant())
            {
                case "MUSIC": am.MusicVolume = v; break;
                case "SFX": case "SOUND": case "EFFECTS": am.SfxVolume = v; break;
                case "AMBIENCE": case "AMB": am.AmbienceVolume = v; break;
                case "ALL": am.MusicVolume = am.SfxVolume = am.AmbienceVolume = v; break;
                default: PrintError("USAGE: VOLUME [MUSIC|SFX|AMBIENCE|ALL] 0-100"); return;
            }
        }
        else if (args.Length > 0)
        {
            PrintError("USAGE: VOLUME [MUSIC|SFX|AMBIENCE|ALL] 0-100");
            return;
        }
        Print($"MUSIC ..... {Bar(am.MusicVolume)} {Mathf.RoundToInt(am.MusicVolume * 100),3}");
        Print($"SFX ....... {Bar(am.SfxVolume)} {Mathf.RoundToInt(am.SfxVolume * 100),3}");
        Print($"AMBIENCE .. {Bar(am.AmbienceVolume)} {Mathf.RoundToInt(am.AmbienceVolume * 100),3}");
    }

    static string Bar(float v)
    {
        int n = Mathf.RoundToInt(v * 10);
        return "[" + new string('#', n) + new string('.', 10 - n) + "]";
    }

    IEnumerator CloseWhenDone()
    {
        while (m_Queue.Count > 0 || m_Typing) yield return null;
        for (float t = 0; t < 0.35f; t += Time.unscaledDeltaTime) yield return null;
        Close();
    }

    void BrowseHistory(int dir)
    {
        if (m_History.Count == 0 || !inputField) return;
        m_HistoryIndex = Mathf.Clamp(m_HistoryIndex + dir, 0, m_History.Count);
        inputField.text = m_HistoryIndex < m_History.Count ? m_History[m_HistoryIndex] : "";
        inputField.caretPosition = inputField.text.Length;
    }

    void SetInputEnabled(bool on)
    {
        if (!inputField) return;
        inputField.interactable = on;
        if (!on) inputField.DeactivateInputField();
    }

    void Focus()
    {
        if (!inputField || !inputField.interactable || !m_Open) return;
        inputField.Select();
        inputField.ActivateInputField();
    }

    void Play(AudioClip clip, float volume = 1f, float pitchJitter = 0f)
    {
        if (clip == null) return;
        // Route through the AudioManager so the player's SFX volume applies.
        if (AudioManager.Instance != null) AudioManager.Instance.PlayClip(clip, volume, pitchJitter);
        else if (audioSource) audioSource.PlayOneShot(clip, volume);
    }
}
