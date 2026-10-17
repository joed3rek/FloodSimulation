// Shared mapping from survey metres to Unity world space: +X east, +Z north, +Y up (1 unit = 1 m),
// heights relative to the lowest existing ground and multiplied by the vertical exaggeration.
using UnityEngine;

namespace SpongePark
{
    public class SiteFrame
    {
        public float X0, Y0, ZRef, Exaggeration = 5f;

        public static SiteFrame From(HeightGrid existing, float exaggeration)
        {
            return new SiteFrame
            {
                X0 = existing.Origin.x,
                Y0 = existing.Origin.y - existing.Rows * existing.Cell,
                ZRef = existing.ZMin,
                Exaggeration = exaggeration
            };
        }

        public Vector3 World(float x, float y, float z) => new Vector3(x - X0, (z - ZRef) * Exaggeration, y - Y0);
    }
}
