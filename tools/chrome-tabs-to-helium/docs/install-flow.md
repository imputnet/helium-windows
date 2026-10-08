# Chrome installation and migration flow

## Implemented standalone flow

The downloadable ZIP has `manifest.json`, the popup, its modules and the launcher template directly at its root. `guide.html` sits beside them. A user extracts one folder and can select that folder in Chrome's **Load unpacked** picker. The ZIP excludes development tests, Node dependencies and sample exports.

1. **Install in Chrome:** open `chrome://extensions`, enable Developer mode, click Load unpacked, select the folder containing `manifest.json`, and pin the helper.
2. **Capture and review:** open the popup to see eligible tab/window counts and skipped tabs. Save re-queries the current tabs rather than using a stale popup snapshot.
3. **Open in Helium:** save and double-click the generated `.cmd`; choose Helium's executable only if automatic detection cannot find it. Chrome tabs stay open.
4. **Finish:** verify the destination, remove the launcher, and optionally uninstall the Chrome helper.

No automatic Chrome installation is attempted. Chrome's installation UI remains the point where users see and accept the tab-access permissions. Managed environments that disable unpacked extensions need administrator approval. A public Chrome Web Store release would be a separate publishing decision; no store listing exists for this prototype.

## Possible future Helium onboarding entry

This entry is a proposal, not implemented by this change. It would need approval and changes in Helium's onboarding component.

On the existing browser-migration step, offer an optional **Bring open tabs from Chrome** entry. Explain: **Add the helper to Chrome, save a launcher, then open your tabs in Helium. Chrome tabs stay open.** Open the local installation guide or an approved distribution page. Offer a visible **Skip** action and retain the existing onboarding path.

Before saving, the helper shows counts and excluded tabs. Before executing, the guide explains that the local launcher contains URLs and executable code. After opening, the user confirms the destination and removes temporary exports. No cookie or password migration claim is part of this flow.

For general release, maintainers should decide whether an unsigned downloaded CMD file and developer-mode installation are acceptable. A store-distributed helper plus a separately approved destination importer is a possible future alternative; this prototype does not silently register a protocol handler, install native messaging, or change system policy.

## Evidence and references

- [Chrome's documented unpacked installation workflow](https://developer.chrome.com/docs/extensions/get-started/tutorial/hello-world)
- [Tabs API and its sensitive-URL permission](https://developer.chrome.com/docs/extensions/reference/api/tabs)
- [Windows API used to collect normal windows](https://developer.chrome.com/docs/extensions/reference/api/windows)
- [Script model and privacy limits](script-model.md)
