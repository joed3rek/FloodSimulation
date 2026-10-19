// The 3D surroundings and the weather, low-poly (built-in render pipeline):
// - the sky: the Synty sky dome when the low-poly packs are in (spongepark unity lowpoly-assets), else a plain sky
//   colour; haze towards the horizon;
// - rain while the storm plays: streaks as thick as the storm is at that moment, a greyer sky and flatter light,
//   darker wet ground and models, livelier water. It follows the storm's own rainfall series, minute by minute;
// - the 2D plan is a map on paper: no sky, haze or weather.
using UnityEngine;

namespace SpongePark
{
    public partial class SpongeParkApp
    {
        Light sun;
        GameObject skyLeft, skyRight;
        RainView rainLeft, rainRight;
        float rainShown, overcast, wetness;
        const float SunIntensity = 1.05f;
        static readonly Color SkyClear = new Color(0.62f, 0.78f, 0.92f), SkyCloud = new Color(0.62f, 0.65f, 0.68f);
        static readonly Color HazeClear = new Color(0.82f, 0.88f, 0.92f), HazeCloud = new Color(0.66f, 0.68f, 0.70f);

        void SetupEnvironment(Light light)
        {
            sun = light;
            sun.shadows = LightShadows.Soft;
            sun.shadowStrength = 0.6f;
            sun.color = new Color(1f, 0.96f, 0.88f);
            sun.intensity = SunIntensity;
            QualitySettings.shadowDistance = 700;
            QualitySettings.shadowResolution = ShadowResolution.High;
            QualitySettings.shadowCascades = 4;
            QualitySettings.shadowProjection = ShadowProjection.StableFit;
            RenderSettings.fogMode = FogMode.Linear;
            ApplyWeather();
        }

        /// The sky dome (one per side, on that side's layer), following the camera.
        void MakeSky()
        {
            var kit = LowPolyKit.Kit;
            if (kit == null || kit.skyDome == null) return;
            skyLeft = Dome(kit.skyDome, LayerLeft);
            skyRight = Dome(kit.skyDome, LayerRight);
        }

        GameObject Dome(GameObject prefab, int layer)
        {
            var go = Instantiate(prefab, transform);
            LowPolyKit.Prepare(go, layer);
            foreach (var r in go.GetComponentsInChildren<Renderer>())
            {
                r.shadowCastingMode = UnityEngine.Rendering.ShadowCastingMode.Off;
                r.receiveShadows = false;
                foreach (var m in r.materials) m.SetFloat("_Unlit", 1);   // its own copy: unlit, no haze
            }
            return go;
        }

        void MakeRain()
        {
            rainLeft = RainView.Create("rain left", transform, LayerLeft, camLeft);
            rainRight = RainView.Create("rain right", transform, LayerRight, camRight);
        }

        /// Each frame: how hard it is raining at this moment of the storm, and how the place looks under it.
        void UpdateWeather()
        {
            if (sun == null || left == null) return;
            float t = simT;
            bool storm = (playing || t > 0) && t < Mathf.Max(left.EndTime, right.EndTime);
            float rate = storm ? Mathf.Max(left.RainNow(t, live), right != null ? right.RainNow(t, live) : 0) : 0;
            float dt = Time.unscaledDeltaTime;
            rainShown = Mathf.Lerp(rainShown, rate, 1 - Mathf.Exp(-dt * 4));
            float cloudy = rate > 0.05f ? Mathf.Clamp01(0.45f + Mathf.Sqrt(rate / 40f) * 0.55f) : 0;
            overcast = Mathf.MoveTowards(overcast, cloudy, dt * 0.6f);
            wetness = rate > 0.05f ? Mathf.MoveTowards(wetness, 1, dt * 0.5f) : Mathf.MoveTowards(wetness, 0, dt / 20f);
            ApplyWeather();
            bool plan = rigLeft != null && rigLeft.Plan;
            rainLeft?.Show(plan ? 0 : rainShown, rigLeft != null ? rigLeft.Distance : 100);
            rainRight?.Show(plan || !sideBySide ? 0 : rainShown, rigRight != null ? rigRight.Distance : 100);
            FollowSky(skyLeft, camLeft, !plan);
            FollowSky(skyRight, camRight, !plan && sideBySide);
        }

        void FollowSky(GameObject dome, Camera cam, bool on)
        {
            if (dome == null) return;
            dome.SetActive(on);
            if (!on) return;
            dome.transform.position = cam.transform.position;
            // as large as the view reaches (inside the far clip plane), so the whole site stands inside it
            float radius = Mathf.Max(1f, LowPolyKit.Size(LowPolyKit.Kit.skyDome).extents.x);
            dome.transform.localScale = Vector3.one * (cam.farClipPlane * 0.8f / radius);
        }

        void ApplyWeather()
        {
            Shader.SetGlobalFloat("_RainRate", rainShown);
            Shader.SetGlobalFloat("_Wet", wetness);
            Shader.SetGlobalFloat("_Overcast", overcast);
            var haze = Color.Lerp(HazeClear, HazeCloud, overcast);
            RenderSettings.fogColor = haze;
            Shader.SetGlobalColor("_RainColour", Color.Lerp(haze, Color.white, 0.35f));
            sun.intensity = SunIntensity * (1 - 0.55f * overcast);
            sun.shadowStrength = 0.6f * (1 - 0.6f * overcast);
        }

        /// The 2D plan: a map on paper. 3D: the sky, haze and weather.
        void SyncEnvironment(bool plan)
        {
            Shader.SetGlobalFloat("_PlanView", plan ? 1 : 0);
            RenderSettings.fog = !plan;
            float near = Mathf.Lerp(1.4f, 0.5f, overcast), far = Mathf.Lerp(5f, 2.2f, overcast);
            RenderSettings.fogStartDistance = rigLeft.Distance * near;
            RenderSettings.fogEndDistance = rigLeft.Distance * far;
            if (!plan)
            {
                var sky = Color.Lerp(skyLeft != null ? HazeClear : SkyClear, SkyCloud, overcast);
                camLeft.backgroundColor = sky;
                camRight.backgroundColor = sky;
            }
        }
    }
}
