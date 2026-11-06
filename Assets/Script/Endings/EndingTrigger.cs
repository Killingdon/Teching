using System.Collections;
using UnityEngine;

/// <summary>
/// Starts an ending from a UnityEvent, e.g. a TerminalCommand's On Execute -> EndingTrigger.PlayBad.
/// Waits for the terminal to finish typing its reply, closes it, then loads the ending cutscene.
/// </summary>
public class EndingTrigger : MonoBehaviour
{
    [Tooltip("Extra seconds after the terminal has finished typing, so the player can read the last line")]
    public float readDelay = 1.2f;

    bool m_Started;

    public void PlayFail() => Begin(GameEnding.Fail);
    public void PlayBad() => Begin(GameEnding.Bad);
    public void PlayGood() => Begin(GameEnding.Good);

    public void Begin(GameEnding ending)
    {
        if (m_Started) return;
        m_Started = true;
        StartCoroutine(Run(ending));
    }

    IEnumerator Run(GameEnding ending)
    {
        yield return null; // let the terminal queue the command's reply first
        var terminal = TerminalController.Instance;
        while (terminal != null && TerminalController.IsOpen && terminal.IsBusy) yield return null;
        for (float t = 0; t < readDelay; t += Time.unscaledDeltaTime) yield return null;
        if (terminal != null && TerminalController.IsOpen)
        {
            terminal.Close();
            for (float t = 0; t < 0.4f; t += Time.unscaledDeltaTime) yield return null;
        }
        Endings.Play(ending);
    }
}
