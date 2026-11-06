using UnityEngine;
using UnityEngine.Events;

/// <summary>
/// One location of the complex. Everything that belongs to the room (background, computer,
/// doors, notes, quest objects) is a child of this object. RoomManager moves the camera to
/// the room and switches the other rooms off.
/// </summary>
public class Room : MonoBehaviour
{
    [Tooltip("Unique id, used by RoomManager.GoToRoom(\"id\") from UnityEvents / terminal commands")]
    public string roomId = "room_01";

    [Tooltip("Shown in the top-left corner when the player enters")]
    public string displayName = "SECTOR 01 // CONTROL ROOM";

    [Tooltip("Your design notes for this room (not shown in game)")]
    [TextArea(3, 8)] public string designNotes;

    [Tooltip("Optional: where the camera looks. Default = this object's position")]
    public Transform cameraPoint;

    [Header("Audio")]
    [Tooltip("Music for this room (empty = AudioManager's default music)")]
    public AudioClip music;
    [Tooltip("Looping room tone (machines, hum, air)")]
    public AudioClip ambience;

    public UnityEvent onEnter = new UnityEvent();
    public UnityEvent onExit = new UnityEvent();

    public Vector3 CameraPosition => cameraPoint != null ? cameraPoint.position : transform.position;

    void OnDrawGizmos()
    {
        // Outline of the 320x180 view (20 x 11.25 units) so rooms are easy to lay out in the Scene view.
        Gizmos.color = new Color(0.4f, 1f, 0.6f, 0.6f);
        Gizmos.DrawWireCube(CameraPosition, new Vector3(20f, 11.25f, 0f));
    }
}
