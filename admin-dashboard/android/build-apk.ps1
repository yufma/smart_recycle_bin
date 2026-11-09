# Builds the Android app (a WebView around the dashboard) without network, signed with the debug key
# for testing. Output: android\dist\reloop-admin.apk
#   .\android\build-apk.ps1
$root = $PSScriptRoot
if (-not $env:JAVA_HOME) { $env:JAVA_HOME = 'C:\Program Files\Eclipse Adoptium\jdk-17.0.20.101-hotspot' }
if (-not $env:ANDROID_HOME) { $env:ANDROID_HOME = 'C:\Android\Sdk' }

# Gradle prints warnings on stderr; success is judged by the exit code only.
Push-Location $root
try {
  & .\gradlew.bat assembleRelease --offline --no-daemon --console=plain 2>&1 | ForEach-Object { "$_" }
  $code = $LASTEXITCODE
} finally {
  Pop-Location
}
if ($code -ne 0) {
  Write-Host "Gradle build failed (exit $code)"
  exit $code
}
$apk = Join-Path $root 'app\build\outputs\apk\release\app-release.apk'
New-Item -ItemType Directory -Force -Path (Join-Path $root 'dist') | Out-Null
Copy-Item $apk (Join-Path $root 'dist\reloop-admin.apk') -Force -ErrorAction Stop
Write-Host "APK: $(Join-Path $root 'dist\reloop-admin.apk')"
