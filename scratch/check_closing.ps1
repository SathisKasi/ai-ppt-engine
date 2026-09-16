$pptx = "e:\yuvi_workspace\WORKSPACE\antigravity_workspace\ai-poc\scratch\test_closing_pic.pptx"
try {
    $ppt = New-Object -ComObject PowerPoint.Application
    $pres = $ppt.Presentations.Open($pptx, [Microsoft.Office.Core.MsoTriState]::msoTrue, [Microsoft.Office.Core.MsoTriState]::msoFalse, [Microsoft.Office.Core.MsoTriState]::msoFalse)
    Write-Host "SUCCESS! Slides:" $pres.Slides.Count "Shapes:" $pres.Slides.Item(1).Shapes.Count
    $pres.Close()
    $ppt.Quit()
} catch {
    Write-Host "FAILED:" $_.Exception.Message
}
