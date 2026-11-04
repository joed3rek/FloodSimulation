// Site setup > Inlets and outlets: the designer places each place water gets in or out of the site, and says what it is:
// an existing site condition or part of the design. Everywhere else the edge holds the water. Nothing is assumed: a
// model-based project asks before it is analysed, and the list has to be confirmed even when it is empty.
using System.Collections;
using System.Collections.Generic;
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
        readonly List<GameObject> openingMarkers = new List<GameObject>();

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

        static string Describe(JToken o)
        {
            var origin = (string)o["origin"] == "design" ? "part of the design" : "existing site condition";
            return (string)o["kind"] == "outlet"
                ? $"Outlet · {(float)o["width_m"]:0.##} m wide · sill {(float)o["sill_m"]:0.##} m · {origin}"
                : $"Inlet · {(float)o["area_m2"]:N0} m² draining, {(float)o["runoff_pct"]:0}% arrives · {origin}";
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
                row.Add(Btn("Remove", () =>
                {
                    var rest = Rows();
                    rest.RemoveAt(index);
                    StartCoroutine(Run(SaveOpenings(rest, false, false), "Saving the inlets and outlets"));
                }, "btn--ghost"));
                openingsRows.Add(row);
            }
            foreach (var g in openingsData["gaps"] ?? new JArray())
            {
                float x = (float)g["x"], y = (float)g["y"];
                var row = Row("field-row");
                row.Add(Text($"Gap in the wall, {(float)g["width_m"]:0.#} m wide: closed unless you say otherwise", "field-label"));
                row.Add(Btn("Show", () => FocusOn(x, y, GroundZ(x, y), 30), "btn--ghost"));
                row.Add(Btn("Outlet", () => OpenOpeningForm("outlet", x, y, (float)g["width_m"]), "btn--ghost"));
                row.Add(Btn("Inlet", () => OpenOpeningForm("inlet", x, y, 0), "btn--ghost"));
                openingsRows.Add(row);
            }
            openingsDone.text = Rows().Count == 0 ? "None: no water gets in or out" : "That is all of them";
        }

        void BeginPlacing(string kind)
        {
            placing = kind;
            siteSetup.Close();
            status = kind == "outlet" ? "Click the edge of the site where water leaves. Esc cancels." : "Click where water comes into the site. Esc cancels.";
        }

        /// While placing: the next click on the site is the place. True when it has the pointer, so nothing else takes it.
        bool OpeningsInput()
        {
            if (placing == null) return false;
            if (Input.GetKeyDown(KeyCode.Escape)) { placing = null; status = ""; siteSetup.Open("outfalls"); return true; }
            if (CameraRig.BlockInput != null && CameraRig.BlockInput()) return true;
            if (Input.GetMouseButtonDown(0) && PickGround(out var xy, out _))
            {
                var kind = placing;
                placing = null;
                OpenOpeningForm(kind, xy.x, xy.y, 0);
            }
            return true;
        }

        void OpenOpeningForm(string kind, float x, float y, float width)
        {
            siteSetup.Close();
            openingForm?.RemoveFromHierarchy();
            openingForm = new VisualElement();
            openingForm.AddToClassList("modal-back");
            var box = new VisualElement();
            box.AddToClassList("modal");
            box.style.height = StyleKeyword.Auto;
            openingForm.Add(box);
            bool outlet = kind == "outlet";
            box.Add(Text(outlet ? "This outlet" : "This inlet", "h2"));
            box.Add(Text(outlet ? "Water leaves the site here, once it rises to the sill." : "Water from outside the site comes in here during the storm.", "muted"));
            var origin = new DropdownField("Is this an existing site condition, or part of the design?", OriginTitles, 0);
            origin.AddToClassList("input");
            origin.AddToClassList("field-stack");
            box.Add(origin);
            var one = Field(outlet ? "How wide is it? (m)" : "What area drains to it? (m²)", outlet && width > 0 ? width.ToString("0.##", System.Globalization.CultureInfo.InvariantCulture) : "");
            var two = Field(outlet ? "How high is its sill above the ground? (m, 0 if level)" : "How much of the rain on that area arrives? (%)");
            box.Add(one);
            box.Add(two);
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
                if (Num(one) == null || Num(two) == null) { note.text = "Fill in both numbers."; return; }
                var row = new JObject { ["kind"] = kind, ["origin"] = OriginIds[origin.index], ["x"] = x, ["y"] = y };
                row[outlet ? "width_m" : "area_m2"] = Num(one);
                row[outlet ? "sill_m" : "runoff_pct"] = Num(two);
                var rows = (JArray)Rows().DeepClone();
                rows.Add(row);
                StartCoroutine(SaveFromForm(rows, note));
            }));
            buttons.Add(Btn("Cancel", () => { openingForm.RemoveFromHierarchy(); siteSetup.Open("outfalls"); }, "btn--outline"));
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
            siteSetup.Open("outfalls");
        }

        IEnumerator SaveOpenings(JArray rows, bool confirmed, bool close)
        {
            JToken r = null;
            yield return api.Send("PUT", api.P("/site/openings"), new JObject { ["openings"] = rows, ["confirmed"] = confirmed }, x => r = x);
            if (r == null) yield break;
            Opened(r);
            if (close) siteSetup.Close();
            status = !confirmed ? "Inlets and outlets saved." : FloodReady ? "Inlets and outlets saved. Analyse the site to see where the water goes." : "Inlets and outlets saved. Finish the site setup, then Analyse site.";
        }

        void Opened(JToken r)
        {
            openingsData = r;
            if (info != null) info["openings_confirmed"] = (bool?)r["confirmed"] == true;
            FillOpenings();
            BuildOpeningMarkers();
        }

        /// A post at each inlet (blue) and outlet (red), for the view and the plan.
        void BuildOpeningMarkers()
        {
            foreach (var m in openingMarkers) if (m != null) Destroy(m);
            openingMarkers.Clear();
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
