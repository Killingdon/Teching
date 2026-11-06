using System;
using System.Collections;
using System.Collections.Generic;
using UnityEngine;

/// <summary>Every sound effect the game plays. Clips are assigned on the AudioManager.</summary>
public enum Sfx
{
    Hover, Click, Type, TerminalOpen, TerminalClose, Accept, Error,
    DoorOpen, DoorLocked, DoorUnlock, RoomTransition, Paper,
    TapeRecStart, TapeRecStop, TapeRewind,
    BlastDoor, PowerUp, Glitch, // intro cutscene (always add new ids at the END: Unity stores them as numbers)
    PowerDown, CountdownBeep, Nuke, // endings
}

[Serializable]
public class SfxEntry
{
    public Sfx id;
    public AudioClip clip;
    [Range(0f, 1f)] public float volume = 1f;
    [Tooltip("Random pitch variation (+/-), makes repeated sounds less robotic")]
    [Range(0f, 0.5f)] public float pitchJitter = 0f;
}

/// <summary>
/// Music (cross-fades between tracks), per-room ambience loops and one-shot sound effects,
/// with separate Music / SFX / Ambience volumes saved in PlayerPrefs (GDD 11.1).
///
/// Play a sound from anywhere:  AudioManager.Play(Sfx.DoorOpen);
/// Rooms choose their music + ambience (Room component); the manager follows RoomManager.
/// </summary>
public class AudioManager : MonoBehaviour
{
    public static AudioManager Instance { get; private set; }

    [Header("Music")]
    [Tooltip("Plays when a room doesn't set its own music")]
    [SerializeField] AudioClip defaultMusic;
    [SerializeField] float musicFadeTime = 2.5f;
    [SerializeField] float ambienceFadeTime = 1.2f;

    [Header("Volumes (defaults; the player's saved values override them)")]
    [Range(0f, 1f)] [SerializeField] float musicVolume = 0.55f;
    [Range(0f, 1f)] [SerializeField] float sfxVolume = 0.8f;
    [Range(0f, 1f)] [SerializeField] float ambienceVolume = 0.6f;

    [Header("Sound effects")]
    [SerializeField] List<SfxEntry> sounds = new List<SfxEntry>();
    [SerializeField] int voices = 12;

    const string MusicKey = "rewind.volume.music", SfxKey = "rewind.volume.sfx", AmbKey = "rewind.volume.ambience";

    readonly Dictionary<Sfx, SfxEntry> m_Lookup = new Dictionary<Sfx, SfxEntry>();
    readonly AudioSource[] m_Music = new AudioSource[2];
    readonly AudioSource[] m_Amb = new AudioSource[2];
    readonly float[] m_MusicFade = new float[2];
    readonly float[] m_AmbFade = new float[2];
    AudioSource[] m_Voices;
    int m_NextVoice, m_MusicActive, m_AmbActive;
    Coroutine m_MusicRoutine, m_AmbRoutine;

    public float MusicVolume { get => musicVolume; set { musicVolume = Mathf.Clamp01(value); Save(); } }
    public float SfxVolume { get => sfxVolume; set { sfxVolume = Mathf.Clamp01(value); Save(); } }
    public float AmbienceVolume { get => ambienceVolume; set { ambienceVolume = Mathf.Clamp01(value); Save(); } }
    public AudioClip CurrentMusic => m_Music[m_MusicActive].clip;
    public AudioClip CurrentAmbience => m_Amb[m_AmbActive].clip;

    // ------------------------------------------------------------------ lifecycle

    void Awake()
    {
        if (Instance != null && Instance != this) { Destroy(gameObject); return; }
        Instance = this;
        if (transform.parent == null) DontDestroyOnLoad(gameObject);

        musicVolume = PlayerPrefs.GetFloat(MusicKey, musicVolume);
        sfxVolume = PlayerPrefs.GetFloat(SfxKey, sfxVolume);
        ambienceVolume = PlayerPrefs.GetFloat(AmbKey, ambienceVolume);

        foreach (var s in sounds) if (s != null && s.clip != null) m_Lookup[s.id] = s;
        for (int i = 0; i < 2; i++)
        {
            m_Music[i] = NewSource("Music " + i, true);
            m_Amb[i] = NewSource("Ambience " + i, true);
        }
        m_Voices = new AudioSource[Mathf.Max(1, voices)];
        for (int i = 0; i < m_Voices.Length; i++) m_Voices[i] = NewSource("Voice " + i, false);

        RoomManager.RoomChanged += OnRoomChanged;
    }

    void OnDestroy()
    {
        RoomManager.RoomChanged -= OnRoomChanged;
        if (Instance == this) Instance = null;
    }

    void Start()
    {
        // No rooms in this scene: just play the default music.
        if (RoomManager.Instance == null && defaultMusic != null) PlayMusic(defaultMusic);
    }

    void Update()
    {
        for (int i = 0; i < 2; i++)
        {
            m_Music[i].volume = m_MusicFade[i] * musicVolume;
            m_Amb[i].volume = m_AmbFade[i] * ambienceVolume;
        }
    }

    AudioSource NewSource(string name, bool loop)
    {
        var go = new GameObject(name);
        go.transform.SetParent(transform, false);
        var src = go.AddComponent<AudioSource>();
        src.playOnAwake = false;
        src.loop = loop;
        src.spatialBlend = 0f;
        return src;
    }

    void OnRoomChanged(Room room)
    {
        PlayMusic(room.music != null ? room.music : defaultMusic);
        PlayAmbience(room.ambience);
    }

    // ------------------------------------------------------------------ SFX

    /// <summary>Plays a sound effect by id (silently does nothing without an AudioManager).</summary>
    public static void Play(Sfx id, float volumeScale = 1f)
    {
        if (Instance != null) Instance.PlaySfx(id, volumeScale);
    }

    public void PlaySfx(Sfx id, float volumeScale = 1f)
    {
        if (m_Lookup.TryGetValue(id, out var s)) PlayClip(s.clip, s.volume * volumeScale, s.pitchJitter);
    }

    /// <summary>Plays any clip as a sound effect (uses the SFX volume).</summary>
    public void PlayClip(AudioClip clip, float volume = 1f, float pitchJitter = 0f)
    {
        if (clip == null || sfxVolume <= 0f) return;
        var v = m_Voices[m_NextVoice];
        m_NextVoice = (m_NextVoice + 1) % m_Voices.Length;
        v.pitch = 1f + (pitchJitter > 0 ? UnityEngine.Random.Range(-pitchJitter, pitchJitter) : 0f);
        v.PlayOneShot(clip, volume * sfxVolume);
    }

    // ------------------------------------------------------------------ music / ambience

    public void PlayMusic(AudioClip clip) => CrossFade(m_Music, m_MusicFade, ref m_MusicActive, ref m_MusicRoutine, clip, musicFadeTime);
    public void PlayAmbience(AudioClip clip) => CrossFade(m_Amb, m_AmbFade, ref m_AmbActive, ref m_AmbRoutine, clip, ambienceFadeTime);

    void CrossFade(AudioSource[] pair, float[] fades, ref int active, ref Coroutine routine, AudioClip clip, float time)
    {
        if (pair[active].clip == clip && (clip == null || pair[active].isPlaying)) return;
        int next = 1 - active;
        pair[next].clip = clip;
        if (clip != null) pair[next].Play();
        if (routine != null) StopCoroutine(routine);
        routine = StartCoroutine(FadeRoutine(pair, fades, active, next, time));
        active = next;
    }

    IEnumerator FadeRoutine(AudioSource[] pair, float[] fades, int from, int to, float time)
    {
        float startFrom = fades[from], startTo = fades[to];
        for (float t = 0; t < time; t += Time.unscaledDeltaTime)
        {
            float k = t / time;
            fades[from] = Mathf.Lerp(startFrom, 0f, k);
            fades[to] = pair[to].clip != null ? Mathf.Lerp(startTo, 1f, k) : 0f;
            yield return null;
        }
        fades[from] = 0f;
        fades[to] = pair[to].clip != null ? 1f : 0f;
        pair[from].Stop();
    }

    void Save()
    {
        PlayerPrefs.SetFloat(MusicKey, musicVolume);
        PlayerPrefs.SetFloat(SfxKey, sfxVolume);
        PlayerPrefs.SetFloat(AmbKey, ambienceVolume);
        PlayerPrefs.Save();
    }
}
