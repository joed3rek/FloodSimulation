// Site setup as one sequence: it opens when the site model is confirmed, and Next walks the pages, staying on a page
// with what is compulsory not filled and showing that in red. The last page's button is Finish: that saves all the
// pages together, closes the dialog and goes to the Analyse tab.
using System.Collections;
using System.Collections.Generic;
using System.Linq;
using Newtonsoft.Json.Linq;
using UnityEngine.UIElements;

namespace SpongePark
{
    public partial class SpongeParkApp
    {
        static readonly string[] SetupPages = { "rainfall", "ground", "ponds", "wells", "outfalls" };
        readonly HashSet<string> setupSeen = new HashSet<string>();
        readonly Dictionary<string, string> setupLoaded = new Dictionary<string, string>();   // each page as last loaded or saved
        Label setupNote;
        Button setupBack, setupNext;
        bool rainChosen;
        int pondCount, wellCount, exitCount;
        Toggle pondLater, wellLater;

        void BuildSetupFooter()
        {
            siteSetup.CloseOnBack = false;
            setupNote = Text("", "muted");
            setupNote.style.flexGrow = 1;
            setupNote.style.flexShrink = 1;
            setupNote.style.whiteSpace = WhiteSpace.Normal;
            setupBack = Btn("Back", () => siteSetup.ShowPage(SetupPages[System.Math.Max(0, SetupIndex - 1)]), "btn--outline");
            setupNext = Btn("Next", SetupForward);
            siteSetup.Footer.Add(setupNote);
            siteSetup.Footer.Add(setupBack);
            siteSetup.Footer.Add(setupNext);
            SpongePark.UI.Kit.Show(siteSetup.Footer, true);
            siteSetup.Root.schedule.Execute(UpdateSetupFooter).Every(250);
        }

        int SetupIndex => System.Math.Max(0, System.Array.IndexOf(SetupPages, siteSetup.Current));

        /// Open at the start of the sequence with the project's answers loaded.
        IEnumerator OpenSetup()
        {
            yield return LoadGroundAndRain();
            setupSeen.Clear();
            siteSetup.Open(SetupPages[0]);
        }

        /// -spPanel setup-walk: confirm the site and go through the sequence as a person does, logging each step.
        IEnumerator SetupWalk()
        {
            yield return Run(ConfirmSite(true), "Saving");
            for (int step = 0; step < 14 && siteSetup.IsOpen; step++)
            {
                yield return new UnityEngine.WaitForSecondsRealtime(0.6f);
                UnityEngine.Debug.Log($"setup walk {step}: page {siteSetup.Current}, button '{setupNext.text}', note '{setupNote.text}', open {siteSetup.IsOpen}");
                if (siteSetup.Current == "rainfall") rainChosen = true;
                if (siteSetup.Current == "ponds") pondLater.value = true;
                if (siteSetup.Current == "wells") wellLater.value = true;
                if (siteSetup.Current == "outfalls" && (bool?)openingsData?["confirmed"] != true) yield return SaveOpenings(Rows(), true, false);
                if (siteSetup.Current == "outfalls" && exitCount > 0) outfallAllState.index = 1;
                if (setupNext.text == "Finish") { yield return Run(SaveSetup(), "Saving the site setup"); break; }
                SetupForward();
            }
            UnityEngine.Debug.Log($"setup walk end: open {siteSetup.IsOpen}, has rain {info?["has_rainfall"]}, has ground {info?["has_ground"]}, status '{status}', error '{setupError}'");
        }

        /// -spPanel survey-walk: the whole survey sequence as a person goes through it, logging each step: confirm, Site
        /// setup, Analyse site, answer the exits, Analyse site again, then pick storms from the table and while busy.
        IEnumerator SurveyWalk()
        {
            void Log(string step) => UnityEngine.Debug.Log($"survey walk {step}: storm {CurrentRp}, busy {busy}, pending {stormPending}, setup open {siteSetup.IsOpen}, status '{status}'");
            var pause = new UnityEngine.WaitForSecondsRealtime(0.6f);
            yield return SetupWalk();
            Log("set up");
            yield return Run(AnalyseSite(), "Analysing the site");
            Log("analysed");
            yield return OpenSetup();
            siteSetup.ShowPage("outfalls");
            yield return pause;
            UnityEngine.Debug.Log($"survey walk exits: count {exitCount}, button '{setupNext.text}', note '{setupNote.text}'");
            outfallAllState.index = 2;
            outfallAllHeight.value = "0.3";
            yield return pause;
            UnityEngine.Debug.Log($"survey walk answered: button '{setupNext.text}', note '{setupNote.text}'");
            yield return Run(SaveSetup(), "Saving the site setup");
            Log("exits saved");
            UnityEngine.Debug.Log("survey walk before analysing: " + flowText.text);
            yield return Run(AnalyseSite(), "Analysing the site");
            Log("analysed again");
            UnityEngine.Debug.Log("survey walk text: " + flowText.text);
            var row = stormTable[3];   // the header, then 2, 5, 10 years
            using (var e = ClickEvent.GetPooled()) { e.target = row; row.SendEvent(e); }
            yield return pause;
            while (busy || stormPending || stormLoading) yield return null;
            Log("clicked the 10-year row");
            UnityEngine.Debug.Log($"survey walk camera: plan {rigLeft.Plan}, distance {rigLeft.Distance}, readout '{stormReadout.text}'");
            rigLeft.Distance *= 0.6f;   // zoomed in by the person: switching must leave it
            float zoomed = rigLeft.Distance;
            for (int k = 0; k < returnPeriods.Count; k++)
            {
                var began = UnityEngine.Time.realtimeSinceStartup;
                PickStorm(k);
                UnityEngine.Debug.Log($"survey walk switch to {CurrentRp}: shown {flowShownRp} in {(UnityEngine.Time.realtimeSinceStartup - began) * 1000f:0} ms, busy {busy}");
                yield return pause;
            }
            UnityEngine.Debug.Log($"survey walk zoom kept: {UnityEngine.Mathf.Approximately(zoomed, rigLeft.Distance)} ({zoomed} / {rigLeft.Distance})");
            UnityEngine.Debug.Log("survey walk text: " + flowText.text);
            StartCoroutine(Run(BusyFor(2f), "Busy"));
            yield return null;
            timeline.OnRp?.Invoke(1);
            Log("picked 5-year while busy");
            yield return pause;
            while (busy || stormPending || stormLoading) yield return null;
            Log("after busy");
            UnityEngine.Debug.Log("survey walk text: " + flowText.text);
            UnityEngine.Debug.Log("survey walk finished");
        }

        static IEnumerator BusyFor(float seconds) { yield return new UnityEngine.WaitForSecondsRealtime(seconds); }

        void SetupForward()
        {
            if (siteSetup.Current == "rainfall" && rainSaved == null) ChooseRain();   // the page says Next uses it
            setupSeen.Add(siteSetup.Current);
            var missing = SetupMissing();
            var stop = missing.FindIndex(m => m.page == siteSetup.Current);
            if (stop < 0 && SetupIndex < SetupPages.Length - 1) { siteSetup.ShowPage(SetupPages[SetupIndex + 1]); return; }
            if (missing.Count == 0) { StartCoroutine(Run(SaveSetup(), "Saving the site setup")); return; }
            UnityEngine.Debug.Log("site setup: still needed: " + string.Join("; ", missing.Select(m => m.what)));
            var page = missing[stop < 0 ? 0 : stop].page;   // Finish goes back to a page reached by its tab
            setupChecked.Add(page);
            siteSetup.ShowPage(page);
            UpdateSetupFooter();
        }

        void UpdateSetupFooter()
        {
            if (!siteSetup.IsOpen || setupNext == null) return;
            setupSeen.Add(siteSetup.Current);
            var here = SetupMissing().Where(m => m.page == siteSetup.Current && setupChecked.Contains(m.page)).ToList();
            setupNext.text = SetupIndex == SetupPages.Length - 1 ? "Finish" : "Next";
            setupNext.SetEnabled(!busy);
            setupBack.SetEnabled(!busy);
            SpongePark.UI.Kit.Show(setupBack, SetupIndex > 0);
            setupNote.text = setupError ?? (here.Count == 0 ? "" : "Still needed: " + string.Join("; ", here.Select(m => m.what)) + ".");
            setupNote.EnableInClassList("note--missing", setupError != null || here.Count > 0);
            MarkSetup();
        }

        static void Mark(VisualElement field, bool missing) => field?.EnableInClassList("input--missing", missing);

        /// Red on what is compulsory and not filled, once Next or Finish has been pressed on that page.
        void MarkSetup()
        {
            bool shares = setupChecked.Contains("ground") && covers.Count > 1 &&
                          System.Math.Abs(covers.Sum(c => float.TryParse(c.Share.value, out var s) ? s : 0f) - 100f) > 0.5f;
            foreach (var c in covers) Mark(c.Share, shares);

            bool ponds = setupChecked.Contains("ponds") && !pondLater.value;
            foreach (var r in pondFields) { Mark(r.Depth, ponds && Num(r.Depth) == null); Mark(r.Water, ponds && Num(r.Water) == null); }

            bool wells = setupChecked.Contains("wells") && wellCount > 0 && !wellLater.value;
            Mark(wellDepth, wells && Num(wellDepth) == null && wellFields.Any(r => Num(r.Depth) == null));
            Mark(wellDia, wells && Num(wellDia) == null && wellFields.Any(r => !r.Drawn && Num(r.Diameter) == null));
            Mark(wellRate, wells && Num(wellRate) == null);

            bool exits = setupChecked.Contains("outfalls");
            Mark(openingsDone, exits && openingsData != null && (bool?)openingsData["confirmed"] != true);
            var height = Num(outfallAllHeight);
            bool allClosed = outfallAllState != null && ExitStates[outfallAllState.index] == "closed";
            Mark(outfallAllHeight, exits && exitCount > 0 && allClosed && height == null);
            foreach (var r in exitFields)
            {
                Mark(r.State, exits && r.State.index == 0 && outfallAllState.index == 0);
                Mark(r.Height, exits && r.State.index > 0 && ExitStates[r.State.index] == "closed" && (Num(r.Height) ?? height) == null);
            }
        }

        string setupError, setupFor;
        readonly HashSet<string> setupChecked = new HashSet<string>();   // pages where Next or Finish has found something missing

        /// What is still to be answered, page by page.
        List<(string page, string what)> SetupMissing()
        {
            var out_ = new List<(string, string)>();
            if (rainSaved == null && !rainChosen) out_.Add(("rainfall", "press Use this rainfall on the Rainfall page"));
            if (groundSaved == null && !setupSeen.Contains("ground")) out_.Add(("ground", "check the ground answers"));
            else if (covers.Count > 1 && System.Math.Abs(covers.Sum(c => float.TryParse(c.Share.value, out var s) ? s : 0f) - 100f) > 0.5f)
                out_.Add(("ground", "the ground cover shares must add up to 100%"));
            if (pondCount > 0 && !pondLater.value && pondFields.Any(r => Num(r.Depth) == null || Num(r.Water) == null))
                out_.Add(("ponds", "the depth and usual water level of every pond, or tick Not known yet"));
            if (wellCount > 0 && !wellLater.value &&
                (Num(wellRate) == null || wellFields.Any(r => (Num(r.Depth) ?? Num(wellDepth)) == null || (!r.Drawn && (Num(r.Diameter) ?? Num(wellDia)) == null))))
                out_.Add(("wells", "the depth, diameter (where not drawn) and strata infiltration of the wells, or tick Not known yet"));
            if (openingsData != null && (bool?)openingsData["confirmed"] != true)
                out_.Add(("outfalls", "place the inlets and outlets, or say there are none"));
            if (exitCount > 0 && !ExitsAnswered()) out_.Add(("outfalls", "answer every exit, with an edge height where water is held"));
            return out_;
        }

        bool ExitsAnswered()
        {
            var height = Num(outfallAllHeight);
            bool Ok(int state, float? own) => ExitStates[state] != "closed" || (own ?? height) != null;
            if (outfallAllState.index > 0 && !Ok(outfallAllState.index, height)) return false;
            return exitFields.All(r => r.State.index > 0 ? Ok(r.State.index, Num(r.Height)) : outfallAllState.index > 0);
        }

        void RememberSetup()
        {
            if (groundQuestions != null) setupLoaded["ground"] = GroundBody().ToString();
            setupLoaded["ponds"] = PondBody().ToString();
            setupLoaded["wells"] = WellBody().ToString();
            setupLoaded["outfalls"] = OutfallBody().ToString();
            if (setupFor != projectPath)   // "not known yet" holds for this project until it is answered
            {
                setupFor = projectPath;
                if (pondLater != null) pondLater.value = false;
                if (wellLater != null) wellLater.value = false;
            }
            rainChosen = false;
            setupError = null;
            setupChecked.Clear();
        }

        bool SetupChanged(string page, JToken body) => !setupLoaded.TryGetValue(page, out var was) || was != body.ToString();

        /// Every page that changed, in order; on a refusal the page stays open at the page it came from.
        IEnumerator SaveSetup()
        {
            setupError = null;
            api.ClearError();
            bool groundModel = false;
            var steps = new List<(string page, System.Func<IEnumerator> save)>();
            if (rainSaved == null) steps.Add(("rainfall", UsePresetRain));
            if (groundSaved == null || SetupChanged("ground", GroundBody())) steps.Add(("ground", SaveGround));
            if (pondCount > 0 && !pondLater.value && SetupChanged("ponds", PondBody())) { steps.Add(("ponds", SavePonds)); groundModel = true; }
            if (wellCount > 0 && !wellLater.value && SetupChanged("wells", WellBody())) { steps.Add(("wells", SaveWells)); groundModel = true; }
            if (exitCount > 0 && SetupChanged("outfalls", OutfallBody())) steps.Add(("outfalls", SaveOutfalls));
            foreach (var (page, save) in steps)
            {
                yield return save();
                if (string.IsNullOrEmpty(api.LastError)) continue;
                setupError = "Not saved: " + Plain(api.LastError);
                api.ClearError();
                siteSetup.ShowPage(page);
                yield break;
            }
            yield return Refresh();
            yield return LoadGroundAndRain();
            siteSetup.Close();
            if (groundModel) yield return LoadViews();
            ui.ActiveTab = SpongePark.UI.Tab.Analyse;
            status = "Site setup saved. Next: Analyse site.";
        }
    }
}
