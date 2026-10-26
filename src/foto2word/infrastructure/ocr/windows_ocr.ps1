# Windows' own OCR (Windows.Media.Ocr, offline) over image files: one JSON line per text line,
# {"file": index, "text", "x0", "y0", "x1", "y1", "width", "height", "words": [[text, x, y,
# width, height], ...]} in pixels.
param([string]$Language = "ru")
$ErrorActionPreference = "Stop"
[Console]::OutputEncoding = [Text.Encoding]::UTF8
[Console]::InputEncoding = [Text.Encoding]::UTF8
Add-Type -AssemblyName System.Runtime.WindowsRuntime
$null = [Windows.Storage.StorageFile, Windows.Storage, ContentType = WindowsRuntime]
$null = [Windows.Media.Ocr.OcrEngine, Windows.Foundation, ContentType = WindowsRuntime]
$null = [Windows.Graphics.Imaging.BitmapDecoder, Windows.Graphics, ContentType = WindowsRuntime]
$null = [Windows.Globalization.Language, Windows.Globalization, ContentType = WindowsRuntime]
$asTask = [System.WindowsRuntimeSystemExtensions].GetMethods() | Where-Object {
    $_.Name -eq "AsTask" -and $_.GetParameters().Count -eq 1 -and
    $_.GetParameters()[0].ParameterType.Name -eq 'IAsyncOperation`1'
} | Select-Object -First 1
function Await($operation, [Type]$type) {
    $task = $asTask.MakeGenericMethod($type).Invoke($null, @($operation))
    $task.Wait() | Out-Null
    $task.Result
}
$engine = [Windows.Media.Ocr.OcrEngine]::TryCreateFromLanguage(
    [Windows.Globalization.Language]::new($Language))
$index = 0
foreach ($path in [Console]::In.ReadToEnd().Split("`n", [StringSplitOptions]::RemoveEmptyEntries)) {
    $file = Await ([Windows.Storage.StorageFile]::GetFileFromPathAsync($path.Trim())) ([Windows.Storage.StorageFile])
    $stream = Await ($file.OpenAsync([Windows.Storage.FileAccessMode]::Read)) ([Windows.Storage.Streams.IRandomAccessStream])
    $decoder = Await ([Windows.Graphics.Imaging.BitmapDecoder]::CreateAsync($stream)) ([Windows.Graphics.Imaging.BitmapDecoder])
    $bitmap = Await ($decoder.GetSoftwareBitmapAsync()) ([Windows.Graphics.Imaging.SoftwareBitmap])
    $result = Await ($engine.RecognizeAsync($bitmap)) ([Windows.Media.Ocr.OcrResult])
    foreach ($line in $result.Lines) {
        $boxes = $line.Words | ForEach-Object { $_.BoundingRect }
        [pscustomobject]@{
            file   = $index
            text   = $line.Text
            x0     = ($boxes | Measure-Object -Property X -Minimum).Minimum
            y0     = ($boxes | Measure-Object -Property Y -Minimum).Minimum
            x1     = ($boxes | ForEach-Object { $_.X + $_.Width } | Measure-Object -Maximum).Maximum
            y1     = ($boxes | ForEach-Object { $_.Y + $_.Height } | Measure-Object -Maximum).Maximum
            width  = $bitmap.PixelWidth
            height = $bitmap.PixelHeight
            words  = @($line.Words | ForEach-Object {
                ,@($_.Text, $_.BoundingRect.X, $_.BoundingRect.Y, $_.BoundingRect.Width, $_.BoundingRect.Height)
            })
        } | ConvertTo-Json -Compress -Depth 4
    }
    $stream.Dispose()
    $index++
}
