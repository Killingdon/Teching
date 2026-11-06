using System;
using System.Collections;
using System.Collections.Generic;
using System.Linq;
using TMPro;
using UnityEngine;
using UnityEngine.UI;

/// <summary>
/// Switches between rooms: fades the screen, moves the camera to the target room, switches the
/// other rooms off and shows the room name. Also shows short system messages (e.g. ACCESS DENIED).
///
/// From a UnityEvent (e.g. a TerminalCommand's On Execute) call GoToRoom("room_02").
/// </summary>
public class RoomManager : MonoBehaviour
{
    public static RoomManager Instance { get; private set; }
    public static bool IsTransitioning => Instance != null && Instance.m_Transitioning;
    public static event Action<Room> RoomChanged;

    [SerializeField] Room startRoom;
    [Tooltip("Moved to the active room. Default = main camera")]
    [SerializeField] Transform cameraRig;
    [Tooltip("Rooms the player isn't in are switched off (their animations and input stop)")]
    [SerializeField] bool deactivateOtherRooms = true;
    [SerializeField] float fadeOutTime = 0.25f;
    [SerializeField] float fadeInTime = 0.35f;
    [SerializeField] Color fadeColor = new Color32(0x10, 0x18, 0x20, 0xFF);

    [Header("Room title / messages")]
    [SerializeField] TMP_FontAsset font;
    [SerializeField] float messageTime = 2.5f;
    [SerializeField] Color titleColor = new Color32(0x66, 0xFF, 0x99, 0xFF);
    [SerializeField] Color errorColor = new Color32(0xFF, 0x7A, 0x70, 0xFF);

    public Room Current { get; private set; }
    public IReadOnlyList<Room> Rooms => m_Rooms;

    readonly List<Room> m_Rooms = new List<Room>();
    bool m_Transitioning;
    CanvasGroup m_Fade;
    TMP_Text m_Message;
    Coroutine m_MessageRoutine;

    void Awake()
    {
        if (Instance != null && Instance != this) { Destroy(this); return; }
        Instance = this;
        m_Rooms.AddRange(FindObjectsByType<Room>(FindObjectsInactive.Include));
        if (cameraRig == null && Camera.main != null) cameraRig = Camera.main.transform;
        BuildOverlay();
    }

    void OnDestroy()
    {
        if (Instance == this) Instance = null;
    }

    void Start()
    {
        var first = startRoom != null ? startRoom : m_Rooms.FirstOrDefault();
        if (first != null) Enter(first);
    }

    // ------------------------------------------------------------------ public API

    public void GoTo(Room target)
    {
        if (target == null || m_Transitioning || target == Current) return;
        StartCoroutine(Transition(target));
    }

    /// <summary>For UnityEvents: go to the room with this id.</summary>
    public void GoToRoom(string roomId)
    {
        var room = m_Rooms.FirstOrDefault(r => r.roomId == roomId);
        if (room == null) { Debug.LogWarning($"[Rooms] No room with id '{roomId}'", this); return; }
        GoTo(room);
    }

    public Room Find(string roomId) => m_Rooms.FirstOrDefault(r => r.roomId == roomId);

    /// <summary>Shows a short line of text in the corner (room titles, ACCESS DENIED...).</summary>
    public void ShowMessage(string text, bool error = false)
    {
        if (m_Message == null) return;
        if (m_MessageRoutine != null) StopCoroutine(m_MessageRoutine);
        m_MessageRoutine = StartCoroutine(MessageRoutine(text, error ? errorColor : titleColor));
    }

    // ------------------------------------------------------------------ internals

    IEnumerator Transition(Room target)
    {
        m_Transitioning = true;
        AudioManager.Play(Sfx.RoomTransition);
        yield return Fade(0f, 1f, fadeOutTime);
        Enter(target);
        yield return null;
        yield return Fade(1f, 0f, fadeInTime);
        m_Transitioning = false;
    }

    void Enter(Room target)
    {
        var previous = Current;
        if (previous != null) previous.onExit.Invoke();
        if (deactivateOtherRooms)
            foreach (var r in m_Rooms) r.gameObject.SetActive(r == target);
        if (cameraRig != null)
        {
            var p = target.CameraPosition;
            cameraRig.position = new Vector3(p.x, p.y, cameraRig.position.z);
        }
        Current = target;
        target.onEnter.Invoke();
        RoomChanged?.Invoke(target);
        if (!string.IsNullOrEmpty(target.displayName)) ShowMessage(target.displayName);
    }

    IEnumerator Fade(float from, float to, float time)
    {
        for (float t = 0; t < time; t += Time.unscaledDeltaTime)
        {
            m_Fade.alpha = Mathf.Lerp(from, to, t / time);
            yield return null;
        }
        m_Fade.alpha = to;
    }

    IEnumerator MessageRoutine(string text, Color color)
    {
        m_Message.text = "";
        m_Message.color = color;
        // quick typewriter
        for (int i = 1; i <= text.Length; i++)
        {
            m_Message.text = text.Substring(0, i) + (i < text.Length ? "_" : "");
            for (float t = 0; t < 0.018f; t += Time.unscaledDeltaTime) yield return null;
        }
        for (float t = 0; t < messageTime; t += Time.unscaledDeltaTime) yield return null;
        for (float t = 0; t < 0.5f; t += Time.unscaledDeltaTime)
        {
            m_Message.color = new Color(color.r, color.g, color.b, 1f - t / 0.5f);
            yield return null;
        }
        m_Message.text = "";
    }

    void BuildOverlay()
    {
        var go = new GameObject("RoomOverlay", typeof(RectTransform), typeof(Canvas), typeof(CanvasScaler));
        go.transform.SetParent(transform, false);
        var canvas = go.GetComponent<Canvas>();
        canvas.renderMode = RenderMode.ScreenSpaceOverlay;
        canvas.sortingOrder = 40; // under the terminal (50)
        var scaler = go.GetComponent<CanvasScaler>();
        scaler.uiScaleMode = CanvasScaler.ScaleMode.ScaleWithScreenSize;
        scaler.referenceResolution = new Vector2(1920, 1080);
        scaler.matchWidthOrHeight = 0.5f;

        var fade = new GameObject("Fade", typeof(RectTransform), typeof(Image), typeof(CanvasGroup));
        fade.transform.SetParent(go.transform, false);
        var frt = (RectTransform)fade.transform;
        frt.anchorMin = Vector2.zero; frt.anchorMax = Vector2.one; frt.offsetMin = frt.offsetMax = Vector2.zero;
        var img = fade.GetComponent<Image>();
        img.color = fadeColor;
        img.raycastTarget = false;
        m_Fade = fade.GetComponent<CanvasGroup>();
        m_Fade.alpha = 0f;
        m_Fade.blocksRaycasts = false;

        var msg = new GameObject("Message", typeof(RectTransform), typeof(TextMeshProUGUI));
        msg.transform.SetParent(go.transform, false);
        var mrt = (RectTransform)msg.transform;
        mrt.anchorMin = new Vector2(0, 1); mrt.anchorMax = new Vector2(1, 1); mrt.pivot = new Vector2(0, 1);
        mrt.offsetMin = new Vector2(48, -110); mrt.offsetMax = new Vector2(-48, -36);
        m_Message = msg.GetComponent<TextMeshProUGUI>();
        if (font != null) m_Message.font = font;
        m_Message.fontSize = 46;
        m_Message.alignment = TextAlignmentOptions.TopLeft;
        m_Message.raycastTarget = false;
        m_Message.text = "";
    }
}
