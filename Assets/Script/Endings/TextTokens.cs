/// <summary>
/// Placeholders you can write in terminal / dialog / caption text:
///   {ATTEMPTS}    previous attempts, 3 digits   (e.g. 047)
///   {ATTEMPTS_N}  previous attempts, plain      (e.g. 47)
///   {SECTORS}     lifecycle progress            (e.g. 2 / 4)
/// </summary>
public static class TextTokens
{
    public static string Apply(string text)
    {
        if (string.IsNullOrEmpty(text) || text.IndexOf('{') < 0) return text;
        var lp = LifecycleProgress.Instance;
        return text
            .Replace("{ATTEMPTS}", Endings.Attempts.ToString("000"))
            .Replace("{ATTEMPTS_N}", Endings.Attempts.ToString())
            .Replace("{SECTORS}", lp != null ? $"{lp.RestoredCount} / {lp.SectorsRequired}" : "0 / 4");
    }
}
