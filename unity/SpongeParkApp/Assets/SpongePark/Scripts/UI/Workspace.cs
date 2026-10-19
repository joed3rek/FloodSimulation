// The workspace frame: app bar, ribbon, then Contents | viewport | (checklist + Properties), the timeline and the
// status bar; dialogs and toasts float over it. The splitters between the panels drag to resize them (sizes are
// kept in the user's settings). With the viewport maximised (F11, the app bar button or a double-click on a panel
// header) only the app bar, the viewport and the status bar remain.
using UnityEngine;
using UnityEngine.UIElements;

namespace SpongePark.UI
{
    public class Workspace
    {
        public readonly VisualElement Root, Viewport, Overlay, DialogHost;
        readonly UiState state;
        readonly VisualElement ribbon, contents, right, timeline, leftSplit, rightSplit;

        public Workspace(UiState state, VisualElement appBar, Ribbon ribbon, ContentsPanel contents, PropertiesPanel props,
                         Timeline timeline, StatusBar status, Toasts toasts)
        {
            this.state = state;
            Root = Kit.Box("ws");
            Root.Add(appBar);
            Root.Add(ribbon.Root);
            this.ribbon = ribbon.Root;
            var middle = Kit.Box("ws-middle");
            Root.Add(middle);
            this.contents = contents.Root;
            middle.Add(contents.Root);
            leftSplit = Splitter(true);
            middle.Add(leftSplit);
            var centre = Kit.Box("centre");
            middle.Add(centre);
            Viewport = Kit.Box("viewport");
            Viewport.pickingMode = PickingMode.Position;   // the scene shows through; hovering it is "in the view"
            centre.Add(Viewport);
            Overlay = new VisualElement { pickingMode = PickingMode.Ignore };
            Overlay.style.position = Position.Absolute;
            Overlay.style.left = 0; Overlay.style.top = 0; Overlay.style.right = 0; Overlay.style.bottom = 0;
            Viewport.Add(Overlay);
            rightSplit = Splitter(false);
            middle.Add(rightSplit);
            right = props.Root;
            middle.Add(props.Root);
            this.timeline = timeline.Root;
            Root.Add(timeline.Root);
            Root.Add(status.Root);
            Root.Add(toasts.Root);
            DialogHost = new VisualElement { pickingMode = PickingMode.Ignore };
            DialogHost.style.position = Position.Absolute;
            DialogHost.style.left = 0; DialogHost.style.top = 0; DialogHost.style.right = 0; DialogHost.style.bottom = 0;
            Root.Add(DialogHost);
            state.LayoutChanged += Sync;
            Sync();
        }

        void Sync()
        {
            bool max = state.ViewportMax;
            Kit.Show(ribbon, !max);
            Kit.Show(contents, !max);
            Kit.Show(right, !max);
            Kit.Show(timeline, !max);
            Kit.Show(leftSplit, !max && !state.Layout.contentsCollapsed);
            Kit.Show(rightSplit, !max && !state.Layout.propsCollapsed);
        }

        /// A drag handle between a side panel and the viewport.
        VisualElement Splitter(bool leftPanel)
        {
            var s = Kit.Box("splitter");
            float startX = 0, startW = 0;
            bool drag = false;
            s.RegisterCallback<PointerDownEvent>(e =>
            {
                drag = true;
                startX = e.position.x;
                startW = leftPanel ? state.Layout.contentsWidth : state.Layout.propsWidth;
                s.CapturePointer(e.pointerId);
            });
            s.RegisterCallback<PointerMoveEvent>(e =>
            {
                if (!drag) return;
                float dx = e.position.x - startX;
                if (leftPanel) state.Layout.contentsWidth = Mathf.Clamp(startW + dx, 180, 420);
                else state.Layout.propsWidth = Mathf.Clamp(startW - dx, 220, 460);
                contents.style.width = state.Layout.contentsCollapsed ? 36 : state.Layout.contentsWidth;
                right.style.width = state.Layout.propsCollapsed ? 36 : state.Layout.propsWidth;
            });
            s.RegisterCallback<PointerUpEvent>(e =>
            {
                if (!drag) return;
                drag = false;
                s.ReleasePointer(e.pointerId);
                state.ChangeLayout(_ => { });
            });
            return s;
        }
    }
}
