; Inno Setup script. Build AFTER running build_exe.bat (needs dist\WebPOptimizer\).
; Command line:  iscc /DAppVersion=1.0.0 installer.iss
#ifndef AppVersion
  #define AppVersion "1.0.0"
#endif

[Setup]
AppId={{8E3B5C1A-4D2F-4B7A-9A61-5F0C2D7E1B93}
AppName=WebP Optimizer
AppVersion={#AppVersion}
AppPublisher=WebP Optimizer
DefaultDirName={autopf}\WebP Optimizer
DefaultGroupName=WebP Optimizer
UninstallDisplayIcon={app}\WebPOptimizer.exe
SetupIconFile=assets\icons\app.ico
OutputDir=installer_output
OutputBaseFilename=WebPOptimizer-Setup-{#AppVersion}
Compression=lzma2
SolidCompression=yes
ArchitecturesAllowed=x64compatible
ArchitecturesInstallIn64BitMode=x64compatible
; Installs just for the current user (no admin prompt) unless the user chooses otherwise.
PrivilegesRequired=lowest
PrivilegesRequiredOverridesAllowed=dialog
WizardStyle=modern

[Tasks]
Name: "desktopicon"; Description: "Create a &desktop shortcut"; GroupDescription: "Additional shortcuts:"

[Files]
Source: "dist\WebPOptimizer\*"; DestDir: "{app}"; Flags: recursesubdirs ignoreversion

[Icons]
Name: "{group}\WebP Optimizer"; Filename: "{app}\WebPOptimizer.exe"
Name: "{autodesktop}\WebP Optimizer"; Filename: "{app}\WebPOptimizer.exe"; Tasks: desktopicon

[Run]
Filename: "{app}\WebPOptimizer.exe"; Description: "Launch WebP Optimizer"; Flags: nowait postinstall skipifsilent
