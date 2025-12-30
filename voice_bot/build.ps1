$env:PATH = "C:\Program Files\CMake\bin;C:\ProgramData\mingw64\mingw64\bin;" + $env:PATH
Set-Location -Path "C:\Users\Administrator\Documents\SEL-main\voice_bot"
& "C:\ProgramData\chocolatey\bin\cargo.exe" build --release
