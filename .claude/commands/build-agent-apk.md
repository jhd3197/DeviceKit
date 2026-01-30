# Build & Deploy Android Agent APK

Build the DeviceKit Agent Android app, install it on a connected device, and relaunch. The user may optionally provide: **$ARGUMENTS** (e.g. "just build", "build and install", device serial)

## Environment Setup

The build requires JAVA_HOME and ANDROID_HOME. On this machine:

```
JAVA_HOME = C:\Program Files\Android\Android Studio\jbr
ANDROID_HOME = C:\Users\Juan\AppData\Local\Android\Sdk
ADB = C:\Users\Juan\AppData\Local\Android\Sdk\platform-tools\adb
```

Since these are not in the system PATH, all commands must be run via Git Bash with inline env vars.

## Steps

### 1. Build the Debug APK

Run the Gradle build from the `agent-android` directory:

```bash
JAVA_HOME="/c/Program Files/Android/Android Studio/jbr" \
ANDROID_HOME="/c/Users/Juan/AppData/Local/Android/Sdk" \
/c/Users/Juan/Documents/GitHub/DeviceKit/agent-android/gradlew \
  -p /c/Users/Juan/Documents/GitHub/DeviceKit/agent-android \
  assembleDebug
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
/c/Users/Juan/AppData/Local/Android/Sdk/platform-tools/adb devices
```

This lists devices by serial number (e.g. `R9TT311P25N`). If no device shows, the user needs to:
- Enable USB Debugging on the phone
- Trust the computer when prompted
- Reconnect the USB cable

### 3. Install the APK

```bash
/c/Users/Juan/AppData/Local/Android/Sdk/platform-tools/adb -s <SERIAL> install -r \
  /c/Users/Juan/Documents/GitHub/DeviceKit/agent-android/app/build/outputs/apk/debug/app-debug.apk
```

The `-r` flag allows reinstall over existing app without losing data.

### 4. Relaunch the App

Force-stop and cold restart to pick up all changes:

```bash
/c/Users/Juan/AppData/Local/Android/Sdk/platform-tools/adb -s <SERIAL> shell \
  "am start -S -W -n com.devicekit.agent/.MainActivity --activity-clear-task"
```

This ensures a cold launch (`LaunchState: COLD` in output).

### 5. Verify

- Check the adb output shows `Status: ok` and `Complete`
- If the app crashes on launch, check logcat:
  ```bash
  /c/Users/Juan/AppData/Local/Android/Sdk/platform-tools/adb -s <SERIAL> logcat -d --pid=$(
    /c/Users/Juan/AppData/Local/Android/Sdk/platform-tools/adb -s <SERIAL> shell pidof com.devicekit.agent
  ) | tail -50
  ```

## Key Paths

| Item | Path |
|------|------|
| Project root | `C:\Users\Juan\Documents\GitHub\DeviceKit\agent-android` |
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
