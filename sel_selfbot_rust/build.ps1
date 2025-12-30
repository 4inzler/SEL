$env:PATH = "C:\ProgramData\mingw64\mingw64\bin;" + $env:PATH
Set-Location -Path "C:\Users\Administrator\Documents\SEL-main\sel_selfbot_rust"
& "C:\ProgramData\chocolatey\bin\cargo.exe" build --release
