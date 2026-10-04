# Chrome Tabs to Helium (Windows)

Capture currently open tabs in Chrome, then open their URLs in Helium using one generated Windows launcher. No browser restart, remote debugging, Python, server, or registry changes required. Chrome's tabs remain open.

## Use

For a guided walkthrough, open [guide.html](guide.html). Build a user ZIP with
`powershell -NoProfile -File build.ps1`; it places `manifest.json` directly at the
ZIP root so the extracted folder can be loaded without choosing a subfolder.

1. In Chrome, open `chrome://extensions`, enable **Developer mode**, choose **Load unpacked**, and select the extracted folder containing `manifest.json`. The download places the manifest directly in the main folder; in the source project, use the `extension` subfolder. Pin **Chrome Tabs to Helium** from Chrome's extensions menu.
2. Click the extension icon. It shows how many tabs and windows can transfer. Click **Save Helium launcher** and save the generated `.cmd` file.
3. Double-click that saved file. It finds a standard Helium installation and opens the captured tabs. For a portable/custom installation, select Helium's executable if asked. In the standard per-user installation the executable is `%LOCALAPPDATA%\imput\Helium\Application\chrome.exe`, despite being named `chrome.exe`.

Install this extension in **Chrome only**. Helium does not need an extension. A local launcher is required because a normal Chrome extension cannot directly start another browser executable.

## Behavior

- Captures tabs across all normal windows in the **current Chrome profile**, including minimized windows. Install/run separately for other profiles. Incognito windows, app/PWA windows, and popups are excluded.
- Opens each Chrome window as a new Helium window, retaining tab order and duplicate URLs. Existing Helium windows remain open. Very large windows may split to respect Windows' command-line length limit.
- Transfers HTTP/HTTPS links, local `file:` pages, and blank/new tabs. Chrome settings/internal pages, extension pages, `data:`, `blob:`, custom protocols and oversized/unavailable URLs are skipped and listed. Chrome new-tab pages become blank tabs. Navigating tabs use their pending destination URL.
- Captures again when you click **Save**, so the launcher contains the tabs open at that moment. Running the same launcher again opens another copy of those tabs.
- Pin status, tab groups, history, scroll position, unsaved forms, media playback state, cookies and authentication are not transferred. URLs open in Helium's default/last-used profile. Sign in again where necessary.

## Integration proposal

The [installation flow](docs/install-flow.md) describes the implemented standalone
guide and a possible future entry from Helium onboarding. The onboarding entry is
a proposal only; this helper does not change the current onboarding UI or browser
build. The [script model](docs/script-model.md) describes the snapshot format,
batch/PowerShell launcher, process arguments, and trust boundaries.

## Privacy and execution

The extension requests only `tabs` and `downloads` permissions. It reads tab URLs and titles to prepare the export; it does not read page content, passwords or cookies. It has no remote requests, background collection or host permissions. The only fetch reads a bundled local template.

The generated `.cmd` is executable code made by this tool. Only run launchers you generated yourself. URLs are stored as Base64-encoded JSON **data**, not interpolated into executable commands. Base64 is not encryption or a signature: keep the file private, since URLs may include private query strings. Delete it after use. A launcher modified by someone else can contain arbitrary code; the helper does not authenticate launcher files.

The launcher runs bundled PowerShell code with `-NoProfile -ExecutionPolicy Bypass` for that process only; it does not change your machine's execution policy. It launches only a detected or explicitly selected Helium executable. Chrome or Windows may ask you to keep/approve a downloaded `.cmd` file. Managed devices may block scripts or unpacked extensions.

Advanced custom installation: set `LOCAL_TAB_TRANSFER_HELIUM` to the absolute path of your trusted Helium executable before running the launcher. No environment variable is required for a standard installation.

## Developer checks

End users do not need Node or npm. For developer checks, use Node 20+ and run `npm install`, then `npm test`. Windows launcher integration uses a synthetic argument recorder, not your browser profiles. `npm run test:browser` tests live capture in a Playwright Chromium installation and opens the generated launcher in an installed Helium using a fresh temporary profile. It creates minimized test windows, then closes them. Set `SESSION_TRANSFER_CHROMIUM` and `TAB_TRANSFER_TEST_HELIUM` to the respective browser executables for nonstandard test installations.

References: [Chrome Tabs API](https://developer.chrome.com/docs/extensions/reference/api/tabs), [Chrome Windows API](https://developer.chrome.com/docs/extensions/reference/api/windows).
