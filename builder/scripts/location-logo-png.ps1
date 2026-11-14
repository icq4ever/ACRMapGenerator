<#
.SYNOPSIS
  Fits an own location logo image into the menu's logo plate: 485x218 RGBA PNG, transparent around the logo, for
  `acr-additive menu-locations --logo-dir` (docs/menu-images.md). Any input size and format System.Drawing reads.

  - Background: when the image has no transparency, the near-white area connected to its border (a logo on a white
    canvas) becomes transparent; white inside the logo, enclosed by its outline, stays. -KeepBackground skips this.
  - The logo is cropped to its visible pixels and scaled to fit 485x218 with its aspect kept, centred.
#>
param(
    [Parameter(Mandatory)][string]$In,
    [Parameter(Mandatory)][string]$Out,
    [int]$Width = 485,
    [int]$Height = 218,
    [int]$Tolerance = 40,      # max per-channel distance from white for the background fill
    [switch]$KeepBackground
)
$ErrorActionPreference = 'Stop'
Add-Type -AssemblyName System.Drawing
# pixel work only (int ARGB arrays): no System.Drawing types in the compiled code
if (-not ('LogoPixels' -as [type])) {
    Add-Type -ReferencedAssemblies System.Collections -TypeDefinition @'
using System;
using System.Collections.Generic;

public static class LogoPixels
{
    static bool White(int c, int tol)
    {
        int a = (c >> 24) & 255, r = (c >> 16) & 255, g = (c >> 8) & 255, b = c & 255;
        return a > 0 && 255 - r <= tol && 255 - g <= tol && 255 - b <= tol;
    }

    // Near-white pixels connected to the border become transparent; opaque pixels touching them get an alpha from how far
    // they are from white (and the white mixed out of their colour), so the anti-aliased outline keeps no white fringe.
    public static int ClearBackground(int[] px, int w, int h, int tol)
    {
        var seen = new bool[px.Length];
        var q = new Queue<int>();
        for (int x = 0; x < w; x++) { q.Enqueue(x); q.Enqueue((h - 1) * w + x); }
        for (int y = 0; y < h; y++) { q.Enqueue(y * w); q.Enqueue(y * w + w - 1); }
        int n = 0;
        while (q.Count > 0)
        {
            int i = q.Dequeue();
            if (seen[i]) continue;
            seen[i] = true;
            if (!White(px[i], tol)) continue;
            px[i] = 0; n++;
            int x = i % w, y = i / w;
            if (x > 0) q.Enqueue(i - 1);
            if (x < w - 1) q.Enqueue(i + 1);
            if (y > 0) q.Enqueue(i - w);
            if (y < h - 1) q.Enqueue(i + w);
        }
        var copy = (int[])px.Clone();
        for (int y = 0; y < h; y++)
            for (int x = 0; x < w; x++)
            {
                int i = y * w + x, c = copy[i];
                if (((c >> 24) & 255) == 0) continue;
                bool edge = (x > 0 && copy[i - 1] == 0) || (x < w - 1 && copy[i + 1] == 0) || (y > 0 && copy[i - w] == 0) || (y < h - 1 && copy[i + w] == 0);
                if (!edge) continue;
                int r = (c >> 16) & 255, g = (c >> 8) & 255, b = c & 255;
                int a = Math.Clamp(Math.Max(255 - r, Math.Max(255 - g, 255 - b)) * 2, 32, 255);
                double af = a / 255.0;
                int fr = (int)Math.Clamp((r - 255 * (1 - af)) / af, 0, 255);
                int fg = (int)Math.Clamp((g - 255 * (1 - af)) / af, 0, 255);
                int fb = (int)Math.Clamp((b - 255 * (1 - af)) / af, 0, 255);
                px[i] = (a << 24) | (fr << 16) | (fg << 8) | fb;
            }
        return n;
    }

    // Bounding box of the visible pixels: x0, y0, x1, y1 (x1 < 0: nothing visible).
    public static int[] Bounds(int[] px, int w, int h)
    {
        int x0 = w, y0 = h, x1 = -1, y1 = -1;
        for (int y = 0; y < h; y++)
            for (int x = 0; x < w; x++)
                if (((px[y * w + x] >> 24) & 255) > 8) { if (x < x0) x0 = x; if (y < y0) y0 = y; if (x > x1) x1 = x; if (y > y1) y1 = y; }
        return new[] { x0, y0, x1, y1 };
    }

    public static bool HasAlpha(int[] px)
    {
        foreach (var c in px) if (((c >> 24) & 255) < 250) return true;
        return false;
    }
}
'@
}

$inPath = (Resolve-Path $In).Path
$outPath = [IO.Path]::GetFullPath($Out)
New-Item -ItemType Directory -Force (Split-Path -Parent $outPath) | Out-Null
$fmt = [System.Drawing.Imaging.PixelFormat]::Format32bppArgb

$src0 = [System.Drawing.Bitmap]::new($inPath)
$w = $src0.Width; $h = $src0.Height
$src = $src0.Clone([System.Drawing.Rectangle]::new(0, 0, $w, $h), $fmt)
$src0.Dispose()
$rect = [System.Drawing.Rectangle]::new(0, 0, $w, $h)
$d = $src.LockBits($rect, [System.Drawing.Imaging.ImageLockMode]::ReadWrite, $fmt)
$px = [int[]]::new($w * $h)
for ($y = 0; $y -lt $h; $y++) { [Runtime.InteropServices.Marshal]::Copy([IntPtr]::Add($d.Scan0, $y * $d.Stride), $px, $y * $w, $w) }
$hasAlpha = [LogoPixels]::HasAlpha($px)
$cleared = 0
if (-not $KeepBackground -and -not $hasAlpha) { $cleared = [LogoPixels]::ClearBackground($px, $w, $h, $Tolerance) }
for ($y = 0; $y -lt $h; $y++) { [Runtime.InteropServices.Marshal]::Copy($px, $y * $w, [IntPtr]::Add($d.Scan0, $y * $d.Stride), $w) }
$src.UnlockBits($d)

$bb = [LogoPixels]::Bounds($px, $w, $h)
if ($bb[2] -lt 0) { throw "${In}: nothing visible left" }
$cw = $bb[2] - $bb[0] + 1; $ch = $bb[3] - $bb[1] + 1
$s = [math]::Min($Width / $cw, $Height / $ch)
$dw = [math]::Max(1, [int][math]::Round($cw * $s)); $dh = [math]::Max(1, [int][math]::Round($ch * $s))

$dst = [System.Drawing.Bitmap]::new($Width, $Height, $fmt)
$g = [System.Drawing.Graphics]::FromImage($dst)
$g.Clear([System.Drawing.Color]::Transparent)
$g.CompositingMode = [System.Drawing.Drawing2D.CompositingMode]::SourceCopy
$g.InterpolationMode = [System.Drawing.Drawing2D.InterpolationMode]::HighQualityBicubic
$g.PixelOffsetMode = [System.Drawing.Drawing2D.PixelOffsetMode]::HighQuality
$ia = [System.Drawing.Imaging.ImageAttributes]::new()
$ia.SetWrapMode([System.Drawing.Drawing2D.WrapMode]::TileFlipXY)
$g.DrawImage($src, [System.Drawing.Rectangle]::new([int](($Width - $dw) / 2), [int](($Height - $dh) / 2), $dw, $dh),
    $bb[0], $bb[1], $cw, $ch, [System.Drawing.GraphicsUnit]::Pixel, $ia)
$g.Dispose(); $ia.Dispose(); $src.Dispose()
$dst.Save($outPath, [System.Drawing.Imaging.ImageFormat]::Png)
$dst.Dispose()
Write-Host ("logo {0}: {1}x{2}{3}, logo {4}x{5} -> {6}x{7} in {8}x{9} -> {10}" -f (Split-Path $inPath -Leaf), $w, $h,
    $(if ($hasAlpha) { ' (has alpha)' } else { ", background cleared $cleared px" }), $cw, $ch, $dw, $dh, $Width, $Height, $outPath)
