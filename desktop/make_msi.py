"""Wraps desktop/dist/Scrubs (from PyInstaller) in an MSI: desktop/dist/Scrubs-<version>.msi.

Uses WiX Toolset v3 (heat, candle, light). It needs no install: build.ps1 expects the
binaries in desktop/build/tools/wix, or set WIX to another folder.
    https://github.com/wixtoolset/wix3/releases (wix314-binaries.zip)

The MSI shows the standard install wizard (welcome, notice, install folder, ready, finish with
"Open Scrubs"), installs for all users into Program Files\\Scrubs by default (Windows asks for
admin), adds Start menu and desktop shortcuts, and upgrades over any older Scrubs version.
"""

import os
import subprocess
import sys
from pathlib import Path

DESKTOP = Path(__file__).resolve().parent
APP_DIR = DESKTOP / "dist" / "Scrubs"
WORK = DESKTOP / "build" / "msi"
WIX = Path(os.getenv("WIX", DESKTOP / "build" / "tools" / "wix"))
VERSION = os.getenv("SCRUBS_VERSION", "0.1.0")
# Never change this: Windows uses it to recognise newer versions of the same app.
UPGRADE_CODE = "6B0F3B52-8E5D-4C1A-9B7E-2F4A1C9D7E31"
ART = DESKTOP / "installer"            # made by installer/make_art.py
LICENSE_RTF = ART / "license.rtf"

PRODUCT_WXS = f"""<?xml version="1.0" encoding="UTF-8"?>
<Wix xmlns="http://schemas.microsoft.com/wix/2006/wi">
  <Product Id="*" Name="Scrubs" Language="1033" Version="{VERSION}"
           Manufacturer="Scrubs (StormHacks 2026)" UpgradeCode="{UPGRADE_CODE}">
    <Package InstallerVersion="500" Compressed="yes" InstallScope="perMachine" Platform="x64"
             Description="Scrubs: pseudonymize patient documents before using a chatbot" />
    <MajorUpgrade DowngradeErrorMessage="A newer version of Scrubs is already installed." />
    <MediaTemplate EmbedCab="yes" CompressionLevel="medium" MaximumUncompressedMediaSize="1024" />

    <!-- Standard wizard: welcome, notice, choose folder, ready, progress, finish. -->
    <Property Id="WIXUI_INSTALLDIR" Value="INSTALLFOLDER" />
    <WixVariable Id="WixUILicenseRtf" Value="{LICENSE_RTF}" />
    <WixVariable Id="WixUIBannerBmp" Value="{ART / 'banner.bmp'}" />
    <WixVariable Id="WixUIDialogBmp" Value="{ART / 'dialog.bmp'}" />
    <Icon Id="ScrubsIcon" SourceFile="{ART / 'scrubs.ico'}" />
    <Property Id="ARPPRODUCTICON" Value="ScrubsIcon" />
    <Property Id="WIXUI_EXITDIALOGOPTIONALCHECKBOXTEXT" Value="Open Scrubs" />
    <Property Id="WIXUI_EXITDIALOGOPTIONALCHECKBOX" Value="1" />
    <Property Id="WixShellExecTarget" Value="[INSTALLFOLDER]Scrubs.exe" />
    <CustomAction Id="LaunchScrubs" BinaryKey="WixCA" DllEntry="WixShellExec" Impersonate="yes" />
    <UI>
      <UIRef Id="WixUI_InstallDir" />
      <Publish Dialog="ExitDialog" Control="Finish" Event="DoAction" Value="LaunchScrubs">
        WIXUI_EXITDIALOGOPTIONALCHECKBOX = 1 and NOT Installed
      </Publish>
    </UI>

    <Directory Id="TARGETDIR" Name="SourceDir">
      <Directory Id="ProgramFiles64Folder">
        <Directory Id="INSTALLFOLDER" Name="Scrubs" />
      </Directory>
      <Directory Id="ProgramMenuFolder" />
      <Directory Id="DesktopFolder" />
    </Directory>

    <DirectoryRef Id="ProgramMenuFolder">
      <Component Id="StartMenuShortcut" Guid="3E1A6C0D-7B2F-4E59-A8D3-5C6B9F2E1A47" Win64="yes">
        <Shortcut Id="StartMenuScrubs" Name="Scrubs" Target="[INSTALLFOLDER]Scrubs.exe" WorkingDirectory="INSTALLFOLDER" Icon="ScrubsIcon" />
        <RegistryValue Root="HKCU" Key="Software\\Scrubs" Name="startmenu" Type="integer" Value="1" KeyPath="yes" />
      </Component>
    </DirectoryRef>
    <DirectoryRef Id="DesktopFolder">
      <Component Id="DesktopShortcut" Guid="9C4D2B71-1F8A-4E3C-B6D5-7A2E8F0C3B19" Win64="yes">
        <Shortcut Id="DesktopScrubs" Name="Scrubs" Target="[INSTALLFOLDER]Scrubs.exe" WorkingDirectory="INSTALLFOLDER" Icon="ScrubsIcon" />
        <RegistryValue Root="HKCU" Key="Software\\Scrubs" Name="desktop" Type="integer" Value="1" KeyPath="yes" />
      </Component>
    </DirectoryRef>

    <Feature Id="Main" Title="Scrubs" Level="1">
      <ComponentGroupRef Id="AppFiles" />
      <ComponentRef Id="StartMenuShortcut" />
      <ComponentRef Id="DesktopShortcut" />
    </Feature>
  </Product>
</Wix>
"""


def run(tool: str, *args: str) -> None:
    cmd = [str(WIX / tool), *args, "-nologo"]   # heat needs its harvest type ("dir") first
    print(tool, args[0] if args else "", "...", flush=True)
    subprocess.run(cmd, check=True)


def main() -> int:
    if not (APP_DIR / "Scrubs.exe").exists():
        print(f"Build the app first: {APP_DIR / 'Scrubs.exe'} is missing.")
        return 1
    if not (WIX / "light.exe").exists():
        print(f"WiX v3 not found in {WIX}. Download wix314-binaries.zip and unzip it there, or set WIX.")
        return 1
    WORK.mkdir(parents=True, exist_ok=True)
    (WORK / "product.wxs").write_text(PRODUCT_WXS, encoding="utf-8")

    # Every file under dist/Scrubs becomes a component, with stable generated GUIDs.
    run("heat.exe", "dir", str(APP_DIR), "-cg", "AppFiles", "-dr", "INSTALLFOLDER", "-ag", "-srd", "-sfrag",
        "-sreg", "-var", "var.AppDir", "-out", str(WORK / "files.wxs"))
    run("candle.exe", "-arch", "x64", "-ext", "WixUtilExtension", f"-dAppDir={APP_DIR}", "-out", str(WORK) + os.sep,
        str(WORK / "product.wxs"), str(WORK / "files.wxs"))
    out = DESKTOP / "dist" / f"Scrubs-{VERSION}.msi"
    # -sval skips ICE validation, which takes many minutes on thousands of files.
    run("light.exe", "-sval", "-spdb", "-ext", "WixUIExtension", "-ext", "WixUtilExtension", "-out", str(out), str(WORK / "product.wixobj"), str(WORK / "files.wixobj"))
    print(f"Built {out} ({out.stat().st_size / 1024 / 1024:.0f} MB)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
