// Site setup > Inlets and outlets: the designer places each place water gets in or out of the site, and says what it is:
// an existing site condition or part of the design. Everywhere else the edge holds the water. Nothing is assumed: a
// model-based project asks before it is analysed, and the list has to be confirmed even when it is empty.
// The same pins can be edited on the Analyse tab without going back to Site setup: drag a pin to move it, click it to
// edit, copy or remove it, and Add outlet / Add inlet on the ribbon.
// An outlet's level is asked on the survey's own levels (its invert or bottom level, as surveys mark it), filled in
// with the ground there; the app works out whether that is above or below the ground.
using System.Collections;
using System.Collections.Generic;
using System.Globalization;
using System.Linq;
using Newtonsoft.Json.Linq;
using UnityEngine;
using UnityEngine.UIElements;

namespace SpongePark
{
    public partial class SpongeParkApp
    {
        static readonly List<string> OriginTitles = new List<string> { "Choose…", "Existing site condition", "Part of the new design" };
        static readonly string[] OriginIds = { null, "site", "design" };

        JToken openingsData;
        VisualElement openingsCard, openingsRows, openingForm;
        Label openingsText;
        Button openingsDone;
        string placing;     // "outlet" or "inlet" while the next click on the site places one
        JObject placingCopy;            // while placing a copy: the opening it copies
        bool openingsFromAnalyse;       // placing or editing from the Analyse tab: stay there afterwards
        readonly List<GameObject> openingMarkers = new List<GameObject>();
        int openingHover = -1, openingDrag = -1;
        Vector2 openingDragAt;
        bool openingDragMoved;

        bool NeedOpenings => (bool?)info?["from_model"] == true && (bool?)info?["openings_confirmed"] != true;

        void AskOpenings()
        {
            status = "Before analysing: where does water enter or leave this site?";
            siteSetup.Open("outfalls");
        }

        void BuildOpenings(VisualElement page)
        {
            openingsCard = new VisualElement();
            openingsCard.Add(Text("INLETS AND OUTLETS", "eyebrow"));
            openingsText = Text("", "muted");
            openingsCard.Add(openingsText);
            var buttons = Row("field-row");
            buttons.Add(Btn("Place an outlet", () => BeginPlacing("outlet"), "btn--outline"));
            buttons.Add(Btn("Place an inlet", () => BeginPlacing("inlet"), "btn--outline"));
            openingsCard.Add(buttons);
            openingsRows = new VisualElement();
            openingsCard.Add(openingsRows);
            openingsDone = Btn("That is all of them", () => StartCoroutine(Run(SaveOpenings(Rows(), true, false), "Saving the inlets and outlets")), "btn--wide");
            openingsCard.Add(openingsDone);
            page.Add(openingsCard);
        }

        JArray Rows() => openingsData?["openings"] as JArray ?? new JArray();

        IEnumerator LoadOpenings()
        {
            JToken st = null;
            yield return api.Get(api.P("/site/openings"), x => st = x);
            api.ClearError();
            openingsData = st;
            FillOpenings();
            BuildOpeningMarkers();
        }

        static string F2(float v) => v.ToString("0.00", CultureInfo.InvariantCulture);

        /// "0.22 m below the ground here" (or above, or level with it).
        static string AgainstGround(float level, float ground)
        {
            float d = level - ground;
            if (Mathf.Abs(d) < 0.005f) return "level with the ground here";
            return $"{Mathf.Abs(d):0.00} m {(d < 0 ? "below" : "above")} the ground here";
        }

        static string Describe(JToken o)
        {
            var origin = (string)o["origin"] == "design" ? "part of the design" : "existing site condition";
            if ((string)o["kind"] != "outlet")
                return $"Inlet · {(float)o["area_m2"]:N0} m² draining, {(float)o["runoff_pct"]:0}% arrives · {origin}";
            string level = o["invert_m"] != null && o["invert_m"].Type != JTokenType.Null
                ? $"level {F2((float)o["invert_m"])} m" + (o["ground_m"] != null ? $" ({AgainstGround((float)o["invert_m"], (float)o["ground_m"])})" : "")
                : $"sill {(float)o["sill_m"]:0.##} m above the ground";
            return $"Outlet · {(float)o["width_m"]:0.##} m wide · {level} · {origin}";
        }

        void FillOpenings()
        {
            if (openingsCard == null || openingsData == null) return;
            bool confirmed = (bool?)openingsData["confirmed"] == true;
            openingsText.text = (string)openingsData["question"] + (confirmed ? "\nConfirmed: this is the full list." : "\nNot confirmed yet.");
            openingsRows.Clear();
            int k = 0;
            foreach (var o in Rows().ToList())
            {
                int index = k++;
                float x = (float)o["x"], y = (float)o["y"];
                var row = Row("field-row");
                row.Add(Text(Describe(o), "field-label"));
                row.Add(Btn("Show", () => FocusOn(x, y, GroundZ(x, y), 30), "btn--ghost"));
                row.Add(Btn("Edit", () => { openingsFromAnalyse = false; StartCoroutine(OpenOpeningForm((string)o["kind"], x, y, 0, index)); }, "btn--ghost"));
                row.Add(Btn("Remove", () => RemoveOpening(index), "btn--ghost"));
                openingsRows.Add(row);
            }
            foreach (var g in openingsData["gaps"] ?? new JArray())
            {
                float x = (float)g["x"], y = (float)g["y"];
                var row = Row("field-row");
                row.Add(Text($"Gap in the wall, {(float)g["width_m"]:0.#} m wide: closed unless you say otherwise", "field-label"));
                row.Add(Btn("Show", () => FocusOn(x, y, GroundZ(x, y), 30), "btn--ghost"));
                row.Add(Btn("Outlet", () => { openingsFromAnalyse = false; StartCoroutine(OpenOpeningForm("outlet", x, y, (float)g["width_m"])); }, "btn--ghost"));
                row.Add(Btn("Inlet", () => { openingsFromAnalyse = false; StartCoroutine(OpenOpeningForm("inlet", x, y, 0)); }, "btn--ghost"));
                openingsRows.Add(row);
            }
            openingsDone.text = Rows().Count == 0 ? "None: no water gets in or out" : "That is all of them";
        }

        void BeginPlacing(string kind, bool fromAnalyse = false, JObject copy = null)
        {
            placing = kind;
            placingCopy = copy;
            openingsFromAnalyse = fromAnalyse;
            siteSetup.Close();
            status = copy != null ? $"Click where the copy of {copy["id"]} goes. Esc cancels."
                   : kind == "outlet" ? "Click the edge of the site where water leaves. Esc cancels."
                   : "Click where water comes into the site. Esc cancels.";
        }

        void BackToOpenings()
        {
            if (!openingsFromAnalyse) siteSetup.Open("outfalls");
        }

        /// Placing, and on the Analyse tab moving and picking the pins. True when it has the pointer, so nothing else takes it.
        bool OpeningsInput()
        {
            if (placing != null)
            {
                if (Input.GetKeyDown(KeyCode.Escape)) { placing = null; placingCopy = null; status = ""; BackToOpenings(); return true; }
                if (CameraRig.BlockInput != null && CameraRig.BlockInput()) return true;
                if (Input.GetMouseButtonDown(0) && PickGround(out var xy, out _))
                {
                    var kind = placing;
                    placing = null;
                    if (placingCopy != null)
                    {
                        var row = (JObject)placingCopy.DeepClone();
                        placingCopy = null;
                        row.Remove("id");
                        row.Remove("ground_m");
                        row.Remove("sill_m");
                        row["x"] = xy.x;
                        row["y"] = xy.y;
                        var rows = (JArray)Rows().DeepClone();
                        rows.Add(row);
                        StartCoroutine(Run(SaveOpenings(rows, false, false), "Saving the copy"));
                    }
                    else StartCoroutine(OpenOpeningForm(kind, xy.x, xy.y, 0));
                }
                return true;
            }
            return AnalyseOpeningsInput();
        }

        bool EditingOpeningsOnMap => ui.ActiveTab == SpongePark.UI.Tab.Analyse && openingsData != null && frame != null && !busy && !live && !playing
                                     && !siteSetup.IsOpen && (openingForm == null || openingForm.parent == null);

        /// Analyse tab: hover a pin to find it, drag it to move it, click it to edit, copy or remove it.
        bool AnalyseOpeningsInput()
        {
            if (!EditingOpeningsOnMap) { SetOpeningHover(-1); openingDrag = -1; return false; }
            bool blocked = CameraRig.BlockInput != null && CameraRig.BlockInput();
            bool onGround = PickGround(out var xy, out _);
            if (openingDrag >= 0)
            {
                var rows = Rows();
                if (openingDrag >= rows.Count) { openingDrag = -1; return false; }
                if (onGround && (xy - openingDragAt).magnitude > 0.3f) openingDragMoved = true;
                if (openingDragMoved && onGround)
                {
                    openingMarkers[openingDrag].transform.position = frame.World(xy.x, xy.y, GroundZ(xy.x, xy.y)) + Vector3.up * 2.5f;
                    status = $"Moving {rows[openingDrag]["id"]} {(xy - openingDragAt).magnitude:0.0} m. Let go to place it; Esc cancels.";
                }
                if (Input.GetKeyDown(KeyCode.Escape)) { openingDrag = -1; BuildOpeningMarkers(); status = ""; return true; }
                if (Input.GetMouseButtonUp(0))
                {
                    int k = openingDrag;
                    openingDrag = -1;
                    if (openingDragMoved && onGround)
                    {
                        var next = (JArray)rows.DeepClone();
                        next[k]["x"] = xy.x;
                        next[k]["y"] = xy.y;
                        openingsFromAnalyse = true;
                        StartCoroutine(Run(SaveOpenings(next, false, false), "Moving the outlet"));
                    }
                    else
                    {
                        openingsFromAnalyse = true;
                        StartCoroutine(OpenOpeningForm((string)rows[k]["kind"], (float)rows[k]["x"], (float)rows[k]["y"], 0, k));
                    }
                }
                return true;
            }
            int hit = !blocked && onGround ? OpeningAt(xy) : -1;
            SetOpeningHover(hit);
            if (hit < 0) return false;
            status = $"{Rows()[hit]["id"]}: drag to move it, click to edit, copy or remove it.";
            if (Input.GetMouseButtonDown(0))
            {
                openingDrag = hit;
                openingDragAt = xy;
                openingDragMoved = false;
            }
            return true;
        }

        bool OpeningHandleActive => openingDrag >= 0 || openingHover >= 0 || placing != null;

        int OpeningAt(Vector2 xy)
        {
            float reach = Mathf.Max(2f, rigLeft.Distance * 0.015f), best = reach;
            int found = -1, k = 0;
            foreach (var o in Rows())
            {
                float d = (new Vector2((float)o["x"], (float)o["y"]) - xy).magnitude;
                if (d < best) { best = d; found = k; }
                k++;
            }
            return found;
        }

        void SetOpeningHover(int k)
        {
            if (k == openingHover) return;
            openingHover = k;
            for (int i = 0; i < openingMarkers.Count; i++)
                if (openingMarkers[i] != null) openingMarkers[i].transform.localScale = i == k ? new Vector3(1.3f, 3f, 1.3f) : new Vector3(0.8f, 2.5f, 0.8f);
        }

        void RemoveOpening(int index)
        {
            var rest = (JArray)Rows().DeepClone();
            if (index < 0 || index >= rest.Count) return;
            rest.RemoveAt(index);
            StartCoroutine(Run(SaveOpenings(rest, false, false), "Saving the inlets and outlets"));
        }

        /// The form for a new opening at x, y, or (index) the one already there. An outlet's level is asked on the survey's
        /// levels, filled in with the ground beside it, which the engine works out (on a wall, the ground, not the wall top).
        IEnumerator OpenOpeningForm(string kind, float x, float y, float width, int index = -1)
        {
            var existing = index >= 0 && index < Rows().Count ? Rows()[index] : null;
            bool outlet = kind == "outlet";
            JToken snap = null;
            float w = existing != null && outlet ? (float)existing["width_m"] : width;
            yield return api.Get(api.P($"/site/openings/snap?x={x.ToString(CultureInfo.InvariantCulture)}&y={y.ToString(CultureInfo.InvariantCulture)}" +
                                       $"&kind={kind}&width_m={w.ToString(CultureInfo.InvariantCulture)}"), r => snap = r);
            api.ClearError();
            float? ground = snap?["ground_m"] != null && snap["ground_m"].Type != JTokenType.Null ? (float)snap["ground_m"] : (float?)null;
            var range = snap?["ground_range_m"] as JArray;

            siteSetup.Close();
            openingForm?.RemoveFromHierarchy();
            openingForm = new VisualElement();
            openingForm.AddToClassList("modal-back");
            var box = new VisualElement();
            box.AddToClassList("modal");
            box.style.height = StyleKeyword.Auto;
            openingForm.Add(box);
            string name = existing != null ? (string)existing["id"] : outlet ? "This outlet" : "This inlet";
            box.Add(Text(name, "h2"));
            box.Add(Text(outlet ? "Water leaves the site here, once it rises to the outlet's level." : "Water from outside the site comes in here during the storm.", "muted"));
            int originAt = existing != null ? System.Array.IndexOf(OriginIds, (string)existing["origin"]) : 0;
            var origin = new DropdownField("Is this an existing site condition, or part of the design?", OriginTitles, Mathf.Max(0, originAt));
            origin.AddToClassList("input");
            origin.AddToClassList("field-stack");
            box.Add(origin);
            string one0 = existing != null ? Fmt(existing[outlet ? "width_m" : "area_m2"]) : outlet && width > 0 ? width.ToString("0.##", CultureInfo.InvariantCulture) : "";
            var one = Field(outlet ? "How wide is it? (m)" : "What area drains to it? (m²)", one0);
            string two0 = !outlet ? (existing != null ? Fmt(existing["runoff_pct"]) : "")
                        : existing?["invert_m"] != null && existing["invert_m"].Type != JTokenType.Null ? F2((float)existing["invert_m"])
                        : existing != null && ground != null ? F2(ground.Value + (float)existing["sill_m"])
                        : ground != null ? F2(ground.Value) : "";
            var two = Field(outlet ? "Outlet level (m): its invert or bottom level, on the survey's levels" : "How much of the rain on that area arrives? (%)", two0);
            box.Add(one);
            box.Add(two);
            Label levelNote = null;
            if (outlet)
            {
                levelNote = Text("", "muted");
                box.Add(levelNote);
                void Explain()
                {
                    var parts = new List<string>();
                    if (ground != null) parts.Add($"Ground here {F2(ground.Value)} m");
                    if (range != null && range.Count == 2) parts.Add($"site ground {F2((float)range[0])}–{F2((float)range[1])} m");
                    var head = string.Join(" · ", parts);
                    var lv = Num(two);
                    string against = lv != null && ground != null ? $"\nAt {F2(lv.Value)} m the outlet is {AgainstGround(lv.Value, ground.Value)}." : "";
                    levelNote.text = (head.Length > 0 ? head + "." : "") + against +
                                     "\nUse the level the survey marks at the outlet (IL or bottom level) if it has one; leave the ground level if the outlet is level with the ground.";
                }
                two.RegisterValueChangedCallback(_ => Explain());
                Explain();
            }
            var note = Text("", "land-status");
            note.style.marginLeft = 0;
            box.Add(note);
            var buttons = Row();
            buttons.Add(Btn("Save", () =>
            {
                Mark(origin, origin.index <= 0);
                Mark(one, Num(one) == null);
                Mark(two, Num(two) == null);
                if (origin.index <= 0) { note.text = "Say whether this is an existing site condition or part of the design."; return; }
                if (Num(one) == null || Num(two) == null) { note.text = outlet ? "Give the width and the outlet's level." : "Fill in both numbers."; return; }
                var row = new JObject { ["kind"] = kind, ["origin"] = OriginIds[origin.index], ["x"] = x, ["y"] = y };
                if (existing?["id"] != null) row["id"] = existing["id"];
                if (existing?["name"] != null) row["name"] = existing["name"];
                row[outlet ? "width_m" : "area_m2"] = Num(one);
                row[outlet ? "invert_m" : "runoff_pct"] = Num(two);
                var rows = (JArray)Rows().DeepClone();
                if (existing != null) rows[index] = row;
                else rows.Add(row);
                StartCoroutine(SaveFromForm(rows, note));
            }));
            if (existing != null)
            {
                buttons.Add(Btn("Copy", () =>
                {
                    openingForm.RemoveFromHierarchy();
                    BeginPlacing(kind, openingsFromAnalyse, (JObject)existing.DeepClone());
                }, "btn--outline"));
                buttons.Add(Btn("Remove", () =>
                {
                    openingForm.RemoveFromHierarchy();
                    RemoveOpening(index);
                    BackToOpenings();
                }, "btn--outline"));
            }
            buttons.Add(Btn("Cancel", () => { openingForm.RemoveFromHierarchy(); BackToOpenings(); }, "btn--outline"));
            box.Add(buttons);
            doc.rootVisualElement.Add(openingForm);
        }

        IEnumerator SaveFromForm(JArray rows, Label note)
        {
            JToken r = null;
            yield return api.Send("PUT", api.P("/site/openings"), new JObject { ["openings"] = rows, ["confirmed"] = false }, x => r = x);
            if (r == null) { note.text = Plain(api.LastError); api.ClearError(); yield break; }
            openingForm.RemoveFromHierarchy();
            Opened(r);
            BackToOpenings();
        }

        IEnumerator SaveOpenings(JArray rows, bool confirmed, bool close)
        {
            JToken r = null;
            yield return api.Send("PUT", api.P("/site/openings"), new JObject { ["openings"] = rows, ["confirmed"] = confirmed }, x => r = x);
            if (r == null) { BuildOpeningMarkers(); yield break; }   // refused: the pins go back where they were
            Opened(r);
            if (close) siteSetup.Close();
            status = openingsFromAnalyse ? "Inlets and outlets saved. Press Analyse site to see where the water goes with them."
                   : !confirmed ? "Inlets and outlets saved." : FloodReady ? "Inlets and outlets saved. Analyse the site to see where the water goes." : "Inlets and outlets saved. Finish the site setup, then Analyse site.";
        }

        void Opened(JToken r)
        {
            openingsData = r;
            if (info != null) info["openings_confirmed"] = (bool?)r["confirmed"] == true;
            FillOpenings();
            BuildOpeningMarkers();
            if (openingsFromAnalyse)
                status = "Inlets and outlets saved. Press Analyse site to see where the water goes with them.";
        }

        /// A post at each inlet (blue) and outlet (red), for the view and the plan.
        void BuildOpeningMarkers()
        {
            foreach (var m in openingMarkers) if (m != null) Destroy(m);
            openingMarkers.Clear();
            openingHover = -1;
            if (frame == null || openingsData == null) return;
            foreach (var o in Rows())
            {
                float x = (float)o["x"], y = (float)o["y"];
                var go = GameObject.CreatePrimitive(PrimitiveType.Cylinder);
                Destroy(go.GetComponent<Collider>());
                go.name = (string)o["id"];
                go.layer = left.Survey.gameObject.layer;
                var mesh = Instantiate(go.GetComponent<MeshFilter>().sharedMesh);
                var colour = (string)o["kind"] == "outlet" ? new Color(0.85f, 0.2f, 0.15f) : new Color(0.15f, 0.4f, 0.9f);
                mesh.colors = Enumerable.Repeat(colour, mesh.vertexCount).ToArray();
                go.GetComponent<MeshFilter>().sharedMesh = mesh;
                go.GetComponent<MeshRenderer>().sharedMaterial = new Material(Shader.Find("SpongePark/VertexLit"));
                go.transform.localScale = new Vector3(0.8f, 2.5f, 0.8f);
                go.transform.position = frame.World(x, y, GroundZ(x, y)) + Vector3.up * 2.5f;
                openingMarkers.Add(go);
            }
        }
    }
}
