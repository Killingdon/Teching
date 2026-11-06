using System.Collections.Generic;
using UnityEngine;
using UnityEngine.Events;
using UnityEngine.InputSystem;

/// <summary>
/// An object in the room the player can use: hover with the mouse to highlight it (outline),
/// then click it or press E to interact. If <see cref="opensTerminal"/> is on, interacting opens
/// the TerminalController with this computer's title, boot text, hint, log and custom commands.
///
/// Works with the new Input System (the project has the legacy Input Manager disabled,
/// so OnMouseEnter / OnMouseDown are not used).
/// </summary>
[RequireComponent(typeof(Collider2D))]
public class ComputerController : MonoBehaviour
{
    [Header("Объект обводки")]
    [Tooltip("Перетащите сюда дочерний объект, который отвечает за обводку")]
    public GameObject outlineObject;

    [Header("Interaction")]
    [Tooltip("Interacting opens the terminal window")]
    public bool opensTerminal = true;
    [Tooltip("Left-click the object to interact")]
    public bool clickToInteract = true;
    [Tooltip("Press E while hovering (or while the player is in range) to interact")]
    public bool keyToInteract = true;
    [Tooltip("Optional: the player can also press E when within this distance (0 = mouse hover only)")]
    public float interactRadius = 0f;
    [Tooltip("Optional: player transform used for Interact Radius")]
    public Transform player;
    [Tooltip("Sound when used without opening the terminal (e.g. Paper for notes)")]
    public Sfx interactSound = Sfx.Click;
    [Tooltip("Fired every time the object is used (also for objects that don't open the terminal, e.g. notes)")]
    public UnityEvent onInteract = new UnityEvent();

    [Header("Animation (optional)")]
    [Tooltip("Animator of the computer sprite, e.g. the MainTerminal prefab")]
    public Animator animator;
    [Tooltip("Int parameter that selects the screen state")]
    public string modeParameter = "Mode";
    [Tooltip("Screen state before the computer has been used (MainTerminal: 0 Off, 1 Locked, 2 Active, 3 Glitch)")]
    public int idleMode = 1;
    [Tooltip("Screen state while the terminal is open")]
    public int inUseMode = 2;
    [Tooltip("Screen state after the terminal is closed (-1 = go back to Idle Mode)")]
    public int afterUseMode = 2;

    [Header("Terminal content")]
    public string systemName = "OLDTECH OS // TERMINAL v0.03";
    [Tooltip("Lines typed when the terminal boots. Empty = default boot text.")]
    [TextArea(1, 4)] public string[] bootMessages =
    {
        "OLDTECH BIOS v1.07 ... MEMORY CHECK 640K OK",
        "MAGNETIC TAPE DRIVE ......... DETECTED",
        "SYSTEM INITIALIZED",
        "",
        "WELCOME, OPERATOR. RECORDING SYSTEM READY.",
    };
    [Tooltip("Printed by STATUS. Empty = default tape status.")]
    [TextArea(1, 4)] public string[] statusLines;
    [Tooltip("Printed by HINT")]
    [TextArea(2, 6)] public string hint = "SOME ACTIONS CAN BE\nREPEATED WHILE YOU MOVE.";
    [Tooltip("Printed by LOG")]
    [TextArea(2, 6)] public string[] logEntries =
    {
        "ENTRY 001: ARCHIVE CONTROL ACTIVE. MAINTENANCE CREW DISMISSED.",
        "ENTRY 002: TAPE CAPACITY LIMITED TO 8 SECONDS. DO NOT EXCEED.",
        "ENTRY 047: YOU HAVE BEEN HERE BEFORE.",
    };
    [Tooltip("Extra commands only this computer understands")]
    public List<TerminalCommand> commands = new List<TerminalCommand>();

    public bool IsHighlighted { get; private set; }

    Collider2D m_Collider;
    int m_Mode = int.MinValue;

    void Awake()
    {
        m_Collider = GetComponent<Collider2D>();
    }

    void Start()
    {
        // На старте игры принудительно выключаем обводку, если она была включена
        SetHighlight(false, force: true);
        if (m_Mode == int.MinValue) SetScreenMode(idleMode);
    }

    // Rooms are switched off when the player leaves them; restore the screen state on return.
    void OnEnable()
    {
        if (m_Mode != int.MinValue) SetScreenMode(m_Mode);
    }

    void OnDisable() => SetHighlight(false);

    void Update()
    {
        if (PointerUtil.InteractionBlocked)
        {
            SetHighlight(false);
            return;
        }

        bool hovered = PointerUtil.IsPointerOver(m_Collider);
        bool inRange = IsPlayerInRange();
        SetHighlight(hovered || inRange);

        var mouse = Mouse.current;
        var kb = Keyboard.current;
        if (clickToInteract && hovered && mouse != null && mouse.leftButton.wasPressedThisFrame)
            Interact();
        else if (keyToInteract && (hovered || inRange) && kb != null && kb.eKey.wasPressedThisFrame)
            Interact();
    }

    /// <summary>Use the object. Call this from other scripts too (e.g. a player interactor).</summary>
    public void Interact()
    {
        if (PointerUtil.InteractionBlocked) return;
        onInteract?.Invoke();
        if (!opensTerminal)
        {
            AudioManager.Play(interactSound);
            return;
        }

        var terminal = TerminalController.Instance;
        if (terminal == null)
        {
            Debug.LogWarning("[Computer] No TerminalController in the scene - add the TerminalUI prefab " +
                             "(Tools > REWIND.exe > Terminal > Add Terminal To Open Scene).", this);
            return;
        }
        SetHighlight(false);
        SetScreenMode(inUseMode);
        terminal.Open(this);
    }

    public bool TryGetCommand(string name, out TerminalCommand command)
    {
        foreach (var c in commands)
        {
            if (c != null && c.Matches(name)) { command = c; return true; }
        }
        command = null;
        return false;
    }

    /// <summary>Called by the terminal when it closes after being opened from this computer.</summary>
    public virtual void OnTerminalClosed()
    {
        SetScreenMode(afterUseMode >= 0 ? afterUseMode : idleMode);
    }

    /// <summary>Sets the computer's screen animation state (no-op without an Animator).</summary>
    public void SetScreenMode(int mode)
    {
        m_Mode = mode;
        if (animator == null || animator.runtimeAnimatorController == null || string.IsNullOrEmpty(modeParameter)) return;
        foreach (var p in animator.parameters)
        {
            if (p.name == modeParameter && p.type == AnimatorControllerParameterType.Int)
            {
                animator.SetInteger(modeParameter, mode);
                return;
            }
        }
    }

    bool IsPlayerInRange() =>
        interactRadius > 0f && player != null &&
        Vector2.Distance(player.position, transform.position) <= interactRadius;

    void SetHighlight(bool on, bool force = false)
    {
        if (!force && IsHighlighted == on) return;
        IsHighlighted = on;
        if (on && !force) AudioManager.Play(Sfx.Hover);
        if (outlineObject != null) outlineObject.SetActive(on);
    }
}
