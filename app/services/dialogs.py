from __future__ import annotations

import os
import re
import shutil
import subprocess
from pathlib import Path


_OWNER_SCRIPT = r'''
Add-Type -AssemblyName System.Windows.Forms
Add-Type -AssemblyName System.Drawing
Add-Type @'
using System;
using System.Runtime.InteropServices;
public static class OrbitNativeWindow {
    [DllImport("user32.dll")] public static extern bool SetForegroundWindow(IntPtr hWnd);
    [DllImport("user32.dll")] public static extern bool BringWindowToTop(IntPtr hWnd);
    [DllImport("user32.dll")] public static extern bool SetWindowPos(IntPtr hWnd, IntPtr hWndInsertAfter, int X, int Y, int cx, int cy, uint flags);
    public static readonly IntPtr HWND_TOPMOST = new IntPtr(-1);
    public const uint SWP_NOMOVE = 0x0002;
    public const uint SWP_NOSIZE = 0x0001;
    public const uint SWP_SHOWWINDOW = 0x0040;
}
'@
[System.Windows.Forms.Application]::EnableVisualStyles()
$owner = New-Object System.Windows.Forms.Form
$owner.Text = 'ORBIT'
$owner.ShowInTaskbar = $false
$owner.TopMost = $true
$owner.FormBorderStyle = [System.Windows.Forms.FormBorderStyle]::None
$owner.StartPosition = [System.Windows.Forms.FormStartPosition]::CenterScreen
$owner.Size = New-Object System.Drawing.Size(8,8)
$owner.Opacity = 0.05
$owner.Show()
$owner.Activate()
$owner.BringToFront()
[OrbitNativeWindow]::SetWindowPos($owner.Handle, [OrbitNativeWindow]::HWND_TOPMOST, 0, 0, 0, 0, [OrbitNativeWindow]::SWP_NOMOVE -bor [OrbitNativeWindow]::SWP_NOSIZE -bor [OrbitNativeWindow]::SWP_SHOWWINDOW) | Out-Null
[OrbitNativeWindow]::BringWindowToTop($owner.Handle) | Out-Null
[OrbitNativeWindow]::SetForegroundWindow($owner.Handle) | Out-Null
Start-Sleep -Milliseconds 80
[System.Windows.Forms.Application]::DoEvents()
'''


def _find_powershell() -> str | None:
    """Find Windows PowerShell even when an embeddable Python has a minimal PATH."""
    candidates: list[str | None] = [shutil.which("powershell.exe"), shutil.which("pwsh.exe")]
    system_root = os.environ.get("SystemRoot") or os.environ.get("WINDIR")
    if system_root:
        candidates.extend([
            str(Path(system_root) / "System32" / "WindowsPowerShell" / "v1.0" / "powershell.exe"),
            str(Path(system_root) / "Sysnative" / "WindowsPowerShell" / "v1.0" / "powershell.exe"),
        ])
    for candidate in candidates:
        if candidate and Path(candidate).is_file():
            return candidate
    return None


def _safe_suggested_name(value: str | None) -> str:
    text = re.sub(r'[<>:"/\\|?*\x00-\x1f]+', "_", str(value or "ORBIT-Pack")).strip(" .")
    if text.casefold().endswith(".orbitpack"):
        text = text[:-10]
    return (text[:100] or "ORBIT-Pack") + ".orbitpack"


def _powershell_dialog(kind: str, suggested_name: str | None = None) -> str | None:
    if kind not in {"file", "folder", "cover", "game", "orbitpack", "save_orbitpack"}:
        raise ValueError("Tipo de selector no válido.")

    if kind == "folder":
        dialog_script = r'''
$dialog = New-Object System.Windows.Forms.FolderBrowserDialog
$dialog.Description = 'Selecciona una carpeta'
$dialog.ShowNewFolderButton = $true
$result = $dialog.ShowDialog($owner)
if ($result -eq [System.Windows.Forms.DialogResult]::OK) {
    [Console]::OutputEncoding = [System.Text.Encoding]::UTF8
    Write-Output $dialog.SelectedPath
}
'''
    elif kind == "save_orbitpack":
        filename = _safe_suggested_name(suggested_name).replace("'", "_")
        dialog_script = rf'''
$dialog = New-Object System.Windows.Forms.SaveFileDialog
$dialog.Title = 'Guardar ORBIT Pack'
$dialog.Filter = 'ORBIT Pack|*.orbitpack|Todos los archivos|*.*'
$dialog.DefaultExt = 'orbitpack'
$dialog.AddExtension = $true
$dialog.OverwritePrompt = $true
$dialog.RestoreDirectory = $true
$dialog.FileName = '{filename}'
$result = $dialog.ShowDialog($owner)
if ($result -eq [System.Windows.Forms.DialogResult]::OK) {{
    [Console]::OutputEncoding = [System.Text.Encoding]::UTF8
    Write-Output $dialog.FileName
}}
'''
    else:
        if kind == "cover":
            filter_text = "Imágenes|*.png;*.jpg;*.jpeg;*.jpe;*.jfif;*.webp;*.gif;*.avif;*.bmp;*.ico;*.tif;*.tiff|Todos los archivos|*.*"
            title = "Selecciona una imagen"
        elif kind == "game":
            filter_text = "Juegos y ROMs|*.exe;*.bat;*.cmd;*.lnk;*.nes;*.sfc;*.smc;*.n64;*.z64;*.v64;*.gb;*.gbc;*.gba;*.nds;*.3ds;*.cci;*.cxi;*.nsp;*.xci;*.nro;*.nca;*.iso;*.gcm;*.rvz;*.wbfs;*.cue;*.chd;*.pbp;*.cso;*.cdi;*.gdi;*.md;*.gen;*.bin;*.zip;*.7z|Todos los archivos|*.*"
            title = "Selecciona un juego o ROM"
        elif kind == "orbitpack":
            filter_text = "ORBIT Pack|*.orbitpack|Todos los archivos|*.*"
            title = "Selecciona un ORBIT Pack"
        else:
            filter_text = "Todos los archivos|*.*"
            title = "Selecciona un archivo"
        dialog_script = rf'''
$dialog = New-Object System.Windows.Forms.OpenFileDialog
$dialog.Title = '{title}'
$dialog.Filter = '{filter_text}'
$dialog.CheckFileExists = $true
$dialog.Multiselect = $false
$dialog.RestoreDirectory = $true
$dialog.AutoUpgradeEnabled = $true
$result = $dialog.ShowDialog($owner)
if ($result -eq [System.Windows.Forms.DialogResult]::OK) {{
    [Console]::OutputEncoding = [System.Text.Encoding]::UTF8
    Write-Output $dialog.FileName
}}
'''

    script = _OWNER_SCRIPT + dialog_script + "\n$owner.Close()\n$owner.Dispose()\n"
    powershell = _find_powershell()
    if not powershell:
        raise ValueError("No se encontró PowerShell para abrir el selector de archivos de Windows.")

    result = subprocess.run(
        [powershell, "-NoProfile", "-STA", "-Command", script],
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        timeout=120,
        check=False,
        creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
    )
    if result.returncode != 0:
        # Deliberately keep the user-facing error generic. PowerShell stderr may
        # contain local paths/usernames which are not appropriate on stream.
        raise ValueError("No se pudo abrir el selector de Windows. Prueba de nuevo o usa launcher_debug.bat si necesitas diagnosticarlo.")
    selected = result.stdout.strip().lstrip("\ufeff")
    return selected or None


def open_dialog(kind: str, suggested_name: str | None = None) -> str | None:
    """Open a native file/folder/save picker without requiring tkinter in embedded Python."""
    if os.name == "nt":
        return _powershell_dialog(kind, suggested_name=suggested_name)

    # Development fallback for non-Windows environments. The Windows portable
    # runtime never relies on tkinter because Python's embeddable package omits Tcl/Tk.
    try:
        import tkinter as tk
        from tkinter import filedialog

        root = tk.Tk()
        root.withdraw()
        try:
            root.attributes("-topmost", True)
        except Exception:
            pass
        try:
            if kind == "folder":
                result = filedialog.askdirectory(title="Selecciona una carpeta", parent=root)
            elif kind == "cover":
                result = filedialog.askopenfilename(
                    title="Selecciona una imagen",
                    filetypes=[("Imágenes", "*.png *.jpg *.jpeg *.jpe *.jfif *.webp *.gif *.avif *.bmp *.ico *.tif *.tiff"), ("Todos", "*.*")],
                    parent=root,
                )
            elif kind == "game":
                result = filedialog.askopenfilename(title="Selecciona un juego o ROM", parent=root)
            elif kind == "orbitpack":
                result = filedialog.askopenfilename(title="Selecciona un ORBIT Pack", filetypes=[("ORBIT Pack", "*.orbitpack"), ("Todos", "*.*")], parent=root)
            elif kind == "save_orbitpack":
                result = filedialog.asksaveasfilename(
                    title="Guardar ORBIT Pack",
                    defaultextension=".orbitpack",
                    initialfile=_safe_suggested_name(suggested_name),
                    filetypes=[("ORBIT Pack", "*.orbitpack"), ("Todos", "*.*")],
                    parent=root,
                )
            elif kind == "file":
                result = filedialog.askopenfilename(title="Selecciona un archivo", parent=root)
            else:
                raise ValueError("Tipo de selector no válido.")
            return result or None
        finally:
            root.destroy()
    except ValueError:
        raise
    except Exception:
        raise ValueError("No se pudo abrir el selector de archivos.")
