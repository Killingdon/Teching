using System;
using UnityEngine;
using UnityEngine.Events;

/// <summary>
/// A custom command a computer adds to its terminal, e.g. "OPEN" that prints a reply
/// and fires an event (open a door, power a platform...). Edit these on ComputerController.
/// </summary>
[Serializable]
public class TerminalCommand
{
    [Tooltip("What the player types (case-insensitive). Can include a code: \"UNLOCK 4471\" only accepts that exact code.")]
    public string command = "COMMAND";

    [Tooltip("Optional extra names for the same command, e.g. UNLOCK")]
    public string[] aliases = Array.Empty<string>();

    [Tooltip("One-line description shown by HELP")]
    public string description = "";

    [Tooltip("Text printed when the command runs. Each line is typed out separately.")]
    [TextArea(2, 6)]
    public string response = "";

    [Tooltip("Fired after the response is queued - hook up doors, switches, platforms...")]
    public UnityEvent onExecute = new UnityEvent();

    public bool Matches(string input)
    {
        var n = Normalize(input);
        if (Normalize(command) == n) return true;
        foreach (var a in aliases)
            if (Normalize(a) == n) return true;
        return false;
    }

    /// <summary>First word of the command, e.g. "UNLOCK" for "UNLOCK 4471".</summary>
    public string Verb => Normalize(command).Split(' ')[0];

    public static string Normalize(string s) =>
        string.Join(" ", (s ?? "").Trim().ToUpperInvariant().Split((char[])null, StringSplitOptions.RemoveEmptyEntries));
}
