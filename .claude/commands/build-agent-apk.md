# Build & Deploy Android Agent APK

Build the DeviceKit Agent Android app, install it on a connected device, and relaunch. The user may optionally provide: **$ARGUMENTS** (e.g. "just build", "build and install", device serial)

## Environment Setup

The build requires JAVA_HOME and ANDROID_HOME. Standard Windows locations:

```
JAVA_HOME = C:\Program Files\Android\Android Studio\jbr
ANDROID_HOME = %LOCALAPPDATA%\Android\Sdk
ADB = %LOCALAPPDATA%\Android\Sdk\platform-tools\adb
```

Since these are not in the system PATH, all commands must be run via Git Bash with inline env vars. In Git Bash the SDK resolves as `~/AppData/Local/Android/Sdk`; set a shorthand once per session:

```bash
ADB=~/AppData/Local/Android/Sdk/platform-tools/adb
```

## Steps

### 1. Build the Debug APK

Run the Gradle build from the repo root (the project lives in `agent-android/`):

```bash
JAVA_HOME="/c/Program Files/Android/Android Studio/jbr" \
ANDROID_HOME=~/AppData/Local/Android/Sdk \
./agent-android/gradlew -p agent-android assembleDebug
```

The APK is output to:
```
agent-android/app/build/outputs/apk/debug/app-debug.apk
```

If the build fails, read the error output. Common issues:
- **Kotlin compile errors**: Fix the source file indicated in the error
- **Resource errors**: Check XML files in `res/` for typos or missing references
- **Missing dependencies**: Check `app/build.gradle.kts`

### 2. Check Connected Devices

```bash
"$ADB" devices
```

This lists devices by serial number (e.g. `ABC1234567`). If no device shows, the user needs to:
- Enable USB Debugging on the phone
- Trust the computer when prompted
- Reconnect the USB cable

### 3. Install the APK

```bash
"$ADB" -s <SERIAL> install -r \
  agent-android/app/build/outputs/apk/debug/app-debug.apk
```

The `-r` flag allows reinstall over existing app without losing data.

### 4. Relaunch the App

Force-stop and cold restart to pick up all changes:

```bash
"$ADB" -s <SERIAL> shell \
  "am start -S -W -n com.devicekit.agent/.MainActivity --activity-clear-task"
```

This ensures a cold launch (`LaunchState: COLD` in output).

### 5. Verify

- Check the adb output shows `Status: ok` and `Complete`
- If the app crashes on launch, check logcat:
  ```bash
  "$ADB" -s <SERIAL> logcat -d --pid=$(
    "$ADB" -s <SERIAL> shell pidof com.devicekit.agent
  ) | tail -50
  ```

## Key Paths

| Item | Path |
|------|------|
| Project root | `agent-android/` (in the repo root) |
| App source | `app/src/main/java/com/devicekit/agent/` |
| Layouts | `app/src/main/res/layout/` |
| Drawables | `app/src/main/res/drawable/` |
| Manifest | `app/src/main/AndroidManifest.xml` |
| Build config | `app/build.gradle.kts` |
| Output APK | `app/build/outputs/apk/debug/app-debug.apk` |

## Notes

- The app package is `com.devicekit.agent`
- Main activity: `.MainActivity`
- The foreground service (`BackgroundAgent`) may keep the process alive after `am force-stop`. Use `am start -S` to force-stop and start in one command.
- The agent starts an embedded HTTP server on port **9800** and a UDP discovery service on port **9801** when the BackgroundAgent service is running.
