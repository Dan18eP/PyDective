param (
    [Parameter(Mandatory=$true)]
    [string]$ImagePath
)

[Console]::OutputEncoding = [System.Text.Encoding]::UTF8
$OutputEncoding = [System.Text.Encoding]::UTF8

Add-Type -AssemblyName System.Runtime.WindowsRuntime
$asTaskGeneric = [System.WindowsRuntimeSystemExtensions].GetMethods() | Where-Object { $_.Name -eq 'AsTask' -and $_.GetParameters().Count -eq 1 -and $_.GetParameters()[0].ParameterType.Name -eq 'IAsyncOperation`1' }[0]

function Await($WinRtTask, $ResultType) {
    $asTask = $asTaskGeneric.MakeGenericMethod($ResultType)
    $netTask = $asTask.Invoke($null, @($WinRtTask))
    $netTask.Wait(-1) | Out-Null
    $netTask.Result
}

[Windows.Globalization.Language, Windows.Globalization, ContentType=WindowsRuntime] | Out-Null
[Windows.Graphics.Imaging.BitmapDecoder, Windows.Graphics.Imaging, ContentType=WindowsRuntime] | Out-Null
[Windows.Media.Ocr.OcrEngine, Windows.Media.Ocr, ContentType=WindowsRuntime] | Out-Null
[Windows.Storage.StorageFile, Windows.Storage, ContentType=WindowsRuntime] | Out-Null

if (-not (Test-Path $ImagePath)) {
    Write-Output '{"text":"","lines":[]}'
    exit
}

$resolvedPath = (Resolve-Path $ImagePath).Path
$file = Await ([Windows.Storage.StorageFile]::GetFileFromPathAsync($resolvedPath)) ([Windows.Storage.StorageFile])
$stream = Await ($file.OpenAsync([Windows.Storage.FileAccessMode]::Read)) ([Windows.Storage.Streams.IRandomAccessStream])
$decoder = Await ([Windows.Graphics.Imaging.BitmapDecoder]::CreateAsync($stream)) ([Windows.Graphics.Imaging.BitmapDecoder])
$bitmap = Await ($decoder.GetSoftwareBitmapAsync()) ([Windows.Graphics.Imaging.SoftwareBitmap])

$engine = [Windows.Media.Ocr.OcrEngine]::TryCreateFromUserProfileLanguages()
if ($null -eq $engine) {
    $engine = [Windows.Media.Ocr.OcrEngine]::TryCreateFromLanguage([Windows.Globalization.Language]::new('es'))
}

if ($null -eq $engine) {
    Write-Output '{"text":"","lines":[]}'
    exit
}

$result = Await ($engine.RecognizeAsync($bitmap)) ([Windows.Media.Ocr.OcrResult])

$linesData = @()
foreach ($line in $result.Lines) {
    $minX = 999999
    $minY = 999999
    $maxX = 0
    $maxY = 0

    foreach ($w in $line.Words) {
        $r = $w.BoundingRect
        if ($r.X -lt $minX) { $minX = $r.X }
        if ($r.Y -lt $minY) { $minY = $r.Y }
        if (($r.X + $r.Width) -gt $maxX) { $maxX = ($r.X + $r.Width) }
        if (($r.Y + $r.Height) -gt $maxY) { $maxY = ($r.Y + $r.Height) }
    }

    $cleanLine = $line.Text -replace "[\x00-\x1f]", " "
    $linesData += @{
        text = $cleanLine
        bbox = @($minX, $minY, $maxX, $maxY)
    }
}

$cleanAllText = $result.Text -replace "[\x00-\x1f]", " "
$output = @{
    text = $cleanAllText
    lines = $linesData
}

ConvertTo-Json -Compress $output
