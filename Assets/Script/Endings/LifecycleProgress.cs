using UnityEngine;
using UnityEngine.Events;

/// <summary>
/// Tracks the four sectors the operator must restore (see the intro) and decides the ending:
///   * RestoreSector(n)   - call from your quests (e.g. a code command's On Execute).
///   * TryRestartCycle()  - the main computer's RESTART CYCLE command:
///         all sectors restored        -> Good ending (Lifecycle Mode)
///         otherwise                   -> "RESTART FAILED"; after Max Failed Restarts -> Fail ending
/// Text anywhere in the terminal can show progress with the token {SECTORS} (e.g. "2 / 4").
/// </summary>
[RequireComponent(typeof(EndingTrigger))]
public class LifecycleProgress : MonoBehaviour
{
    public static LifecycleProgress Instance { get; private set; }

    [SerializeField] int sectorsRequired = 4;
    [Tooltip("Failed RESTART CYCLE attempts before life support collapses (Fail ending). 0 = never")]
    [SerializeField] int maxFailedRestarts = 3;

    [Tooltip("Fired with the sector number (1-4) when a sector is restored")]
    public UnityEvent<int> onSectorRestored = new UnityEvent<int>();
    public UnityEvent onAllSectorsRestored = new UnityEvent();

    bool[] m_Restored;
    int m_FailedRestarts;
    EndingTrigger m_Endings;

    public int SectorsRequired => sectorsRequired;
    public int RestoredCount { get { int n = 0; foreach (var r in m_Restored) if (r) n++; return n; } }
    public bool AllRestored => RestoredCount >= sectorsRequired;
    public int FailedRestarts => m_FailedRestarts;
    public bool IsRestored(int sector) => sector >= 1 && sector <= sectorsRequired && m_Restored[sector - 1];

    void Awake()
    {
        Instance = this;
        m_Restored = new bool[Mathf.Max(1, sectorsRequired)];
        m_Endings = GetComponent<EndingTrigger>();
    }

    void OnDestroy()
    {
        if (Instance == this) Instance = null;
    }

    /// <summary>Marks a sector (1-based) as restored.</summary>
    public void RestoreSector(int sector)
    {
        if (sector < 1 || sector > sectorsRequired) { Debug.LogWarning($"[Lifecycle] No sector {sector}", this); return; }
        if (m_Restored[sector - 1]) { Say($"SECTOR {sector:00} IS ALREADY ONLINE.", 1); return; }
        m_Restored[sector - 1] = true;
        AudioManager.Play(Sfx.Accept);
        Say($"SECTOR {sector:00} RESTORED. LIFECYCLE: {RestoredCount} / {sectorsRequired}", 0);
        onSectorRestored.Invoke(sector);
        if (AllRestored)
        {
            Say("ALL SECTORS ONLINE. RUN 'RESTART CYCLE' ON THE MAIN COMPUTER.", 1);
            onAllSectorsRestored.Invoke();
        }
    }

    /// <summary>Restarts the lifecycle system: Good ending if every sector is restored, otherwise a failed attempt.</summary>
    public void TryRestartCycle()
    {
        if (AllRestored)
        {
            Say("ALL SECTORS ONLINE. RESTARTING LIFECYCLE SYSTEM...", 0);
            m_Endings.PlayGood();
            return;
        }
        m_FailedRestarts++;
        AudioManager.Play(Sfx.Error);
        Say($"RESTART FAILED: SECTORS RESTORED {RestoredCount} / {sectorsRequired}.", 2);
        if (maxFailedRestarts <= 0) return;
        int left = maxFailedRestarts - m_FailedRestarts;
        if (left <= 0)
        {
            Say("CRITICAL FAILURE. LIFE SUPPORT COLLAPSING.", 2);
            m_Endings.PlayFail();
        }
        else Say($"WARNING: LIFE SUPPORT DEGRADING. {left} RESTART ATTEMPT{(left == 1 ? "" : "S")} LEFT.", 1);
    }

    public void ResetProgress()
    {
        for (int i = 0; i < m_Restored.Length; i++) m_Restored[i] = false;
        m_FailedRestarts = 0;
    }

    /// <summary>0 = normal, 1 = warning, 2 = error. Uses the terminal if it's open, else the room message line.</summary>
    static void Say(string text, int kind)
    {
        var t = TerminalController.Instance;
        if (t != null && TerminalController.IsOpen)
        {
            if (kind == 2) t.PrintError(text);
            else if (kind == 1) t.PrintWarning(text);
            else t.Print(text);
        }
        else if (RoomManager.Instance != null) RoomManager.Instance.ShowMessage(text, kind == 2);
    }
}
