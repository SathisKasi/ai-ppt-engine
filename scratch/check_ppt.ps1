$pptx = "e:\yuvi_workspace\WORKSPACE\antigravity_workspace\ai-poc\output\test_new_techm.pptx"
try {
    $ppt = New-Object -ComObject PowerPoint.Application
    $pres = $ppt.Presentations.Open($pptx, [Microsoft.Office.Core.MsoTriState]::msoTrue, [Microsoft.Office.Core.MsoTriState]::msoFalse, [Microsoft.Office.Core.MsoTriState]::msoFalse)
    Write-Host "SUCCESSFULLY OPENED IN POWERPOINT! Slides:" $pres.Slides.Count
    $pres.Close()
    $ppt.Quit()
} catch {
    Write-Host "ERROR:" $_.Exception.Message
}
