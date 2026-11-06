using UnityEngine;
using UnityEngine.SceneManagement;

public enum GameEnding
{
    /// <summary>The lifecycle restart fails; life support dies and the operator suffocates in the bunker.</summary>
    Fail,
    /// <summary>The operator does something unsafe; the bunker AI runs its kill protocol (nuclear blast).</summary>
    Bad,
    /// <summary>All sectors restored; the lifecycle system restarts correctly (Lifecycle Mode).</summary>
    Good,
}

/// <summary>
/// Plays the ending cutscenes and keeps the "previous attempts" counter (shown as {ATTEMPTS} in text).
/// From code: Endings.Play(GameEnding.Bad). From a UnityEvent: use an EndingTrigger component.
/// </summary>
public static class Endings
{
    public const string FailScene = "Ending_Fail";
    public const string BadScene = "Ending_Bad";
    public const string GoodScene = "Ending_Good";
    public const int FirstAttempt = 47; // GDD: "PREVIOUS ATTEMPTS: 047"

    const string AttemptsKey = "rewind.attempts";

    /// <summary>How many times the operator has failed. Goes up with every Fail / Bad ending; saved.</summary>
    public static int Attempts
    {
        get => PlayerPrefs.GetInt(AttemptsKey, FirstAttempt);
        set { PlayerPrefs.SetInt(AttemptsKey, Mathf.Max(0, value)); PlayerPrefs.Save(); }
    }

    public static GameEnding? LastEnding { get; private set; }

    public static string SceneFor(GameEnding ending)
    {
        switch (ending)
        {
            case GameEnding.Fail: return FailScene;
            case GameEnding.Bad: return BadScene;
            default: return GoodScene;
        }
    }

    /// <summary>Loads the ending's cutscene scene. Fail/Bad count as a failed attempt unless countAttempt is false.</summary>
    public static void Play(GameEnding ending, bool countAttempt = true)
    {
        LastEnding = ending;
        if (countAttempt && ending != GameEnding.Good) Attempts++;
        Debug.Log($"[Endings] {ending} ending (attempts: {Attempts:000})");
        SceneManager.LoadScene(SceneFor(ending));
    }
}
