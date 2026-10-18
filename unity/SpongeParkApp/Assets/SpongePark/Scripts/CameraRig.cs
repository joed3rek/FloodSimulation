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
        /// Plan view: looking straight down, north up, without perspective (a 2D map of the site).
        public bool Plan;
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
                Target = Follow.Target; Distance = Follow.Distance; Yaw = Follow.Yaw; Pitch = Follow.Pitch; Plan = Follow.Plan;
            }
            else if (Touring)
            {
                Yaw += TourDegreesPerSecond * Time.deltaTime;
                Pitch = 30 + 10 * Mathf.Sin(Time.time * 0.15f);
            }
            else if (BlockInput == null || !BlockInput())
            {
                if (Plan && (Input.GetMouseButton(1) || Input.GetMouseButton(2)))
                {
                    Target -= new Vector3(Input.GetAxis("Mouse X"), 0, Input.GetAxis("Mouse Y")) * Distance * 0.02f;
                }
                else if (Input.GetMouseButton(1))
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
            var cam = GetComponent<Camera>();
            if (cam != null) cam.orthographic = Plan;
            if (Plan)
            {
                transform.rotation = Quaternion.Euler(90, 0, 0);   // north (+Z) up the screen
                transform.position = Target + Vector3.up * 500;
                if (cam != null) { cam.orthographicSize = Distance * 0.45f; cam.farClipPlane = 2000; }
                return;
            }
            var rot = Quaternion.Euler(Pitch, Yaw, 0);
            transform.position = Target - rot * Vector3.forward * Distance;
            transform.rotation = rot;
        }
    }
}
