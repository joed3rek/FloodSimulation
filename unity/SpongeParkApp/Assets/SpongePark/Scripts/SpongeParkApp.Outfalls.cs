// Site setup > Outfalls: where water leaves the park. The drainage finds every point where the ground drains to the
// edge of the surveyed park; the designer says for each whether water can leave there (a gate, an opening, a drain
// inlet) or a wall / kerb holds it, and how high that edge is. Closed exits hold water against the edge in the
// existing site and every design, and spill to the road above the edge height. No way out is assumed: an exit not answered holds the water.
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
        static readonly List<string> ExitChoices = new List<string> { "Not answered: held, no way out", "Water leaves here", "No way out (wall or kerb)" };
        static readonly string[] ExitStates = { null, "open", "closed" };
        VisualElement outfallCard, outfallRows, outfallAll;
        Label outfallText;
        DropdownField outfallAllState;
        TextField outfallAllHeight;
        class ExitRow { public string Id; public DropdownField State; public TextField Height; }
        readonly List<ExitRow> exitFields = new List<ExitRow>();

        void BuildOutfalls(VisualElement page)
        {
            BuildOpenings(page);
            outfallCard = new VisualElement();
            outfallCard.Add(Text("WHERE WATER LEAVES THE PARK", "eyebrow"));
            outfallText = Text("", "muted");
            outfallCard.Add(outfallText);
            outfallAll = new VisualElement();
            outfallAll.Add(Text("The same for every exit", "field-label"));
            var line = Row("field-row");
            outfallAllState = new DropdownField("Every exit", ExitChoices, 0);
            outfallAllState.AddToClassList("input");
            outfallAllState.AddToClassList("field-stack");
            outfallAllHeight = Field("Edge height (m)");
            // the answer for every exit goes onto each exit's own row, which can then differ
            outfallAllState.RegisterValueChangedCallback(_ => { if (outfallAllState.index > 0) foreach (var r in exitFields) r.State.index = outfallAllState.index; });
            outfallAllHeight.RegisterValueChangedCallback(e => { foreach (var r in exitFields) r.Height.value = e.newValue; });
            outfallAllHeight.tooltip = "Height of the wall or kerb above the ground where the water reaches it";
            line.Add(outfallAllState);
            line.Add(outfallAllHeight);
            outfallAll.Add(line);
            outfallCard.Add(outfallAll);
            outfallCard.Add(Text("Or exit by exit (largest first):", "field-label"));
            outfallRows = new VisualElement();
            outfallCard.Add(outfallRows);
            page.Add(outfallCard);
        }

        IEnumerator LoadOutfalls()
        {
            JToken st = null;
            yield return api.Get(api.P("/site/outfalls"), x => st = x);
            api.ClearError();   // a project analysed before outfalls existed simply has none to answer yet
            FillOutfalls(st);
            yield return LoadOpenings();
        }

        void FillOutfalls(JToken st)
        {
            if (outfallCard == null) return;
            outfallRows.Clear();
            exitFields.Clear();
            int count = (int?)st?["count"] ?? 0;
            exitCount = count;
            foreach (var e in new VisualElement[] { outfallAll, outfallRows }) SpongePark.UI.Kit.Show(e, count > 0);
            if (count == 0)
            {
                outfallText.text = "Nothing to answer yet: the points where the ground drains to the park edge come from Analyse site. Answer them here afterwards.";
                return;
            }
            int closed = (int?)st["closed"] ?? 0;
            bool done = (bool?)st["confirmed"] == true;
            outfallText.text = $"The ground drains to the park edge at {count} point{(count == 1 ? "" : "s")}. For each, say whether water can leave there " +
                               "(a gate, an opening in the wall, a drain inlet) or a wall or kerb holds it. Held water ponds against the edge, soaks in, " +
                               "and spills to the road only above the edge height, in the existing site and every design." +
                               (done ? $"\nAll answered: {closed} with no way out." : "\nWhere you have not answered, the water is held at the edge and does not leave: the model assumes no outlet.");
            var all = st["all"];
            outfallAllState.index = System.Array.IndexOf(ExitStates, (string)all?["state"]) is var ai && ai > 0 ? ai : 0;
            outfallAllHeight.value = Fmt(all?["edge_height_m"]);
            foreach (var ex in st["exits"])
            {
                var row = new ExitRow
                {
                    Id = (string)ex["id"],
                    // a point nobody answered for is held by the engine; it still shows here as not answered
                    State = new DropdownField("", ExitChoices, (bool?)ex["assumed"] == true ? 0
                                              : System.Array.IndexOf(ExitStates, (string)ex["state"]) is var i && i > 0 ? i : 0),
                    Height = Field("Edge height (m)", (bool?)ex["assumed"] == true ? "" : Fmt(ex["edge_height_m"])),
                };
                row.State.AddToClassList("input");
                float x = (float)ex["x"], y = (float)ex["y"], z = ex["ground_m"] != null && ex["ground_m"].Type != JTokenType.Null ? (float)ex["ground_m"] : 0f;
                var box = new VisualElement();
                box.AddToClassList("cover-row");
                var head = Row("field-row");
                head.Add(Text($"{EdgeName(ex)} · {(float)ex["draining_area_m2"]:0} m² drains here · ground {z:0.00} m", "field-label"));
                head.Add(Btn("Show", () => FocusOn(x, y, z, 30), "btn--ghost"));
                box.Add(head);
                var line = Row("field-row");
                line.Add(row.State);
                line.Add(row.Height);
                box.Add(line);
                outfallRows.Add(box);
                exitFields.Add(row);
            }
        }

        JObject OutfallBody()
        {
            var body = new JObject();
            if (outfallAllState.index > 0)
                body["all"] = new JObject { ["state"] = ExitStates[outfallAllState.index], ["edge_height_m"] = Num(outfallAllHeight) };
            body["exits"] = new JArray(exitFields.Where(r => r.State.index > 0)
                .Select(r => new JObject { ["id"] = r.Id, ["state"] = ExitStates[r.State.index], ["edge_height_m"] = Num(r.Height) }));
            return body;
        }

        IEnumerator SaveOutfalls()
        {
            JToken r2 = null;
            yield return api.Send("PUT", api.P("/site/outfalls"), OutfallBody(), x => r2 = x);
            if (r2 != null) FillOutfalls(r2);
        }
    }
}
