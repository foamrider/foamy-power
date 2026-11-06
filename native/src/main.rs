//! `foamy-power-helper`: changes the power profile or Omarchy's AC/battery
//! default profiles, for a user action in the widget. Readings (battery,
//! active profile, defaults) come from Quickshell's UPower and PowerProfiles
//! services in the widget itself; this helper never runs while you only look.
//! It replaces `power_action.py` with the same contract.
//!
//! # Arguments
//!
//! - `set <profile>`: makes `<profile>` the active profile until the power
//!   source changes; the saved defaults stay as they are.
//! - `default <ac|battery> <profile>`: saves the default of a source; applies
//!   it (through `omarchy-powerprofiles-set`) only when that source is the
//!   current one.
//!
//! `<profile>` is `power-saver`, `balanced` or `performance`. Anything else
//! (other subcommands, missing or extra arguments, non-UTF-8 arguments) is
//! `INVALID_ARGUMENT`, exit 2, and runs nothing. (The Python helper's
//! argparse printed usage to stderr and nothing on stdout for these.)
//!
//! # Reply
//!
//! Exactly one compact JSON line on stdout, also on failure: `{"ok":true}`
//! (exit 0) or `{"ok":false,"error":{"code":…,"message":…}}` (exit 1; 2 for
//! `INVALID_ARGUMENT`; 101 and code `INTERNAL` for a helper bug). stderr
//! stays empty; child diagnostics are captured and dropped because they can
//! contain machine identifiers. Codes and their fixed messages:
//!
//! | code | message |
//! |---|---|
//! | `INVALID_ARGUMENT` | Invalid power profile or source. |
//! | `BUSY` | Another power-profile change is running. Try again. |
//! | `MISSING_COMMAND` | Required command is missing: `<program>`. |
//! | `TIMEOUT` | Power service timed out. Try again. |
//! | `COMMAND_FAILED` | `<program>` failed. Check the power service and permissions. |
//! | `INVALID_RESPONSE` | Invalid response from UPower. |
//! | `UNKNOWN_SOURCE` | Cannot determine the power source. |
//! | `PROFILES_UNAVAILABLE` | Power profiles are unavailable. Check power-profiles-daemon. |
//! | `PROFILE_UNAVAILABLE` | This power profile is not available on this machine. |
//! | `SOURCE_UNSTABLE` | Power source keeps changing. Try again when it is stable. |
//! | `DEFAULT_SAVED_APPLY_FAILED` | Default saved, but the active profile could not be applied. Try again. |
//! | `STATE_WRITE_FAILED` | Cannot save power-profile state. Check directory permissions. |
//!
//! # Steps
//!
//! 1. Take the action lock without waiting (`flock`, mode 0600, no
//!    symlinks, owned by this user): `$XDG_RUNTIME_DIR/foamy-power.lock`
//!    when `XDG_RUNTIME_DIR` is a directory, otherwise
//!    `${XDG_CACHE_HOME:-$HOME/.cache}/foamy-power/action.lock` (directory
//!    created 0700). Held: `BUSY`. Cannot open: `STATE_WRITE_FAILED`. The
//!    lock never lives in Omarchy's state directory.
//! 2. Read the profiles: `busctl --system --json=short get-property
//!    net.hadess.PowerProfiles /net/hadess/PowerProfiles
//!    net.hadess.PowerProfiles ActiveProfile Profiles` (never
//!    `powerprofilesctl`). Line 1 is `{"data":<active>}`, line 2
//!    `{"data":[{"Profile":{"data":<name>}},…]}`; anything else, or an
//!    active profile outside the known ones the daemon lists, is
//!    `PROFILES_UNAVAILABLE`. A requested profile the daemon doesn't list is
//!    `PROFILE_UNAVAILABLE`.
//! 3. Read the source: `busctl --system --json=short call
//!    org.freedesktop.UPower /org/freedesktop/UPower
//!    org.freedesktop.DBus.Properties GetAll s org.freedesktop.UPower`,
//!    `{"data":[{<name>:{"data":…},…}]}` (`INVALID_RESPONSE` otherwise);
//!    `OnBattery` must be a boolean (`UNKNOWN_SOURCE` otherwise).
//! 4. `set`: `busctl --system set-property net.hadess.PowerProfiles
//!    /net/hadess/PowerProfiles net.hadess.PowerProfiles ActiveProfile s
//!    <profile>`, then restore (below).
//!    `default`: write `<profile>\n` to `<state>/<source>` (below), then
//!    re-read the source, run `omarchy-powerprofiles-set <source>` if it is
//!    the current one, and restore. Any failure after the write is
//!    `DEFAULT_SAVED_APPLY_FAILED`.
//! 5. Restore: a cable transition during the action wins over it. Up to 3
//!    times: re-read the source; unchanged ends the action; changed runs
//!    `omarchy-powerprofiles-set <new source>`. Still changing:
//!    `SOURCE_UNSTABLE`.
//!
//! # Files
//!
//! `<state>` is `$OMARCHY_POWERPROFILES_STATE_DIR`, else
//! `${XDG_STATE_HOME:-$HOME/.local/state}/omarchy/powerprofiles` (empty
//! variables count as unset, as in Omarchy's scripts and the widget), created
//! with missing parents (mode 0777 minus the umask). The default file is
//! replaced atomically: a temporary file in `<state>` (`O_EXCL|O_NOFOLLOW`),
//! mode 0600, fsync, rename, directory fsync. Stricter than the Python
//! helper, which also wrote mode 0600: an existing `<state>/<source>` that is
//! a symlink or not owned by this user, or a `<state>` that is not owned by
//! this user or is writable by group or others, is refused
//! (`STATE_WRITE_FAILED`) instead of replaced. Any other file error is
//! `STATE_WRITE_FAILED` too.
//!
//! # Children
//!
//! Run by name from `PATH`, with the helper's environment plus `LC_ALL=C`,
//! stdin `/dev/null`, stdout and stderr captured (at most 256 KiB each; more
//! kills the child: `COMMAND_FAILED`), a 5 s deadline each (`TIMEOUT`; the
//! whole process group is killed), their own process group and
//! `PR_SET_PDEATHSIG`. Not found: `MISSING_COMMAND`; another start failure
//! or a non-zero exit: `COMMAND_FAILED` (the Python helper reported a start
//! failure other than "not found" as `STATE_WRITE_FAILED`). The caller wraps
//! the helper in `timeout --kill-after=1s 30s`.

use std::ffi::OsString;
use std::fs::DirBuilder;
use std::io::ErrorKind;
use std::path::{Path, PathBuf};
use std::process::ExitCode;
use std::time::Duration;

use foamy_helper::child::Bounded;
use foamy_helper::lock::FileLock;
use foamy_helper::{Failure, fs, json};
use serde_json::{Map, Value, json};

const PROFILES: [&str; 3] = ["power-saver", "balanced", "performance"];
const UPOWER: &str = "org.freedesktop.UPower";
const ROOT: &str = "/org/freedesktop/UPower";
const PPD: &str = "net.hadess.PowerProfiles";
const PPD_PATH: &str = "/net/hadess/PowerProfiles";
const CHILD_TIMEOUT: Duration = Duration::from_secs(5);
const MAX_OUTPUT: usize = 256 * 1024;
const SOURCE_TRIES: usize = 3;

const PROFILES_UNAVAILABLE: &str = "Power profiles are unavailable. Check power-profiles-daemon.";
const INVALID_RESPONSE: &str = "Invalid response from UPower.";

fn failure(code: &str, message: &str) -> Failure {
    Failure::coded(code, message)
}

fn state_write_failed() -> Failure {
    failure(
        "STATE_WRITE_FAILED",
        "Cannot save power-profile state. Check directory permissions.",
    )
}

#[derive(Debug, Clone, Copy, PartialEq, Eq)]
enum Source {
    Ac,
    Battery,
}

impl Source {
    fn parse(text: &str) -> Option<Source> {
        match text {
            "ac" => Some(Source::Ac),
            "battery" => Some(Source::Battery),
            _ => None,
        }
    }

    fn name(self) -> &'static str {
        match self {
            Source::Ac => "ac",
            Source::Battery => "battery",
        }
    }
}

#[derive(Debug, PartialEq, Eq)]
struct Action {
    profile: &'static str,
    source: Option<Source>,
}

fn parse_args(args: &[OsString]) -> Result<Action, Failure> {
    let invalid =
        || failure("INVALID_ARGUMENT", "Invalid power profile or source.").with_exit_code(2);
    let args: Vec<&str> = args
        .iter()
        .map(|arg| arg.to_str().ok_or_else(invalid))
        .collect::<Result<_, _>>()?;
    let profile = |text: &str| PROFILES.into_iter().find(|&known| known == text);
    match args.as_slice() {
        ["set", name] => Ok(Action {
            profile: profile(name).ok_or_else(invalid)?,
            source: None,
        }),
        ["default", source, name] => Ok(Action {
            profile: profile(name).ok_or_else(invalid)?,
            source: Some(Source::parse(source).ok_or_else(invalid)?),
        }),
        _ => Err(invalid()),
    }
}

/// Runs a system tool within the bounds above; its stdout on success.
fn run(program: &str, args: &[&str]) -> Result<String, Failure> {
    let output = Bounded::new(program)
        .args(args)
        .env("LC_ALL", "C")
        .timeout(CHILD_TIMEOUT)
        .max_output(MAX_OUTPUT)
        .run();
    let failed = || {
        // Service diagnostics can contain machine identifiers; report a stable recovery message.
        failure(
            "COMMAND_FAILED",
            &format!("{program} failed. Check the power service and permissions."),
        )
    };
    let output = match output {
        Ok(output) => output,
        Err(error) if error.kind() == ErrorKind::NotFound => {
            return Err(failure(
                "MISSING_COMMAND",
                &format!("Required command is missing: {program}."),
            ));
        }
        Err(_) => return Err(failed()),
    };
    if output.timed_out {
        return Err(failure("TIMEOUT", "Power service timed out. Try again."));
    }
    if !output.success() {
        return Err(failed());
    }
    Ok(output.stdout_lossy())
}

fn field<'a>(value: &'a Value, name: &str) -> Option<&'a Value> {
    value.as_object()?.get(name)
}

/// The known profiles the daemon lists, in `PROFILES` order, and the active
/// one, from `busctl --json=short get-property … ActiveProfile Profiles`.
fn parse_profiles(output: &str) -> Result<(Vec<&'static str>, &'static str), Failure> {
    let unavailable = || failure("PROFILES_UNAVAILABLE", PROFILES_UNAVAILABLE);
    let lines: Vec<Value> = output
        .lines()
        .filter(|line| !line.trim().is_empty())
        .map(serde_json::from_str)
        .collect::<Result<_, _>>()
        .map_err(|_| unavailable())?;
    let active = lines
        .first()
        .and_then(|line| field(line, "data"))
        .ok_or_else(unavailable)?;
    let entries = lines
        .get(1)
        .and_then(|line| field(line, "data"))
        .and_then(Value::as_array)
        .ok_or_else(unavailable)?;
    let listed: Vec<&Value> = entries
        .iter()
        .map(|entry| field(entry, "Profile").and_then(|profile| field(profile, "data")))
        .collect::<Option<_>>()
        .ok_or_else(unavailable)?;
    let available: Vec<&'static str> = PROFILES
        .into_iter()
        .filter(|&profile| listed.iter().any(|name| name.as_str() == Some(profile)))
        .collect();
    let active = available
        .iter()
        .copied()
        .find(|&profile| active.as_str() == Some(profile))
        .ok_or_else(unavailable)?;
    Ok((available, active))
}

/// The source from `busctl --json=short call … GetAll s org.freedesktop.UPower`.
fn parse_source(output: &str) -> Result<Source, Failure> {
    let invalid = || failure("INVALID_RESPONSE", INVALID_RESPONSE);
    let response: Value = serde_json::from_str(output).map_err(|_| invalid())?;
    let values: &Map<String, Value> = field(&response, "data")
        .and_then(Value::as_array)
        .and_then(|data| data.first())
        .and_then(Value::as_object)
        .ok_or_else(invalid)?;
    let mut on_battery = None;
    for (name, value) in values {
        let data = field(value, "data").ok_or_else(invalid)?;
        if name == "OnBattery" {
            on_battery = Some(data);
        }
    }
    match on_battery.and_then(Value::as_bool) {
        Some(true) => Ok(Source::Battery),
        Some(false) => Ok(Source::Ac),
        None => Err(failure(
            "UNKNOWN_SOURCE",
            "Cannot determine the power source.",
        )),
    }
}

fn profile_status() -> Result<Vec<&'static str>, Failure> {
    let output = run(
        "busctl",
        &[
            "--system",
            "--json=short",
            "get-property",
            PPD,
            PPD_PATH,
            PPD,
            "ActiveProfile",
            "Profiles",
        ],
    )?;
    Ok(parse_profiles(&output)?.0)
}

fn power_source() -> Result<Source, Failure> {
    let output = run(
        "busctl",
        &[
            "--system",
            "--json=short",
            "call",
            UPOWER,
            ROOT,
            "org.freedesktop.DBus.Properties",
            "GetAll",
            "s",
            UPOWER,
        ],
    )?;
    parse_source(&output)
}

fn apply_profile(profile: &str) -> Result<(), Failure> {
    run(
        "busctl",
        &[
            "--system",
            "set-property",
            PPD,
            PPD_PATH,
            PPD,
            "ActiveProfile",
            "s",
            profile,
        ],
    )
    .map(drop)
}

fn apply_source_default(source: Source) -> Result<(), Failure> {
    run("omarchy-powerprofiles-set", &[source.name()]).map(drop)
}

/// A cable transition during a manual operation must win over the old source's request.
fn restore_if_source_changed(mut previous: Source) -> Result<(), Failure> {
    for _ in 0..SOURCE_TRIES {
        let current = power_source()?;
        if current == previous {
            return Ok(());
        }
        apply_source_default(current)?;
        previous = current;
    }
    Err(failure(
        "SOURCE_UNSTABLE",
        "Power source keeps changing. Try again when it is stable.",
    ))
}

/// An environment variable; empty counts as unset.
type Env<'a> = &'a dyn Fn(&str) -> Option<OsString>;

fn system_env(name: &str) -> Option<OsString> {
    std::env::var_os(name).filter(|value| !value.is_empty())
}

fn home(env: Env) -> Result<PathBuf, Failure> {
    env("HOME")
        .map(PathBuf::from)
        .or_else(|| std::env::home_dir().filter(|home| !home.as_os_str().is_empty()))
        .ok_or_else(state_write_failed)
}

fn state_directory(env: Env) -> Result<PathBuf, Failure> {
    if let Some(dir) = env("OMARCHY_POWERPROFILES_STATE_DIR") {
        return Ok(PathBuf::from(dir));
    }
    let state = match env("XDG_STATE_HOME") {
        Some(state) => PathBuf::from(state),
        None => home(env)?.join(".local/state"),
    };
    Ok(state.join("omarchy/powerprofiles"))
}

/// Where the action lock lives, and the directory to create first (0700) if any.
fn lock_location(env: Env) -> Result<(PathBuf, Option<PathBuf>), Failure> {
    if let Some(runtime) = env("XDG_RUNTIME_DIR").map(PathBuf::from)
        && runtime.is_dir()
    {
        return Ok((runtime.join("foamy-power.lock"), None));
    }
    let cache = match env("XDG_CACHE_HOME") {
        Some(cache) => PathBuf::from(cache),
        None => home(env)?.join(".cache"),
    };
    let dir = cache.join("foamy-power");
    Ok((dir.join("action.lock"), Some(dir)))
}

/// Fails promptly when another widget instance is applying a change; stale intent is never queued.
fn action_lock(env: Env) -> Result<FileLock, Failure> {
    let (path, dir) = lock_location(env)?;
    if let Some(dir) = dir {
        fs::ensure_private_dir(&dir).map_err(|_| state_write_failed())?;
    }
    FileLock::try_exclusive(&path)
        .map_err(|_| state_write_failed())?
        .ok_or_else(|| {
            failure(
                "BUSY",
                "Another power-profile change is running. Try again.",
            )
        })
}

fn atomic_default(dir: &Path, source: Source, profile: &str) -> Result<(), Failure> {
    DirBuilder::new()
        .recursive(true)
        .create(dir)
        .map_err(|_| state_write_failed())?;
    fs::write_atomic(
        &dir.join(source.name()),
        format!("{profile}\n").as_bytes(),
        0o600,
    )
    .map_err(|_| state_write_failed())
}

fn change_profile(action: &Action, env: Env) -> Result<Value, Failure> {
    let _lock = action_lock(env)?;
    let available = profile_status()?;
    if !available.contains(&action.profile) {
        return Err(failure(
            "PROFILE_UNAVAILABLE",
            "This power profile is not available on this machine.",
        ));
    }
    let current = power_source()?;
    match action.source {
        None => {
            apply_profile(action.profile)?;
            restore_if_source_changed(current)?;
        }
        Some(source) => {
            atomic_default(&state_directory(env)?, source, action.profile)?;
            // Persist the inactive source without briefly applying its profile to the current source.
            let applied = (|| {
                let current = power_source()?;
                if current == source {
                    apply_source_default(current)?;
                }
                restore_if_source_changed(current)
            })();
            applied.map_err(|_| {
                failure(
                    "DEFAULT_SAVED_APPLY_FAILED",
                    "Default saved, but the active profile could not be applied. Try again.",
                )
            })?;
        }
    }
    Ok(json!({"ok": true}))
}

fn error_reply(failure: &Failure) -> Value {
    json!({"ok": false, "error": {"code": failure.code, "message": failure.message}})
}

fn main() -> ExitCode {
    json::run(
        || {
            let args: Vec<OsString> = std::env::args_os().skip(1).collect();
            let action = parse_args(&args)?;
            change_profile(&action, &system_env)
        },
        error_reply,
    )
}

#[cfg(test)]
mod tests {
    use super::*;
    use std::collections::HashMap;

    fn args(list: &[&str]) -> Result<Action, Failure> {
        parse_args(&list.iter().map(OsString::from).collect::<Vec<_>>())
    }

    fn env_of(pairs: &[(&str, &str)]) -> impl Fn(&str) -> Option<OsString> {
        let map: HashMap<String, OsString> = pairs
            .iter()
            .filter(|(_, value)| !value.is_empty())
            .map(|(name, value)| (name.to_string(), OsString::from(value)))
            .collect();
        move |name| map.get(name).cloned()
    }

    #[test]
    fn arguments_are_exact() {
        assert_eq!(
            args(&["set", "balanced"]).unwrap(),
            Action {
                profile: "balanced",
                source: None
            }
        );
        assert_eq!(
            args(&["default", "battery", "power-saver"]).unwrap(),
            Action {
                profile: "power-saver",
                source: Some(Source::Battery)
            }
        );
        for bad in [
            &[][..],
            &["status"],
            &["set"],
            &["set", "turbo"],
            &["set", "balanced", "x"],
            &["default", "ac"],
            &["default", "mains", "balanced"],
            &["default", "ac", "Balanced"],
            &["--help"],
        ] {
            let failure = args(bad).unwrap_err();
            assert_eq!(
                (failure.code.as_str(), failure.exit_code),
                ("INVALID_ARGUMENT", 2),
                "{bad:?}"
            );
        }
        use std::os::unix::ffi::OsStringExt;
        let invalid = parse_args(&[OsString::from("set"), OsString::from_vec(vec![0xff])]);
        assert_eq!(invalid.unwrap_err().exit_code, 2);
    }

    #[test]
    fn profiles_parse_like_busctl_prints_them() {
        let reply = "{\"type\":\"s\",\"data\":\"performance\"}\n{\"type\":\"aa{sv}\",\"data\":[{\"Profile\":{\"type\":\"s\",\"data\":\"performance\"}},{\"Driver\":{\"type\":\"s\",\"data\":\"x\"},\"Profile\":{\"type\":\"s\",\"data\":\"power-saver\"}},{\"Profile\":{\"type\":\"s\",\"data\":\"extreme\"}}]}\n";
        assert_eq!(
            parse_profiles(reply).unwrap(),
            (vec!["power-saver", "performance"], "performance")
        );
        // Blank lines and CRLF are tolerated.
        assert!(parse_profiles(&format!("\n{}", reply.replace('\n', "\r\n"))).is_ok());
    }

    #[test]
    fn unusable_profiles_are_unavailable() {
        for reply in [
            "",
            "{}",
            "nope",
            "{\"data\":\"balanced\"}",
            "{\"data\":\"balanced\"}\n{\"data\":\"balanced\"}",
            "{\"data\":\"balanced\"}\n{\"data\":[{\"Profile\":\"balanced\"}]}",
            "{\"data\":\"balanced\"}\n{\"data\":[[\"balanced\"]]}",
            "{\"data\":\"turbo\"}\n{\"data\":[{\"Profile\":{\"data\":\"turbo\"}}]}",
            "{\"data\":\"balanced\"}\n{\"data\":[{\"Profile\":{\"data\":\"performance\"}}]}",
            "{\"data\":1}\n{\"data\":[{\"Profile\":{\"data\":\"balanced\"}}]}",
            "[\"balanced\"]\n{\"data\":[{\"Profile\":{\"data\":\"balanced\"}}]}",
        ] {
            assert_eq!(
                parse_profiles(reply).unwrap_err().code,
                "PROFILES_UNAVAILABLE",
                "{reply}"
            );
        }
    }

    #[test]
    fn source_needs_a_boolean_on_battery() {
        let reply = |value: &str| {
            format!(
                "{{\"type\":\"a{{sv}}\",\"data\":[{{\"Lid\":{{\"type\":\"b\",\"data\":false}},\"OnBattery\":{{\"type\":\"b\",\"data\":{value}}}}}]}}\n"
            )
        };
        assert_eq!(parse_source(&reply("true")).unwrap(), Source::Battery);
        assert_eq!(parse_source(&reply("false")).unwrap(), Source::Ac);
        assert_eq!(
            parse_source(&reply("1")).unwrap_err().code,
            "UNKNOWN_SOURCE"
        );
        assert_eq!(
            parse_source("{\"data\":[{\"Lid\":{\"data\":true}}]}")
                .unwrap_err()
                .code,
            "UNKNOWN_SOURCE"
        );
        for bad in [
            "",
            "{",
            "[]",
            "{\"data\":[]}",
            "{\"data\":{\"0\":{}}}",
            "{\"data\":[\"x\"]}",
            "{\"data\":[{\"OnBattery\":true}]}",
            "{\"data\":[{\"OnBattery\":{\"data\":true},\"Other\":{}}]}",
            "{\"data\":[{}]} {}",
        ] {
            assert_eq!(
                parse_source(bad).unwrap_err().code,
                "INVALID_RESPONSE",
                "{bad}"
            );
        }
    }

    #[test]
    fn state_directory_follows_omarchy() {
        let dir = |pairs: &[(&str, &str)]| state_directory(&env_of(pairs)).unwrap();
        assert_eq!(
            dir(&[
                ("OMARCHY_POWERPROFILES_STATE_DIR", "/s"),
                ("XDG_STATE_HOME", "/x"),
                ("HOME", "/h")
            ]),
            PathBuf::from("/s")
        );
        assert_eq!(
            dir(&[("XDG_STATE_HOME", "/x"), ("HOME", "/h")]),
            PathBuf::from("/x/omarchy/powerprofiles")
        );
        assert_eq!(
            dir(&[
                ("OMARCHY_POWERPROFILES_STATE_DIR", ""),
                ("XDG_STATE_HOME", ""),
                ("HOME", "/h")
            ]),
            PathBuf::from("/h/.local/state/omarchy/powerprofiles")
        );
    }

    #[test]
    fn lock_lives_in_the_runtime_dir_or_the_cache() {
        let runtime = std::env::temp_dir();
        let runtime = runtime.to_str().unwrap();
        assert_eq!(
            lock_location(&env_of(&[("XDG_RUNTIME_DIR", runtime), ("HOME", "/h")])).unwrap(),
            (Path::new(runtime).join("foamy-power.lock"), None)
        );
        let missing = "/nonexistent/foamy-power-test";
        assert_eq!(
            lock_location(&env_of(&[
                ("XDG_RUNTIME_DIR", missing),
                ("XDG_CACHE_HOME", "/c")
            ]))
            .unwrap(),
            (
                PathBuf::from("/c/foamy-power/action.lock"),
                Some(PathBuf::from("/c/foamy-power"))
            )
        );
        assert_eq!(
            lock_location(&env_of(&[("HOME", "/h")])).unwrap().0,
            PathBuf::from("/h/.cache/foamy-power/action.lock")
        );
    }

    #[test]
    fn errors_keep_the_python_reply_shape() {
        assert_eq!(
            error_reply(&failure("BUSY", "later")),
            json!({"ok": false, "error": {"code": "BUSY", "message": "later"}})
        );
    }
}
