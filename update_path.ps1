$currentPath = [Environment]::GetEnvironmentVariable('PATH', 'User')
$mingwPath = 'C:\ProgramData\mingw64\mingw64\bin'

if ($currentPath -notlike "*$mingwPath*") {
    $newPath = $currentPath + ';' + $mingwPath
    [Environment]::SetEnvironmentVariable('PATH', $newPath, 'User')
    Write-Host "Added MinGW to PATH"
} else {
    Write-Host "MinGW already in PATH"
}
