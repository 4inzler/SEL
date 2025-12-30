# SEL Bot Vector Database Diagnostic Script
# Automates the diagnostic check for HTML/JavaScript poisoning

Write-Host "=" * 80 -ForegroundColor Cyan
Write-Host "SEL BOT VECTOR DATABASE DIAGNOSTICS" -ForegroundColor Cyan
Write-Host "=" * 80 -ForegroundColor Cyan
Write-Host ""

# Set paths
$diagnosticScript = "C:\Users\Public\vector_store_diagnostics.py"
$himStorePath = "C:\Users\Administrator\Documents\SEL-main\project_echo\data\him_store"
$reportPath = "C:\Users\Public\vector_store_diagnostic_report.json"

# Check if diagnostic script exists
if (-Not (Test-Path $diagnosticScript)) {
    Write-Host "❌ ERROR: Diagnostic script not found at $diagnosticScript" -ForegroundColor Red
    exit 1
}

Write-Host "✅ Found diagnostic script" -ForegroundColor Green
Write-Host ""

# Check if HIM store exists
Write-Host "Checking HIM store path: $himStorePath" -ForegroundColor Yellow
if (Test-Path $himStorePath) {
    Write-Host "✅ HIM store directory exists" -ForegroundColor Green

    # Get directory size
    $size = (Get-ChildItem -Path $himStorePath -Recurse -ErrorAction SilentlyContinue | Measure-Object -Property Length -Sum).Sum / 1MB
    Write-Host "   Size: $([math]::Round($size, 2)) MB" -ForegroundColor Gray
} else {
    Write-Host "❌ WARNING: HIM store not found at $himStorePath" -ForegroundColor Red
    Write-Host "   This could mean:" -ForegroundColor Yellow
    Write-Host "   • Vector database was deleted" -ForegroundColor Yellow
    Write-Host "   • SEL bot not initialized yet" -ForegroundColor Yellow
    Write-Host "   • Path is incorrect" -ForegroundColor Yellow
    Write-Host ""
    $response = Read-Host "Enter correct path or press Enter to exit"
    if ($response) {
        $himStorePath = $response
    } else {
        exit 1
    }
}

Write-Host ""
Write-Host "=" * 80 -ForegroundColor Cyan
Write-Host "RUNNING DIAGNOSTICS..." -ForegroundColor Cyan
Write-Host "=" * 80 -ForegroundColor Cyan
Write-Host ""

# Run diagnostic script
try {
    # Create input file with path
    $inputFile = "C:\Users\Public\diagnostic_input.txt"
    Set-Content -Path $inputFile -Value $himStorePath

    # Run Python script with input
    $result = Get-Content $inputFile | python $diagnosticScript 2>&1

    Write-Host $result

    # Clean up input file
    Remove-Item $inputFile -ErrorAction SilentlyContinue

    Write-Host ""
    Write-Host "=" * 80 -ForegroundColor Cyan
    Write-Host "QUICK ANALYSIS" -ForegroundColor Cyan
    Write-Host "=" * 80 -ForegroundColor Cyan
    Write-Host ""

    # Check if report was generated
    if (Test-Path $reportPath) {
        Write-Host "✅ Report generated at: $reportPath" -ForegroundColor Green

        # Parse report
        $report = Get-Content $reportPath | ConvertFrom-Json

        # Check for poisoning
        if ($report.malicious.contains_html -eq $true) {
            Write-Host ""
            Write-Host "❌ CRITICAL: HTML DETECTED IN VECTOR DATABASE" -ForegroundColor Red
            Write-Host "   Found in $($report.malicious.suspicious_count) file(s)" -ForegroundColor Red
            Write-Host ""
            Write-Host "Examples:" -ForegroundColor Yellow
            foreach ($example in $report.malicious.examples) {
                Write-Host "   • $example" -ForegroundColor Yellow
            }
            Write-Host ""
            Write-Host "⚠️  NEXT STEPS:" -ForegroundColor Yellow
            Write-Host "   1. Run fresh context test (see PENTEST_RESPONSE_PLAN.md STEP 2)" -ForegroundColor Yellow
            Write-Host "   2. Backup database: xcopy /E /I $himStorePath ${himStorePath}_POISONED" -ForegroundColor Yellow
            Write-Host "   3. Delete poisoned DB: rmdir /S /Q $himStorePath" -ForegroundColor Yellow
            Write-Host "   4. Restart SEL bot (creates clean DB)" -ForegroundColor Yellow
            Write-Host ""
        } elseif ($report.malicious.contains_scripts -eq $true) {
            Write-Host ""
            Write-Host "❌ CRITICAL: JAVASCRIPT DETECTED IN VECTOR DATABASE" -ForegroundColor Red
            Write-Host "   Found in $($report.malicious.suspicious_count) file(s)" -ForegroundColor Red
            Write-Host ""
            Write-Host "⚠️  Same cleanup steps as above apply" -ForegroundColor Yellow
            Write-Host ""
        } else {
            Write-Host ""
            Write-Host "✅ NO HTML/JAVASCRIPT DETECTED" -ForegroundColor Green
            Write-Host "   Vector database appears clean" -ForegroundColor Green
            Write-Host ""
            Write-Host "⚠️  NOTE: Still run fresh context test to confirm" -ForegroundColor Yellow
            Write-Host "   (see PENTEST_RESPONSE_PLAN.md STEP 2)" -ForegroundColor Yellow
            Write-Host ""
        }

        # Check for corruption
        if ($report.database.db_corrupted -eq $true) {
            Write-Host "❌ DATABASE CORRUPTED!" -ForegroundColor Red
            Write-Host "   Emergency rebuild required" -ForegroundColor Red
            Write-Host ""
        } elseif ($report.database.db_readable -eq $true) {
            Write-Host "✅ Database is readable and functional" -ForegroundColor Green
            Write-Host ""
        }

        # Check write capability
        if ($report.writes.can_write -eq $false) {
            Write-Host "❌ CANNOT WRITE TO DATABASE" -ForegroundColor Red
            Write-Host "   Check permissions" -ForegroundColor Red
            Write-Host ""
        }

    } else {
        Write-Host "⚠️  WARNING: Report file not generated" -ForegroundColor Yellow
        Write-Host "   Check output above for errors" -ForegroundColor Yellow
        Write-Host ""
    }

} catch {
    Write-Host "❌ ERROR running diagnostics:" -ForegroundColor Red
    Write-Host $_.Exception.Message -ForegroundColor Red
    Write-Host ""
    Write-Host "Try running manually:" -ForegroundColor Yellow
    Write-Host "   python $diagnosticScript" -ForegroundColor Yellow
    Write-Host ""
    exit 1
}

Write-Host "=" * 80 -ForegroundColor Cyan
Write-Host "DIAGNOSTIC COMPLETE" -ForegroundColor Cyan
Write-Host "=" * 80 -ForegroundColor Cyan
Write-Host ""
Write-Host "Full report saved to: $reportPath" -ForegroundColor Cyan
Write-Host "Full action plan: C:\Users\Public\PENTEST_RESPONSE_PLAN.md" -ForegroundColor Cyan
Write-Host ""

# Pause so user can read
Write-Host "Press any key to exit..." -ForegroundColor Gray
$null = $Host.UI.RawUI.ReadKey("NoEcho,IncludeKeyDown")
