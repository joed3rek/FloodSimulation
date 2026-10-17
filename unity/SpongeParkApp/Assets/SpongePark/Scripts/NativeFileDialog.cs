// The operating system's "Open file" window (Windows Explorer dialog), for choosing a survey drawing
// or a .sponge project. In the Editor Unity's own panel is used; on Windows players the Win32 common
// dialog (comdlg32); elsewhere Supported is false and the app falls back to its in-app browser.
using System;
using System.Runtime.InteropServices;

namespace SpongePark
{
    public static class NativeFileDialog
    {
#if UNITY_EDITOR
        public static bool Supported => true;
#else
        public static bool Supported => UnityEngine.Application.platform == UnityEngine.RuntimePlatform.WindowsPlayer;
#endif

        /// Shows the dialog and returns the chosen path, or null when cancelled.
        /// extensions: e.g. "dxf,dwg" or "sponge"; label: shown in the file-type list.
        public static string Open(string title, string label, string extensions, string initialDir = "")
        {
#if UNITY_EDITOR
            var p = UnityEditor.EditorUtility.OpenFilePanelWithFilters(title, initialDir, new[] { label, extensions });
            return string.IsNullOrEmpty(p) ? null : p.Replace('/', '\\');
#elif UNITY_STANDALONE_WIN
            var patterns = string.Join(";", Array.ConvertAll(extensions.Split(','), e => "*." + e.Trim()));
            var ofn = new OpenFileName
            {
                structSize = Marshal.SizeOf(typeof(OpenFileName)),
                dlgOwner = GetActiveWindow(),
                filter = $"{label} ({patterns})\0{patterns}\0All files (*.*)\0*.*\0\0",
                filterIndex = 1,
                file = new string('\0', 2048),
                maxFile = 2048,
                fileTitle = new string('\0', 256),
                maxFileTitle = 256,
                initialDir = string.IsNullOrEmpty(initialDir) ? null : initialDir,
                title = title,
                flags = OFN_EXPLORER | OFN_FILEMUSTEXIST | OFN_PATHMUSTEXIST | OFN_NOCHANGEDIR,
            };
            if (!GetOpenFileName(ofn)) return null;
            var path = ofn.file;
            int nul = path.IndexOf('\0');
            return nul >= 0 ? path.Substring(0, nul) : path;
#else
            return null;
#endif
        }

#if UNITY_STANDALONE_WIN && !UNITY_EDITOR
        const int OFN_EXPLORER = 0x00080000, OFN_FILEMUSTEXIST = 0x00001000, OFN_PATHMUSTEXIST = 0x00000800, OFN_NOCHANGEDIR = 0x00000008;

        [StructLayout(LayoutKind.Sequential, CharSet = CharSet.Unicode)]
        class OpenFileName
        {
            public int structSize;
            public IntPtr dlgOwner;
            public IntPtr instance;
            public string filter;
            public string customFilter;
            public int maxCustFilter;
            public int filterIndex;
            public string file;
            public int maxFile;
            public string fileTitle;
            public int maxFileTitle;
            public string initialDir;
            public string title;
            public int flags;
            public short fileOffset;
            public short fileExtension;
            public string defExt;
            public IntPtr custData;
            public IntPtr hook;
            public string templateName;
            public IntPtr reservedPtr;
            public int reservedInt;
            public int flagsEx;
        }

        [DllImport("comdlg32.dll", SetLastError = true, CharSet = CharSet.Unicode)]
        static extern bool GetOpenFileName([In, Out] OpenFileName ofn);

        [DllImport("user32.dll")]
        static extern IntPtr GetActiveWindow();
#endif
    }
}
