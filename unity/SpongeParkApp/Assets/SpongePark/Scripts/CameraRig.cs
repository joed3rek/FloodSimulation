// Orbit camera (right mouse drag to orbit, wheel to zoom, middle drag to pan) and an automatic tour
// around the site for presentations and video export.
using UnityEngine;

namespace SpongePark
{
    public class CameraRig : MonoBehaviour
    {
        public Vector3 Target;
        public float Distance = 120, Yaw = 30, Pitch = 35;
        public bool Touring;
        public float TourDegreesPerSecond = 8;
        public CameraRig Follow;   // side-by-side: the second camera mirrors the first
        public static System.Func<bool> BlockInput;   // true while the pointer is over the interface

        public void Frame(Bounds b, bool narrow = true)
        {
            Target = b.center;
            Distance = Mathf.Max(b.size.x, b.size.z) * (narrow ? 1.7f : 1.05f) + 10;   // side-by-side views are narrow
        }

        void LateUpdate()
        {
            if (Follow != null)
            {
                Target = Follow.Target; Distance = Follow.Distance; Yaw = Follow.Yaw; Pitch = Follow.Pitch;
            }
            else if (Touring)
            {
                Yaw += TourDegreesPerSecond * Time.deltaTime;
                Pitch = 30 + 10 * Mathf.Sin(Time.time * 0.15f);
            }
            else if (BlockInput == null || !BlockInput())
            {
                if (Input.GetMouseButton(1))
                {
                    Yaw += Input.GetAxis("Mouse X") * 4;
                    Pitch = Mathf.Clamp(Pitch - Input.GetAxis("Mouse Y") * 4, 5, 85);
                }
                if (Input.GetMouseButton(2))
                {
                    var right = transform.right; right.y = 0;
                    var fwd = transform.forward; fwd.y = 0;
                    Target -= (right.normalized * Input.GetAxis("Mouse X") + fwd.normalized * Input.GetAxis("Mouse Y")) * Distance * 0.02f;
                }
                Distance = Mathf.Clamp(Distance * (1 - Input.mouseScrollDelta.y * 0.1f), 5, 2000);
            }
            var rot = Quaternion.Euler(Pitch, Yaw, 0);
            transform.position = Target - rot * Vector3.forward * Distance;
            transform.rotation = rot;
        }
    }
}
