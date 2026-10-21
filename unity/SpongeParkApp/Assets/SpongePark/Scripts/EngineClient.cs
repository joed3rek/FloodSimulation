// HTTP client for the local spongepark engine API (spongepark serve), with a read-only fallback to a
// viewer bundle in StreamingAssets/bundle (WebGL results viewer: no engine, no computation).
using System;
using System.Collections;
using System.Text;
using Newtonsoft.Json;
using Newtonsoft.Json.Linq;
using UnityEngine;
using UnityEngine.Networking;

namespace SpongePark
{
    public class EngineClient : MonoBehaviour
    {
        public string baseUrl = "http://127.0.0.1:8765";
        public bool bundleMode;          // true: read results from StreamingAssets/bundle only
        public string ProjectId { get; private set; }
        public JObject BundleManifest { get; private set; }
        public string LastError { get; private set; } = "";
        /// Forget the last error (before a new piece of work, or after optional data that may be missing).
        public void ClearError() => LastError = "";
        /// What the running engine can do (empty for an engine older than this app).
        public string[] Features { get; private set; } = new string[0];
        public bool Current => Array.IndexOf(Features, "intake") >= 0;
        /// The engine's code changed after it started (an update it has not loaded yet).
        public bool Stale { get; private set; }

        public IEnumerator Get(string path, Action<JToken> done, int timeoutS = 600)
        {
            using var req = UnityWebRequest.Get(baseUrl + path);
            req.timeout = timeoutS;
            yield return req.SendWebRequest();
            Finish(req, done);
        }

        /// Raw bytes (e.g. a PNG preview); null on failure.
        public IEnumerator GetBytes(string path, Action<byte[]> done)
        {
            using var req = UnityWebRequest.Get(baseUrl + path);
            req.timeout = 120;
            yield return req.SendWebRequest();
            done(req.result == UnityWebRequest.Result.Success ? req.downloadHandler.data : null);
        }

        public IEnumerator Send(string method, string path, object body, Action<JToken> done, int timeoutS = 3600)
        {
            var json = body == null ? "{}" : JsonConvert.SerializeObject(body);
            using var req = new UnityWebRequest(baseUrl + path, method)
            {
                uploadHandler = new UploadHandlerRaw(Encoding.UTF8.GetBytes(json)),
                downloadHandler = new DownloadHandlerBuffer(),
                timeout = timeoutS
            };
            req.SetRequestHeader("Content-Type", "application/json");
            yield return req.SendWebRequest();
            Finish(req, done);
        }

        void Finish(UnityWebRequest req, Action<JToken> done)
        {
            if (req.result != UnityWebRequest.Result.Success)
            {
                LastError = $"{req.url}: {req.error} {req.downloadHandler?.text}";
                Debug.LogWarning(LastError);
                done?.Invoke(null);
                return;
            }
            LastError = "";
            done?.Invoke(JToken.Parse(req.downloadHandler.text));
        }

        /// Starts an engine job and polls until it ends. progress gets the job status text.
        public IEnumerator RunJob(string method, string path, object body, Action<JToken> done, Action<string> progress = null)
        {
            JToken started = null;
            yield return Send(method, path, body, r => started = r);
            if (started == null) { done?.Invoke(null); yield break; }
            if (started["job"] == null) { done?.Invoke(started); yield break; }
            var jid = (string)started["job"];
            while (true)
            {
                JToken s = null;
                yield return Get("/jobs/" + jid, r => s = r);
                if (s == null) { done?.Invoke(null); yield break; }
                var status = (string)s["status"];
                progress?.Invoke(status);
                if (status == "done") { done?.Invoke(s["result"]); yield break; }
                if (status == "error") { LastError = (string)s["error"]; Debug.LogError(LastError); done?.Invoke(null); yield break; }
                yield return new WaitForSecondsRealtime(1f);
            }
        }

        bool? reachable;   // the last health result, so the log says when it changes rather than every poll

        /// attempts: 3 lets an engine busy with a long job answer; 1 for a quick look before starting one.
        public IEnumerator Health(Action<bool> done, int attempts = 3)
        {
            for (int attempt = 0; attempt < attempts; attempt++)
            {
                using var req = UnityWebRequest.Get(baseUrl + "/health");
                req.timeout = 5;
                yield return req.SendWebRequest();
                if (req.result == UnityWebRequest.Result.Success)
                {
                    try
                    {
                        var h = JToken.Parse(req.downloadHandler.text);
                        Features = h["features"]?.ToObject<string[]>() ?? new string[0];
                        Stale = (bool?)h["stale"] == true;
                    }
                    catch (Exception) { Features = new string[0]; Stale = false; }
                    if (reachable != true) Debug.Log("engine connected: " + baseUrl);
                    reachable = true;
                    done(true);
                    yield break;
                }
                LastError = $"{baseUrl}/health: {req.error}";
            }
            // not running is normal before the app starts it; only losing a running engine is worth a warning
            if (reachable == true) Debug.LogWarning("engine stopped answering: " + LastError);
            reachable = false;
            done(false);
        }

        public IEnumerator Open(string path, bool create, Action<JToken> done)
        {
            yield return Send("POST", "/projects/open", new { path, create }, r =>
            {
                if (r != null) ProjectId = (string)r["project"];
                done?.Invoke(r);
            });
        }

        public string P(string rest) => $"/projects/{ProjectId}{rest}";

        // ------------------------------------------------------------ viewer bundle (read-only)
        public IEnumerator LoadBundleFile(string name, Action<JToken> done)
        {
            var url = System.IO.Path.Combine(Application.streamingAssetsPath, "bundle", name);
            if (!url.Contains("://")) url = "file://" + url;
            using var req = UnityWebRequest.Get(url);
            yield return req.SendWebRequest();
            if (req.result != UnityWebRequest.Result.Success) { LastError = req.error; done(null); yield break; }
            done(JToken.Parse(req.downloadHandler.text));
        }

        public IEnumerator OpenBundle(Action<JObject> done)
        {
            yield return LoadBundleFile("manifest.json", r => { BundleManifest = r as JObject; done(BundleManifest); });
        }
    }
}
