// Import settings for the workspace's icons (Resources/UI/Icons): white Lucide glyphs tinted by the theme, so no
// mipmaps (they blur small icons), clamped edges, alpha kept as transparency.
using UnityEditor;
using UnityEngine;

namespace SpongePark.EditorTools
{
    public class UiAssetImport : AssetPostprocessor
    {
        void OnPreprocessTexture()
        {
            if (!assetPath.Replace("\\", "/").Contains("/Resources/UI/Icons/")) return;
            var t = (TextureImporter)assetImporter;
            t.textureType = TextureImporterType.Default;
            t.mipmapEnabled = false;
            t.wrapMode = TextureWrapMode.Clamp;
            t.alphaIsTransparency = true;
            t.filterMode = FilterMode.Bilinear;
            t.textureCompression = TextureImporterCompression.Uncompressed;
            t.npotScale = TextureImporterNPOTScale.None;
        }
    }
}
