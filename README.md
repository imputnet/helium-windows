# helium-windows

Windows packaging for [Helium](https://github.com/imputnet/helium).

## Credits

This repo is based on
[ungoogled-chromium-windows](https://github.com/ungoogled-software/ungoogled-chromium-windows),
but is pretty heavily modified for Helium. Huge shout-out to everyone behind ungoogled-chromium,
they made working with Chromium infinitely easier.

A huge thank you to [Depot](https://depot.dev/) for sponsoring our runners, which handle the Windows
builds of Helium. Their high-performance infrastructure lets us compile and package Helium at least
8 times faster than with GitHub-hosted runners, allowing us to release new builds within hours, not days.

## License
All code, patches, modified portions of imported code or patches, and
any other content that is unique to Helium and not imported from other
repositories is licensed under GPL-3.0. See [LICENSE](LICENSE).

Any content imported from other projects retains its original license (for
example, any original unmodified code imported from ungoogled-chromium remains
licensed under their [BSD 3-Clause license](LICENSE.ungoogled_chromium)).

## Building

### Setting up

On Windows 11, run this in an elevated PowerShell:

```powershell
irm https://raw.githubusercontent.com/imputnet/helium-windows/main/devutils/setup.ps1 | iex
```

It installs Git, clones helium-windows onto a [Dev Drive](https://learn.microsoft.com/en-us/windows/dev-drive/),
creating one if there isn't one yet, and installs Visual Studio, Python, 7-Zip, q and the other
requirements from [`.config\configuration.winget`](.config/configuration.winget). It skips what
is already done, so it is safe to run again, including from a checkout with
`powershell -ExecutionPolicy Bypass -File devutils\setup.ps1`. A checkout that isn't on a Dev
Drive gets a new clone on one, since builds are much faster there. See `Get-Help devutils\setup.ps1`
for options such as `-SkipDevDrive`, which you can pass like this:

```powershell
iex "& {$(irm https://raw.githubusercontent.com/imputnet/helium-windows/main/devutils/setup.ps1)} -SkipDevDrive"
```

### Building a release

In PowerShell, from the checkout:

```powershell
# Replace TAG_OR_BRANCH_HERE with a tag or branch name
git checkout --recurse-submodules TAG_OR_BRANCH_HERE
python build.py
python package.py
```

A zip archive and installers will be created under `build`.

If `build.py` fails while downloading, remove `build\download_cache` and run it again. If it
fails later, remove everything in `build` except `download_cache` before running it again.

## Developer info

Load the development tools into PowerShell from the checkout, then set up the source tree:

```powershell
. .\dev.ps1
he setup    # or `he setup -c` to clone Chromium instead of downloading it
he build
he run
```

Run `he` to list the other commands, such as `he sub`/`he unsub` for domain and name
substitution, `he pull` to update both repositories, and `he wt` for worktrees.

### Updating patches

`he setup` merges the helium-chromium patches into `patches` and applies them all with q.
Use `q` (or `quilt`, an alias for it) in `build\src` to edit and refresh patches. See
ungoogled-chromium's [docs/developing.md](https://github.com/ungoogled-software/ungoogled-chromium/blob/master/docs/developing.md#updating-patches)
section "Updating patches" for the workflow. Before committing, run `he unmerge` to move the
shared patches back, then `.\devutils\check_patch_files.sh` from Git Bash to check the series.
Run `he merge` to continue working afterwards.

### Updating the pruning list

```powershell
python helium-chromium\devutils\update_lists.py -t build\src --domain-regex helium-chromium\domain_regex.list
```
