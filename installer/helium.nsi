; Copyright 2025 The Helium Authors
; You can use, redistribute, and/or modify this source code under
; the terms of the GPL-3.0 license that can be found in the LICENSE file.
;
; NSIS installer script for Helium browser.
; Wraps setup.exe + helium.7z with a GUI.
;
; Required defines (passed via makensis -D):
;   VERSION    - Helium version string (e.g., 0.10.4.1)
;   ARCH       - Target architecture (x64 or arm64)
;   SETUP_EXE  - Path to setup.exe
;   HELIUM_7Z  - Path to helium.7z (uncompressed; NSIS handles compression)
;   ICON_FILE  - Path to helium .ico file
;   OUTPUT_FILE - Output installer .exe path
;   LICENSE_FILE - Path to LICENSE file

!include "MUI2.nsh"
!include "x64.nsh"
!include "WinVer.nsh"
!include "nsDialogs.nsh"
!include "LogicLib.nsh"
!include "FileFunc.nsh"

; --- Product Information ---
!define PRODUCT_NAME "Helium"
!define PRODUCT_PUBLISHER "imput"
!define PRODUCT_COMPANY_PATH "imput"
!define PRODUCT_GUID "{FB68A146-637A-48C2-A0C4-1565DE45FEBD}"

; --- Installer Configuration ---
Name "${PRODUCT_NAME} ${VERSION}"
OutFile "${OUTPUT_FILE}"
Unicode true
ManifestDPIAware true
SetCompressor /SOLID lzma
RequestExecutionLevel user
ShowInstDetails show

; --- Variables ---
Var InstallType
Var SetupExitCode
Var SetupFlags
Var InstallFailed
Var RadioUser
Var RadioSystem

; --- MUI2 Configuration ---
!define MUI_ICON "${ICON_FILE}"
!define MUI_ABORTWARNING
!define MUI_ABORTWARNING_TEXT "Are you sure you want to cancel ${PRODUCT_NAME} installation?"

; Welcome page
!define MUI_WELCOMEPAGE_TITLE "Welcome to ${PRODUCT_NAME} Setup"
!define MUI_WELCOMEPAGE_TEXT "Setup will install ${PRODUCT_NAME} ${VERSION} on your computer.$\r$\n$\r$\nClick Next to continue."
!insertmacro MUI_PAGE_WELCOME

; License page
!insertmacro MUI_PAGE_LICENSE "${LICENSE_FILE}"

; Install type selection (custom page)
Page custom InstallTypePage InstallTypePageLeave

; Installation progress
!insertmacro MUI_PAGE_INSTFILES

; Finish page
!define MUI_FINISHPAGE_TITLE "${PRODUCT_NAME} has been installed"
!define MUI_FINISHPAGE_TEXT "${PRODUCT_NAME} has been successfully installed on your computer.$\r$\n$\r$\nClick Finish to close Setup."
!define MUI_FINISHPAGE_RUN
!define MUI_FINISHPAGE_RUN_TEXT "Launch ${PRODUCT_NAME}"
!define MUI_FINISHPAGE_RUN_FUNCTION LaunchHelium
!insertmacro MUI_PAGE_FINISH

; --- Language ---
!insertmacro MUI_LANGUAGE "English"

; --- Version Information ---
VIProductVersion "${VERSION}"
VIAddVersionKey "ProductName" "${PRODUCT_NAME}"
VIAddVersionKey "CompanyName" "${PRODUCT_PUBLISHER}"
VIAddVersionKey "FileDescription" "${PRODUCT_NAME} Installer"
VIAddVersionKey "FileVersion" "${VERSION}"
VIAddVersionKey "LegalCopyright" "Copyright The Helium Authors"

; =============================================================================
; Custom Install Type Page
; =============================================================================

Function InstallTypePage
  !insertmacro MUI_HEADER_TEXT "Installation Type" "Choose how you want to install ${PRODUCT_NAME}."

  nsDialogs::Create 1018
  Pop $0
  ${If} $0 == error
    Abort
  ${EndIf}

  ${NSD_CreateLabel} 0 0 100% 24u "Select the installation type:"
  Pop $0

  ${NSD_CreateRadioButton} 10u 30u 280u 12u "Install for current user only (recommended)"
  Pop $RadioUser
  ${NSD_SetState} $RadioUser ${BST_CHECKED}

  ${NSD_CreateLabel} 24u 44u 280u 16u "Installs to your user profile. No administrator privileges required."
  Pop $0

  ${NSD_CreateRadioButton} 10u 66u 280u 12u "Install for all users"
  Pop $RadioSystem

  ${NSD_CreateLabel} 24u 80u 280u 16u "Installs system-wide. Requires administrator privileges."
  Pop $0

  nsDialogs::Show
FunctionEnd

Function InstallTypePageLeave
  ${NSD_GetState} $RadioUser $0
  ${If} $0 == ${BST_CHECKED}
    StrCpy $InstallType "user"
  ${Else}
    StrCpy $InstallType "system"
  ${EndIf}
FunctionEnd

; =============================================================================
; Initialization
; =============================================================================

Function .onInit
  ; Default to user install; parse command-line flags
  StrCpy $InstallType "user"
  StrCpy $SetupFlags ""
  ${GetParameters} $0

  ${GetOptions} $0 "/SYSTEM" $1
  ${IfNot} ${Errors}
    StrCpy $InstallType "system"
  ${EndIf}
  ClearErrors

  ${GetOptions} $0 "/VERBOSE-LOGGING" $1
  ${IfNot} ${Errors}
    StrCpy $SetupFlags '$SetupFlags --verbose-logging'
  ${EndIf}
  ClearErrors

  ${GetOptions} $0 "/LOG-FILE=" $1
  ${IfNot} ${Errors}
    StrCpy $SetupFlags '$SetupFlags --log-file="$1"'
  ${EndIf}
  ClearErrors

  ; Check Windows version (setup.exe requires Windows 10+)
  ${IfNot} ${AtLeastWin10}
    MessageBox MB_OK|MB_ICONSTOP "${PRODUCT_NAME} requires Windows 10 or later."
    Abort
  ${EndIf}

  ; Check architecture matches installer variant
  ${If} "${ARCH}" == "x64"
    ${IfNot} ${IsNativeAMD64}
      MessageBox MB_OK|MB_ICONSTOP "This installer is for x64 systems. Please download the ARM64 installer."
      Abort
    ${EndIf}
  ${ElseIf} "${ARCH}" == "arm64"
    ${IfNot} ${IsNativeARM64}
      MessageBox MB_OK|MB_ICONSTOP "This installer is for ARM64 systems. Please download the x64 installer."
      Abort
    ${EndIf}
  ${EndIf}
FunctionEnd

; =============================================================================
; Main Install Section
; =============================================================================

Section "Install" SecInstall
  StrCpy $InstallFailed ""

  ; Extract setup files to temp directory
  SetOutPath "$TEMP\helium_install"
  DetailPrint "Extracting installation files..."
  File "${SETUP_EXE}"
  File /oname=helium.7z "${HELIUM_7Z}"

  ; Build setup.exe command line
  StrCpy $0 '"$TEMP\helium_install\setup.exe" --uncompressed-archive="$TEMP\helium_install\helium.7z" --do-not-launch-chrome'

  ${If} $InstallType == "system"
    StrCpy $0 '$0 --system-level'
  ${EndIf}

  ; Append optional flags (verbose logging, log file)
  StrCpy $0 '$0$SetupFlags'

  ; Run setup.exe
  DetailPrint "Running setup.exe..."
  SetDetailsPrint none
  nsExec::ExecToLog $0
  Pop $SetupExitCode
  SetDetailsPrint both

  ; Handle exit code
  ${Switch} $SetupExitCode
    ${Case} "0"
      ; FIRST_INSTALL_SUCCESS
      DetailPrint "Installation completed successfully."
      ${Break}

    ${Case} "1"
      ; INSTALL_REPAIRED
      DetailPrint "Installation repaired successfully."
      ${Break}

    ${Case} "2"
      ; NEW_VERSION_UPDATED
      DetailPrint "${PRODUCT_NAME} has been updated successfully."
      ${Break}

    ${Case} "3"
      ; EXISTING_VERSION_LAUNCHED
      DetailPrint "Existing ${PRODUCT_NAME} installation is up to date."
      ${Break}

    ${Case} "30"
      ; IN_USE_UPDATED
      DetailPrint "${PRODUCT_NAME} has been updated. Please restart the browser for changes to take effect."
      ${Break}

    ${Case} "4"
      ; HIGHER_VERSION_EXISTS
      DetailPrint "A newer version of ${PRODUCT_NAME} is already installed."
      ${Break}

    ${Case} "7"
      ; INSTALL_FAILED
      DetailPrint "Installation failed."
      MessageBox MB_OK|MB_ICONEXCLAMATION "Installation failed. Please try again."
      StrCpy $InstallFailed "1"
      ${Break}

    ${Case} "9"
      ; OS_NOT_SUPPORTED
      DetailPrint "This operating system is not supported."
      MessageBox MB_OK|MB_ICONEXCLAMATION "${PRODUCT_NAME} requires Windows 10 or later."
      StrCpy $InstallFailed "1"
      ${Break}

    ${Case} "12"
      ; UNCOMPRESSION_FAILED
      DetailPrint "Failed to decompress the installer archive."
      MessageBox MB_OK|MB_ICONEXCLAMATION "Failed to decompress the installer archive. The download may be corrupted."
      StrCpy $InstallFailed "1"
      ${Break}

    ${Case} "14"
      ; INSUFFICIENT_RIGHTS
      DetailPrint "Insufficient privileges."
      MessageBox MB_OK|MB_ICONEXCLAMATION "Insufficient privileges to install ${PRODUCT_NAME}.$\r$\n$\r$\nPlease run the installer as administrator, or choose 'Install for current user only'."
      StrCpy $InstallFailed "1"
      ${Break}

    ${Case} "60"
      ; SETUP_SINGLETON_ACQUISITION_FAILED
      DetailPrint "Another installation is in progress."
      MessageBox MB_OK|MB_ICONEXCLAMATION "Another ${PRODUCT_NAME} installation is already in progress. Please wait for it to complete."
      StrCpy $InstallFailed "1"
      ${Break}

    ${Case} "error"
      DetailPrint "Failed to launch the installer."
      MessageBox MB_OK|MB_ICONEXCLAMATION "Failed to launch the installer. The download may be corrupted."
      StrCpy $InstallFailed "1"
      ${Break}

    ${Case} "timeout"
      DetailPrint "Installation timed out."
      MessageBox MB_OK|MB_ICONEXCLAMATION "Installation timed out."
      StrCpy $InstallFailed "1"
      ${Break}

    ${Default}
      DetailPrint "Installation failed with error code: $SetupExitCode"
      MessageBox MB_OK|MB_ICONEXCLAMATION "Installation failed with error code: $SetupExitCode"
      StrCpy $InstallFailed "1"
      ${Break}

  ${EndSwitch}

  ; Clean up extracted files
  DetailPrint "Cleaning up..."
  Delete "$TEMP\helium_install\setup.exe"
  Delete "$TEMP\helium_install\helium.7z"
  RMDir "$TEMP\helium_install"

  ; Abort if installation failed (prevents finish page from showing success)
  ${If} $InstallFailed == "1"
    Abort
  ${EndIf}
SectionEnd

; =============================================================================
; Finish Page - Launch Function
; =============================================================================

Function LaunchHelium
  ${If} $InstallType == "system"
    Exec '"$PROGRAMFILES64\${PRODUCT_COMPANY_PATH}\${PRODUCT_NAME}\Application\chrome.exe"'
  ${Else}
    Exec '"$LOCALAPPDATA\${PRODUCT_COMPANY_PATH}\${PRODUCT_NAME}\Application\chrome.exe"'
  ${EndIf}
FunctionEnd
