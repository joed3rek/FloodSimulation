// The workspace's one state store: active ribbon tab, panel layout, view mode, UI scale and the guided-project
// preference. Panels read it and send commands through it; they never reach into each other. Layout and
// preferences are saved in the user's settings (PlayerPrefs), not in the project.
using System;
using UnityEngine;

namespace SpongePark.UI
{
    public enum Tab { Site, Analyse, Design, Simulate, Results, Export }

    /// An action the user can take: shown as a ribbon button, an app bar button or (Pass 3) in the command palette.
    public class Command
    {
        public string Id, Label, Icon, Tooltip, Shortcut;
        public Action Run;
        public Func<bool> Enabled = () => true, On = () => false, Visible = () => true;
        public bool Primary;   // a stage's main action (accent icon)
    }

    [Serializable]
    public class Layout
    {
        public float contentsWidth = 240, propsWidth = 270, uiScale = 1f;
        public bool contentsCollapsed, propsCollapsed, ribbonCollapsed, timelineCollapsed, guideNewProjects = true;
    }

    public class UiState
    {
        const string Key = "spongepark.workspace.v1";
        public Layout Layout { get; private set; } = new Layout();
        Tab tab = Tab.Site;
        string propsTab = "properties";
        bool viewportMax, checklistOpen = true;

        public event Action LayoutChanged, TabChanged, PropsTabChanged;
        public event Action<string> PanelRequested;

        public Tab ActiveTab
        {
            get => tab;
            set { if (tab == value) return; tab = value; TabChanged?.Invoke(); }
        }

        /// "properties", "checks" or "results".
        public string PropsTab
        {
            get => propsTab;
            set { if (propsTab == value) return; propsTab = value; PropsTabChanged?.Invoke(); }
        }

        /// The viewport fills the window (panels, ribbon and timeline hidden): F11, or double-click a panel header.
        public bool ViewportMax
        {
            get => viewportMax;
            set { if (viewportMax == value) return; viewportMax = value; LayoutChanged?.Invoke(); }
        }

        public bool ChecklistOpen
        {
            get => checklistOpen;
            set { if (checklistOpen == value) return; checklistOpen = value; LayoutChanged?.Invoke(); }
        }

        public void ChangeLayout(Action<Layout> change)
        {
            change(Layout);
            Layout.contentsWidth = Mathf.Clamp(Layout.contentsWidth, 180, 420);
            Layout.propsWidth = Mathf.Clamp(Layout.propsWidth, 220, 460);
            Save();
            LayoutChanged?.Invoke();
        }

        /// Open a panel, tab or dialog by name (ribbon tabs "tab:design"; "properties", "checks", "results";
        /// "contents"; "checklist"; dialogs "site-setup", "site-setup:ground", "targets", "settings").
        public void Request(string name) => PanelRequested?.Invoke(name);

        public void Load()
        {
            try
            {
                var json = PlayerPrefs.GetString(Key, "");
                if (!string.IsNullOrEmpty(json)) Layout = JsonUtility.FromJson<Layout>(json) ?? new Layout();
            }
            catch (Exception) { Layout = new Layout(); }
        }

        public void Save()
        {
            PlayerPrefs.SetString(Key, JsonUtility.ToJson(Layout));
            PlayerPrefs.Save();
        }
    }
}
