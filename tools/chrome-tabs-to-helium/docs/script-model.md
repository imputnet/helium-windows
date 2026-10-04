# Script model

The Chrome extension reads the currently open tab URLs and generates one local Windows launcher. The transfer has no backend, native-messaging registration, remote-debugging requirement or browser restart. This model describes the implemented helper.

## Snapshot

```json
{
  "format": "chrome-tabs-to-helium",
  "version": 1,
  "createdAt": "2026-10-03T12:00:00.000Z",
  "windows": [
    {
      "urls": ["https://example.com/", "https://example.com/help"]
    },
    {
      "urls": ["https://example.net/"]
    }
  ]
}
```

Window objects preserve the tab sequence. Duplicates are intentional. Chrome's window IDs, profile location and cookie store IDs are not needed in the launcher. An in-progress navigation uses `pendingUrl` when present. No tab titles enter the exported snapshot; they are used only for explaining skipped tabs in the popup.

The extension queries normal windows of the current profile, excludes incognito, sorts tabs by their tab-strip index, and accepts HTTP, HTTPS, local file URLs and `about:blank`. Chrome new-tab pages become blank tabs. Other browser-internal, extension, data, blob and custom-protocol pages are omitted. URLs over 23,000 characters or containing literal control/whitespace characters are omitted. The popup reports skipped tabs.

## Launcher layers

1. `core.mjs` validates the snapshot and encodes its UTF-8 JSON as Base64.
2. A bundled `launcher.ps1.txt` template receives the Base64 value in one fixed placeholder. No URL is inserted into PowerShell source as executable text.
3. A short CMD header reads its own file and runs the PowerShell section after a fixed marker. This avoids putting the complete snapshot on CMD's command line.
4. PowerShell validates the decoded model again, detects or asks for Helium's executable, quotes each URL as a separate Windows process argument, and starts Helium with `--new-window` for each source window.
5. Windows command lines are batched below 28,000 characters including the executable-path allowance. A source window too large for one command is split into additional destination windows.

The CMD header runs PowerShell with `-NoProfile`, `-STA` for the executable picker, and `-ExecutionPolicy Bypass` for this process only. It does not change the machine's policy. Helium is the only intended target executable; the custom path override or picker is a user trust decision.

## Boundaries

- Chrome permissions: `tabs` and `downloads`. There are no host, cookie, scripting, native-messaging or storage permissions.
- Network: the extension fetches only its bundled local template. Exporting sends no URLs to a service. Opening the URLs in Helium causes the normal website requests the user requested.
- URLs stay process arguments and never go through CMD `start`, `Invoke-Expression`, or a dynamically generated shell command. The fixed, locally bundled PowerShell program itself is run as a script block.
- Base64 is transport encoding, not encryption or authenticity. A saved launcher can contain private URLs. A third party can replace the executable code, so users must run only their own trusted exports.
- Chrome tabs and existing Helium windows remain open. Authentication, tab groups, pin state, scroll positions and unsaved page state are outside this model.
- The launcher reports that launches were sent. It cannot certify successful navigation or a website's acceptance of the user's session.

## Validation

Tests cover actual CMD execution using an argument-recorder executable, shell-sensitive URL characters, Unicode, trailing backslashes, duplicates and command-length batching. Browser integration uses synthetic local URLs in fresh Chrome and installed-Helium profiles, verifies source windows, destination windows, order and duplicate URLs, and confirms the Chrome tabs remain open. The complete Chromium/Helium build is not exercised because this optional helper does not alter it.
