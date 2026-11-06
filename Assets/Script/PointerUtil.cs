using UnityEngine;
using UnityEngine.EventSystems;
using UnityEngine.InputSystem;

/// <summary>Mouse hover helpers shared by clickable world objects (computers, doors, notes...).</summary>
public static class PointerUtil
{
    static Camera s_Camera;

    /// <summary>True while the terminal is open or the screen is changing rooms.</summary>
    public static bool InteractionBlocked => TerminalController.IsOpen || RoomManager.IsTransitioning;

    /// <summary>Is the mouse over this collider (and not over UI)?</summary>
    public static bool IsPointerOver(Collider2D collider)
    {
        var mouse = Mouse.current;
        if (mouse == null || collider == null || !collider.enabled) return false;
        if (EventSystem.current != null && EventSystem.current.IsPointerOverGameObject()) return false;
        if (s_Camera == null || !s_Camera.isActiveAndEnabled) s_Camera = Camera.main;
        if (s_Camera == null) return false;

        Vector2 screen = mouse.position.ReadValue();
        Vector3 world = s_Camera.ScreenToWorldPoint(new Vector3(screen.x, screen.y, -s_Camera.transform.position.z));
        return collider.OverlapPoint(world);
    }

    public static bool ClickedThisFrame => Mouse.current != null && Mouse.current.leftButton.wasPressedThisFrame;
    public static bool InteractKeyThisFrame => Keyboard.current != null && Keyboard.current.eKey.wasPressedThisFrame;
}
