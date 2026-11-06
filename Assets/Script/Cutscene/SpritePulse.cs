using UnityEngine;

/// <summary>Makes a sprite's alpha pulse (emergency lights, glows), with optional random flicker.</summary>
[RequireComponent(typeof(SpriteRenderer))]
public class SpritePulse : MonoBehaviour
{
    [Range(0f, 1f)] public float minAlpha = 0.45f;
    [Range(0f, 1f)] public float maxAlpha = 1f;
    [Tooltip("Pulses per second")]
    public float speed = 0.6f;
    [Tooltip("Chance per second of a short flicker")]
    public float flickerChance = 0.3f;

    SpriteRenderer m_Sr;
    float m_Flicker;

    void Awake() => m_Sr = GetComponent<SpriteRenderer>();

    void Update()
    {
        float k = 0.5f + 0.5f * Mathf.Sin(Time.time * speed * Mathf.PI * 2f);
        float a = Mathf.Lerp(minAlpha, maxAlpha, k);
        if (m_Flicker > 0) { m_Flicker -= Time.deltaTime; a *= 0.4f; }
        else if (Random.value < flickerChance * Time.deltaTime) m_Flicker = Random.Range(0.04f, 0.12f);
        var c = m_Sr.color;
        c.a = a;
        m_Sr.color = c;
    }
}
