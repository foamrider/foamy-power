# Foamy Power

Battery status and power profiles for Omarchy Quattro.

![Foamy Power screenshot](preview.png)

## Install

Requires Omarchy Quattro, Python 3, UPower, `busctl`, `powerprofilesctl` from
power-profiles-daemon, and Symbols Nerd Font (included with Omarchy). Keep Omarchy’s built-in battery service enabled for
automatic profile switching.

```sh
omarchy plugin add https://github.com/foamrider/foamy-power.git --enable
```

Remove any previous power widget from the bar. The widget hides when no system
battery is present.

## Use

- Left-click to see battery readings and choose a power profile.
- Profile selections last until the power source changes.
- Open the cog to set separate AC and battery defaults and bar percentage.
- Enable **Show bar percentage** to reveal **Show only when battery is low**. The second option limits the percentage to 10% or below while discharging.
- Right-click to toggle the percentage on horizontal bars.

Percentage preferences are stored in `shell.json`. Power defaults
use Omarchy’s existing files in `~/.local/state/omarchy/powerprofiles` (or the
configured state directory). Plugging in or unplugging applies the matching default.
Charge limits are shown when available; the plugin does not change them.

## Remove

```sh
omarchy plugin remove foamy.power
```

Restore the stock power widget through the bar settings if needed. The selected
power profile and saved AC/battery defaults remain in place. Omarchy's stock
battery service continues to apply those defaults when the power source changes.

Omarchy manages the plugin entry in `shell.json`. Packages and data outside
the plugin directory are retained unless you remove them separately.

## License

Licensed under [MIT](LICENSE). Omarchy and Lucide notices are in
[LICENSE-OMARCHY](LICENSE-OMARCHY) and [LICENSE-LUCIDE](LICENSE-LUCIDE).

Provided **as is**, without warranty or guaranteed support. Use at your own risk.

Language follows **Omarchy → Setup → Language** on Omarchy 4.5. Plugin language overrides are no longer used. Omarchy 4.0 displays the plugin in English. Missing translations fall back to English.

Translation checks: `python3 tests/i18n-runtime.py` uses the installed shell. Set `OMARCHY_PATH` to a 4.5 source tree to check live language switching against that version.
