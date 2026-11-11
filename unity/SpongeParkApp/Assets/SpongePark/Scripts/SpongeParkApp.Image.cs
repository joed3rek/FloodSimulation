// Picture export from the viewport (Analyse and Export tabs): choose a size (HD to 8K), turn on the frame to see
// exactly what the picture will hold, zoom and pan the view to frame it, then save. The picture is a PNG with a
// scale bar, written to the export folder's "images".
using System;
using System.Collections;
using System.Collections.Generic;
using System.IO;
using System.Linq;
using UnityEngine;
using UnityEngine.UIElements;
using SpongePark.UI;

namespace SpongePark
{
    public partial class SpongeParkApp
    {
        int imageSizeIdx = 4;   // 4K
        bool captureFrameOn, exportingImage;
        VisualElement captureFrame, captureBox;
        VisualElement[] captureDims;
        Label captureLabel;
        readonly List<DropdownField> imageSizeFields = new List<DropdownField>();

        ImageExport.Size ImageSize => ImageExport.Sizes[Mathf.Clamp(imageSizeIdx, 0, ImageExport.Sizes.Length - 1)];

        void BuildImageCommands()
        {
            try { imageSizeIdx = PlayerPrefs.GetInt("sp.imageSize", imageSizeIdx); } catch (Exception) { }
            C("image-frame", "Frame", "extents", "Show the part of the view the picture will hold; zoom and pan to frame it",
              () => captureFrameOn = !captureFrameOn, () => frame != null, () => captureFrameOn);
            C("image-save", "Save image", "export", "Save the framed view as a PNG at the chosen size (with a scale bar) in the export folder's \"images\"",
              () => StartCoroutine(SaveImage()), () => frame != null && !exportingImage, primary: true);
        }

        /// The size picker and the two commands, as a ribbon group (one on the Analyse tab, one on Export).
        void AddImageGroup(RibbonTab tab)
        {
            var f = new DropdownField(ImageExport.Sizes.Select(s => s.Label).ToList(), imageSizeIdx);
            f.AddToClassList("input");
            f.AddToClassList("ribbon-field");
            f.tooltip = "The picture's size in pixels";
            f.RegisterValueChangedCallback(e =>
            {
                if (f.index < 0) return;
                imageSizeIdx = f.index;
                try { PlayerPrefs.SetInt("sp.imageSize", imageSizeIdx); } catch (Exception) { }
                foreach (var o in imageSizeFields) if (o != f) o.SetValueWithoutNotify(ImageSize.Label);
            });
            imageSizeFields.Add(f);
            var g = tab.Group("Image");
            g.Add(f);
            g.Large(commands["image-frame"]).Large(commands["image-save"]);
        }

        /// The frame over the viewport: the outside dimmed, the picture's part outlined and labelled.
        void BuildCaptureFrame(VisualElement overlay)
        {
            captureFrame = new VisualElement { pickingMode = PickingMode.Ignore };
            captureFrame.style.position = Position.Absolute;
            captureFrame.style.left = 0; captureFrame.style.top = 0; captureFrame.style.right = 0; captureFrame.style.bottom = 0;
            captureDims = new VisualElement[4];
            for (int i = 0; i < 4; i++)
            {
                var d = new VisualElement { pickingMode = PickingMode.Ignore };
                d.style.position = Position.Absolute;
                d.style.backgroundColor = new Color(0, 0, 0, 0.55f);
                captureDims[i] = d;
                captureFrame.Add(d);
            }
            captureBox = new VisualElement { pickingMode = PickingMode.Ignore };
            captureBox.style.position = Position.Absolute;
            var line = new Color(1f, 0.78f, 0.2f, 0.95f);
            captureBox.style.borderTopWidth = captureBox.style.borderBottomWidth = captureBox.style.borderLeftWidth = captureBox.style.borderRightWidth = 2;
            captureBox.style.borderTopColor = captureBox.style.borderBottomColor = captureBox.style.borderLeftColor = captureBox.style.borderRightColor = line;
            captureLabel = new Label { pickingMode = PickingMode.Ignore };
            captureLabel.style.position = Position.Absolute;
            captureLabel.style.right = 6;
            captureLabel.style.top = 6;
            captureLabel.style.paddingLeft = captureLabel.style.paddingRight = 6;
            captureLabel.style.paddingTop = captureLabel.style.paddingBottom = 2;
            captureLabel.style.backgroundColor = line;
            captureLabel.style.color = new Color(0.1f, 0.1f, 0.1f);
            captureBox.Add(captureLabel);
            captureFrame.Add(captureBox);
            Kit.Show(captureFrame, false);
            overlay.Insert(0, captureFrame);   // behind the viewport's own buttons and labels
        }

        void SyncCaptureFrame()
        {
            if (captureFrame == null) return;
            bool show = captureFrameOn && frame != null;
            Kit.Show(captureFrame, show);
            if (!show) return;
            var l = ws.Viewport.layout;
            if (float.IsNaN(l.width) || l.width <= 0) return;
            var b = ImageExport.Frame(new Rect(0, 0, l.width, l.height), ImageSize.Aspect);   // panel units, centred
            float top = (l.height - b.height) / 2, left = (l.width - b.width) / 2;
            Place(captureBox, left, top, b.width, b.height);
            Place(captureDims[0], 0, 0, l.width, top);                          // above
            Place(captureDims[1], 0, top + b.height, l.width, l.height - top - b.height);   // below
            Place(captureDims[2], 0, top, left, b.height);                      // left
            Place(captureDims[3], left + b.width, top, l.width - left - b.width, b.height);  // right
            captureLabel.text = $"{ImageSize.Label} · zoom and pan to frame";
        }

        static void Place(VisualElement e, float x, float y, float w, float h)
        {
            e.style.left = x; e.style.top = y; e.style.width = Mathf.Max(0, w); e.style.height = Mathf.Max(0, h);
        }

        IEnumerator SaveImage()
        {
            exportingImage = true;
            var size = ImageSize;
            string path = null;
            try
            {
                yield return new WaitForEndOfFrame();   // the view as it stands this frame (animations included)
                var vp = new Rect(viewRect.x * Screen.width, viewRect.y * Screen.height, viewRect.width * Screen.width, viewRect.height * Screen.height);
                var box = ImageExport.Frame(vp, size.Aspect);
                var cam = camLeft;
                float mpp = cam.orthographic ? 2 * cam.orthographicSize / Mathf.Max(1, cam.pixelHeight)
                    : 2 * rigLeft.Distance * Mathf.Tan(cam.fieldOfView * 0.5f * Mathf.Deg2Rad) / Mathf.Max(1, cam.pixelHeight);
                var cams = sideBySide ? new[] { camLeft, camRight } : new[] { camLeft };
                byte[] rgb = null;
                try { rgb = ImageExport.Render(cams, box, size, cam.backgroundColor, mpp, cam.orthographic ? "" : "(at the centre)"); }
                catch (Exception e)
                {
                    Debug.LogException(e);
                    toasts.Show($"The picture could not be made at {size.Name}: {e.Message}", "error", 8);
                }
                if (rgb == null) yield break;
                string name = HasProject ? (string)info["name"] ?? Path.GetFileNameWithoutExtension(projectPath) : "site";
                foreach (var ch in Path.GetInvalidFileNameChars()) name = name.Replace(ch, '_');
                string file = $"{name}-{(rigLeft.Plan ? "plan" : "3d")}{(sideBySide ? "-split" : "")}-{size.Name.Replace(" ", "")}-{DateTime.Now:yyyyMMdd-HHmmss}.png";
                path = Path.Combine(exportDir, "images", file);
                status = $"Saving the {size.Name} picture…";
                var task = ImageExport.Save(rgb, size.W, size.H, path);
                while (!task.IsCompleted) yield return null;
                if (task.IsFaulted)
                {
                    var err = task.Exception?.GetBaseException();
                    Debug.LogException(err);
                    toasts.Show($"The picture could not be saved: {err?.Message}", "error", 8);
                    yield break;
                }
                status = "Image saved: " + path;
                toasts.Show($"{size.Name} picture saved: {path}", "ok", 8);
            }
            finally { exportingImage = false; }
        }
    }
}
