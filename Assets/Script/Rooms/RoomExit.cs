using System.Collections;
using UnityEngine;
using UnityEngine.Events;

/// <summary>
/// A door (or any clickable exit) that takes the player to another room.
/// Hover to highlight, click or press E to use. Locked exits show <see cref="lockedMessage"/>;
/// unlock them from a terminal command (TerminalCommand > On Execute > RoomExit.Unlock).
/// </summary>
[RequireComponent(typeof(Collider2D))]
public class RoomExit : MonoBehaviour
{
    public Room targetRoom;

    [Header("Lock")]
    public bool locked;
    public string lockedMessage = "ACCESS DENIED // AUTHORIZATION CODE REQUIRED";
    public string unlockedMessage = "DOOR UNLOCKED";

    [Header("Visuals")]
    public GameObject outlineObject;
    [Tooltip("Door animator with a bool parameter (Door prefab: IsOpen)")]
    public Animator doorAnimator;
    public string openParameter = "IsOpen";
    [Tooltip("Seconds the door opening animation plays before the room changes")]
    public float openDelay = 0.45f;

    [Header("Events")]
    public UnityEvent onUsed = new UnityEvent();
    public UnityEvent onLockedAttempt = new UnityEvent();
    public UnityEvent onUnlocked = new UnityEvent();

    Collider2D m_Collider;
    SpriteRenderer m_OutlineRenderer;
    bool m_Busy, m_Highlighted;

    void Awake()
    {
        m_Collider = GetComponent<Collider2D>();
        if (outlineObject != null) m_OutlineRenderer = outlineObject.GetComponent<SpriteRenderer>();
    }

    void OnEnable()
    {
        m_Busy = false;
        SetDoor(false); // doors are closed when you come back into a room
        SetHighlight(false);
    }

    void Update()
    {
        if (m_Busy) return;
        if (PointerUtil.InteractionBlocked) { SetHighlight(false); return; }
        bool hovered = PointerUtil.IsPointerOver(m_Collider);
        SetHighlight(hovered);
        if (hovered && (PointerUtil.ClickedThisFrame || PointerUtil.InteractKeyThisFrame)) Use();
    }

    public void Use()
    {
        if (m_Busy || targetRoom == null || !isActiveAndEnabled) return;
        if (locked)
        {
            onLockedAttempt.Invoke();
            AudioManager.Play(Sfx.DoorLocked);
            if (RoomManager.Instance != null) RoomManager.Instance.ShowMessage(lockedMessage, error: true);
            StartCoroutine(DenyFlash());
            return;
        }
        StartCoroutine(OpenAndGo());
    }

    public void Unlock()
    {
        if (!locked) return;
        locked = false;
        AudioManager.Play(Sfx.DoorUnlock);
        onUnlocked.Invoke();
        if (RoomManager.Instance != null && !string.IsNullOrEmpty(unlockedMessage))
            RoomManager.Instance.ShowMessage(unlockedMessage);
    }

    public void Lock() => locked = true;

    IEnumerator OpenAndGo()
    {
        m_Busy = true;
        SetHighlight(false);
        SetDoor(true);
        AudioManager.Play(Sfx.DoorOpen);
        for (float t = 0; t < openDelay; t += Time.unscaledDeltaTime) yield return null;
        onUsed.Invoke();
        if (RoomManager.Instance != null) RoomManager.Instance.GoTo(targetRoom);
        else Debug.LogWarning("[Rooms] No RoomManager in the scene.", this);
        m_Busy = false;
    }

    IEnumerator DenyFlash()
    {
        m_Busy = true;
        if (m_OutlineRenderer != null)
        {
            SetHighlight(true);
            for (int i = 0; i < 3; i++)
            {
                m_OutlineRenderer.color = new Color(1f, 0.35f, 0.3f);
                for (float t = 0; t < 0.08f; t += Time.unscaledDeltaTime) yield return null;
                m_OutlineRenderer.color = Color.white;
                for (float t = 0; t < 0.08f; t += Time.unscaledDeltaTime) yield return null;
            }
        }
        m_Busy = false;
    }

    void SetDoor(bool open)
    {
        if (doorAnimator == null || !doorAnimator.isActiveAndEnabled || doorAnimator.runtimeAnimatorController == null) return;
        foreach (var p in doorAnimator.parameters)
            if (p.name == openParameter && p.type == AnimatorControllerParameterType.Bool)
            {
                doorAnimator.SetBool(openParameter, open);
                return;
            }
    }

    void SetHighlight(bool on)
    {
        if (m_Highlighted == on) return;
        m_Highlighted = on;
        if (on && !m_Busy) AudioManager.Play(Sfx.Hover);
        if (outlineObject != null) outlineObject.SetActive(on);
    }
}
